#include "shell_window.h"

#include "assets_page.h"
#include "engine_page.h"
#include "mesh_page.h"
#include "sounds_page.h"
#include "trainzutil_page.h"

#include "icons.h"

#include <QApplication>
#include <QColor>
#include <QCursor>
#include <QEasingCurve>
#include <QGraphicsOpacityEffect>
#include <QPixmap>
#include <QPropertyAnimation>
#include <QEvent>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QLabel>
#include <QMouseEvent>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QScreen>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWindow>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {

QVariantMap item(const QString& id, const QString& label, bool alive = true) {
    QVariantMap row;
    row.insert(QStringLiteral("actId"), id);
    row.insert(QStringLiteral("label"), label);
    row.insert(QStringLiteral("shortcut"), QString());
    row.insert(QStringLiteral("sep"), false);
    row.insert(QStringLiteral("checked"), false);
    row.insert(QStringLiteral("alive"), alive);
    return row;
}

QString qml_dir() {
#ifdef QML_DIR
    return QStringLiteral(QML_DIR);
#else
    return {};
#endif
}

struct StudioCard {
    const char* id;
    const char* title;
    const char* blurb;
    const char* glyph;
};

}  // namespace

ShellBridge::ShellBridge(QObject* parent) : QObject(parent) {
    const StudioCard studios[] = {
        {"mesh", "Mesh Studio", "Mesh · FBX · lamps", "layers"},
        {"sounds", "Sounds Studio", "Loop · waveform · export", "graphic_eq"},
        {"engine", "Engine Tuner", "Curves · throttle · sim", "tune"},
        {"assets", "Assets Tools", "CDP · config · KUID", "inventory_2"},
        {"texmesh", "Texture & Mesh Lods", "LODs · maps · bake", "texture"},
        {"trainzutil", "TrainzUtil", "Install · CDP · zip", "upload_file"},
    };
    for (const StudioCard& studio : studios) {
        QVariantMap card;
        card.insert(QStringLiteral("studioId"), QString::fromUtf8(studio.id));
        card.insert(QStringLiteral("title"), QString::fromUtf8(studio.title));
        card.insert(QStringLiteral("blurb"), QString::fromUtf8(studio.blurb));
        card.insert(QStringLiteral("glyph"), material_glyph(studio.glyph));
        cards_.push_back(card);
    }
    const QList<QPair<QString, QString>> menu_rows = {
        {QStringLiteral("file"), QStringLiteral("File")},
        {QStringLiteral("edit"), QStringLiteral("Edit")},
        {QStringLiteral("view"), QStringLiteral("View")},
        {QStringLiteral("tools"), QStringLiteral("Tools")},
    };
    for (const auto& menu : menu_rows) {
        QVariantMap row;
        row.insert(QStringLiteral("key"), menu.first);
        row.insert(QStringLiteral("label"), menu.second);
        menus_.push_back(row);
    }
}

void ShellBridge::set_title(const QString& title) {
    title_ = title;
    emit changed();
}

void ShellBridge::set_page(const QString& page) {
    page_ = page;
    emit pageChanged(page);
    emit changed();
}

void ShellBridge::set_open_key(const QString& key) {
    open_key_ = key;
    emit changed();
}

void ShellBridge::set_zoomed(bool zoomed) {
    if (zoomed_ == zoomed) return;
    zoomed_ = zoomed;
    emit changed();
}

void ShellBridge::set_items(const QVariantList& items) {
    items_ = items;
    emit changed();
}

void ShellBridge::bump_menu() {
    ++menu_gen_;
    emit menuOpened();
}

void ShellBridge::openStudio(const QString& studio_id) {
    set_page(studio_id);
}

void ShellBridge::dropUrls(const QVariantList&) {}

void ShellBridge::requestClose() { emit closeRequested(); }
void ShellBridge::requestMin() { emit minRequested(); }
void ShellBridge::requestZoom() { emit zoomRequested(); }
void ShellBridge::startMove() { emit moveRequested(); }

void ShellBridge::toggleMenu(const QString& key, double x, double y) {
    emit menuRequested(key, static_cast<int>(x), static_cast<int>(y));
}

void ShellBridge::triggerItem(const QString& act_id) {
    set_open_key({});
    emit menuDismiss();
    if (act_id == QLatin1String("quit")) emit closeRequested();
    else if (!act_id.isEmpty()) set_page(act_id);
}

bool chrome_click_dismisses_menu(const QRect& menu, const QRect& title, const QPoint& global) {
    if (menu.adjusted(-4, -4, 4, 4).contains(global)) return false;
    if (title.adjusted(-2, -2, 2, 2).contains(global)) return false;
    return true;
}

LogoProvider::LogoProvider() : QQuickImageProvider(QQuickImageProvider::Pixmap) {}

QPixmap LogoProvider::requestPixmap(const QString&, QSize* size, const QSize&) {
    QPixmap pixmap(8, 8);
    pixmap.fill(Qt::transparent);
    if (size) *size = pixmap.size();
    return pixmap;
}

void prepare_qt_runtime() {
#ifdef QT_PREFIX
    qputenv("QT_PLUGIN_PATH", QT_PREFIX "/plugins");
    qputenv("QML_IMPORT_PATH", QT_PREFIX "/qml");
#endif
    qputenv("QSG_RHI_BACKEND", "software");
}

void ShellWindow::boot_stage(const QString& text, int pct) {
    if (boot_) boot_(text, pct);
}

ShellWindow::~ShellWindow() {
    if (qApp) qApp->removeEventFilter(this);
}

ShellWindow::ShellWindow(QWidget* parent, std::function<void(const QString&, int)> boot)
    : QWidget(parent), boot_(std::move(boot)) {
    boot_stage(QStringLiteral("Starting…"), 12);
    setWindowTitle(QStringLiteral("Trainz Studio"));
    // Min/max hints keep a thick frame so Windows snap (drag to the top edge) still works.
    setWindowFlags(Qt::Window | Qt::FramelessWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinMaxButtonsHint | Qt::WindowCloseButtonHint);
    resize(1100, 720);

    bridge_ = new ShellBridge(this);
    load_material_icons();
    title_ = load_quick(QStringLiteral("TitleBar.qml"), true);
    home_ = load_quick(QStringLiteral("HomePage.qml"), false);
    home_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    menu_ = load_quick(QStringLiteral("MenuDrop.qml"), true);
    // Tool, not Popup: Popup on this frameless host never took the mouse grab, so the menu stayed up.
    menu_->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint | Qt::WindowStaysOnTopHint | Qt::WindowDoesNotAcceptFocus);
    menu_->setAttribute(Qt::WA_TranslucentBackground, true);
    menu_->setAttribute(Qt::WA_ShowWithoutActivating, true);
    menu_->hide();
    qApp->installEventFilter(this);
    boot_stage(QStringLiteral("Chrome"), 40);

    blank_ = new QLabel(QStringLiteral("Home"));
    blank_->setAlignment(Qt::AlignCenter);
    blank_->setStyleSheet(QStringLiteral("background:#12161c;color:#f2f4f8;font-size:28px;"));

    trainz_ = new TrainzUtilPage(this);
    connect(trainz_, &TrainzUtilPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    engine_ = new EngineTunerPage(this);
    connect(engine_, &EngineTunerPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    assets_ = new AssetsPage(this);
    connect(assets_, &AssetsPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    sounds_ = new SoundsPage(this);
    connect(sounds_, &SoundsPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    mesh_ = new MeshStudioPage(this);
    connect(mesh_, &MeshStudioPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    stack_ = new QStackedWidget(this);
    stack_->addWidget(home_);
    stack_->addWidget(blank_);
    stack_->addWidget(trainz_);
    stack_->addWidget(engine_);
    stack_->addWidget(assets_);
    stack_->addWidget(sounds_);
    stack_->addWidget(mesh_);
    boot_stage(QStringLiteral("Studios"), 80);

    title_->setFixedHeight(60);
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    layout->addWidget(title_);
    layout->addWidget(stack_, 1);

    connect(bridge_, &ShellBridge::pageChanged, this, [this](const QString& page) {
        const bool home = page == QLatin1String("home");
        const bool trainz = page == QLatin1String("trainzutil");
        const bool engine = page == QLatin1String("engine");
        const bool assets = page == QLatin1String("assets");
        const bool texmesh = page == QLatin1String("texmesh");
        const bool sounds = page == QLatin1String("sounds");
        const bool mesh = page == QLatin1String("mesh");
        if (assets || texmesh) assets_->setSuite(page);
        const int next = home ? 0 : trainz ? 2 : engine ? 3 : (assets || texmesh) ? 4 : sounds ? 5 : mesh ? 6 : 1;
        const int prev = stack_->currentIndex();
        QPixmap snap;
        if (prev != next && (prev == 0 || next == 0) && stack_->currentWidget())
            snap = stack_->currentWidget()->grab();
        stack_->setCurrentIndex(next);
        if (!snap.isNull()) fade_out(snap);
        blank_->setText(page);
        bridge_->set_title(home ? QStringLiteral("Trainz Studio") : engine ? QStringLiteral("Engine Tuner") : assets ? QStringLiteral("Assets Tools") : texmesh ? QStringLiteral("Texture & Mesh Lods") : sounds ? QStringLiteral("Sounds Studio") : mesh ? QStringLiteral("Mesh Studio") : page);
        hide_menu();
    });
    connect(bridge_, &ShellBridge::menuRequested, this, &ShellWindow::show_menu);
    connect(bridge_, &ShellBridge::menuDismiss, this, &ShellWindow::hide_menu);
    connect(bridge_, &ShellBridge::closeRequested, this, &QWidget::close);
    connect(bridge_, &ShellBridge::minRequested, this, [this] {
        hide_menu();
        showMinimized();
    });
    connect(bridge_, &ShellBridge::zoomRequested, this, [this] {
        hide_menu();
        isMaximized() ? showNormal() : showMaximized();
    });
    connect(bridge_, &ShellBridge::moveRequested, this, &ShellWindow::begin_move);
    boot_stage(QStringLiteral("Ready"), 100);
}

QQuickWidget* ShellWindow::load_quick(const QString& file, bool translucent) {
    auto* view = new QQuickWidget(this);
    view->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    if (translucent) {
        view->setClearColor(Qt::transparent);
        view->setAttribute(Qt::WA_TranslucentBackground, true);
        view->setAttribute(Qt::WA_AlwaysStackOnTop, false);
    } else {
        view->setClearColor(QColor(QStringLiteral("#12161c")));
        view->setAttribute(Qt::WA_OpaquePaintEvent, true);
    }
    view->setSource(QUrl::fromLocalFile(qml_dir() + QLatin1Char('/') + file));
    return view;
}

void ShellWindow::fill_menu(const QString& key) {
    QVariantList rows;
    if (key == QLatin1String("file")) {
        rows << item(QStringLiteral("quit"), QStringLiteral("Quit"));
    } else if (key == QLatin1String("view")) {
        rows << item(QStringLiteral("home"), QStringLiteral("Home"));
        rows << item(QStringLiteral("mesh"), QStringLiteral("Mesh Studio"));
        rows << item(QStringLiteral("sounds"), QStringLiteral("Sounds Studio"));
        rows << item(QStringLiteral("engine"), QStringLiteral("Engine Tuner"));
        rows << item(QStringLiteral("assets"), QStringLiteral("Assets Tools"));
        rows << item(QStringLiteral("texmesh"), QStringLiteral("Texture & Mesh Lods"));
        rows << item(QStringLiteral("trainzutil"), QStringLiteral("TrainzUtil"));
    } else {
        rows << item(QString(), QStringLiteral("Later"), false);
    }
    bridge_->set_items(rows);
}

void ShellWindow::fade_out(const QPixmap& snap) {
    if (!cover_) {
        cover_ = new QLabel(stack_);
        cover_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
        auto* effect = new QGraphicsOpacityEffect(cover_);
        cover_->setGraphicsEffect(effect);
        fade_ = new QPropertyAnimation(effect, "opacity", this);
        fade_->setDuration(180);
        fade_->setEasingCurve(QEasingCurve::OutCubic);
        connect(fade_, &QPropertyAnimation::finished, this, [this] {
            if (cover_) cover_->hide();
        });
    }
    cover_->setPixmap(snap);
    cover_->setScaledContents(true);
    cover_->setGeometry(stack_->rect());
    cover_->show();
    cover_->raise();
    auto* effect = static_cast<QGraphicsOpacityEffect*>(cover_->graphicsEffect());
    fade_->stop();
    effect->setOpacity(1);
    fade_->setStartValue(1.0);
    fade_->setEndValue(0.0);
    fade_->start();
}

void ShellWindow::hide_menu() {
    if (!menu_ || !menu_->isVisible()) {
        if (bridge_ && !bridge_->openKey().isEmpty()) bridge_->set_open_key({});
        return;
    }
    menu_->hide();
    if (bridge_) bridge_->set_open_key({});
}

void ShellWindow::begin_move() {
    if (moving_) return;
    moving_ = true;
    hide_menu();
    if (isMaximized()) {
        const QPoint cursor = QCursor::pos();
        const QRect frame = frameGeometry();
        const int span = qMax(1, frame.width());
        const int local_x = cursor.x() - frame.x();
        showNormal();
        move(cursor.x() - width() * local_x / span, qMax(frame.top(), cursor.y() - 20));
    }
    if (windowHandle()) windowHandle()->startSystemMove();
}

void ShellWindow::show_menu(const QString& key, int x, int y) {
    if (bridge_->openKey() == key && menu_->isVisible()) {
        hide_menu();
        return;
    }
    fill_menu(key);
    bridge_->set_open_key(key);
    const int rows = bridge_->items().size();
    menu_->resize(260, rows * 32 + 24);
    menu_->move(x, y);
    menu_->show();
    menu_->raise();
    bridge_->bump_menu();
}

bool ShellWindow::qmlReady() const {
    const auto ready = [](const QQuickWidget* view) { return view && view->status() == QQuickWidget::Ready; };
    return ready(home_) && ready(title_) && ready(menu_);
}

QString ShellWindow::page() const { return bridge_->page(); }

QStringList ShellWindow::qmlErrors() const {
    QStringList lines;
    const auto collect = [&](const QQuickWidget* view) {
        if (!view) return;
        for (const QQmlError& error : view->errors()) lines << error.toString();
    };
    collect(home_);
    collect(title_);
    collect(menu_);
    return lines;
}

bool ShellWindow::eventFilter(QObject* watched, QEvent* event) {
    Q_UNUSED(watched);
    if (event->type() == QEvent::MouseButtonRelease) moving_ = false;
    if (!menu_ || !menu_->isVisible()) return false;
    if (event->type() == QEvent::KeyPress) {
        const auto* key = static_cast<QKeyEvent*>(event);
        if (key->key() == Qt::Key_Escape) {
            hide_menu();
            return true;
        }
        return false;
    }
    if (event->type() != QEvent::MouseButtonPress) return false;
    const auto* mouse = static_cast<QMouseEvent*>(event);
    if (mouse->button() != Qt::LeftButton) return false;
    const QPoint global = mouse->globalPosition().toPoint();
    const QRect menu_rect(menu_->mapToGlobal(QPoint(0, 0)), menu_->size());
    const QRect title_rect(title_->mapToGlobal(QPoint(0, 0)), title_->size());
    if (!chrome_click_dismisses_menu(menu_rect, title_rect, global)) return false;
    hide_menu();
    return false;
}

void ShellWindow::changeEvent(QEvent* event) {
    if (event->type() == QEvent::WindowStateChange && bridge_) bridge_->set_zoomed(isMaximized());
    QWidget::changeEvent(event);
}

bool ShellWindow::nativeEvent(const QByteArray& eventType, void* message, qintptr* result) {
#ifdef Q_OS_WIN
    if ((eventType == "windows_generic_MSG" || eventType == "windows_dispatcher_MSG") && message) {
        const auto* msg = static_cast<MSG*>(message);
        if (msg->message == WM_EXITSIZEMOVE) {
            moving_ = false;
            if (isMaximized()) return QWidget::nativeEvent(eventType, message, result);
            const QPoint cursor = QCursor::pos();
            QScreen* screen = QGuiApplication::screenAt(cursor);
            if (!screen && windowHandle()) screen = windowHandle()->screen();
            if (screen && cursor.y() <= screen->geometry().top() + 1) showMaximized();
        }
    }
#else
    Q_UNUSED(eventType);
    Q_UNUSED(message);
#endif
    return QWidget::nativeEvent(eventType, message, result);
}

void ShellWindow::openStudio(const QString& studio_id) { bridge_->openStudio(studio_id); }

void ShellWindow::triggerItem(const QString& act_id) { bridge_->triggerItem(act_id); }
