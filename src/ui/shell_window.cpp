#include "shell_window.h"
#include "res_path.h"

#include "assets_page.h"
#include "engine_page.h"
#include "mesh_page.h"
#include "sounds_page.h"
#include "trainzutil_page.h"

#include "crash_report.h"
#include "i18n.h"
#include "icons.h"
#include "status_hub.h"

#include <QApplication>
#include <QColor>
#include <QCoreApplication>
#include <QCursor>
#include <QCloseEvent>
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
#include <QQuickWindow>
#include <QQuickWidget>
#include <QSGRendererInterface>
#include <QScreen>
#include <QStackedWidget>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QUrl>
#include <QKeySequence>
#include <QMessageBox>
#include <QSettings>
#include <QShortcut>
#include <QSurfaceFormat>
#include <QTimer>
#include <QVBoxLayout>
#include <QWindow>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {

QVariantMap item(const QString& id, const QString& label, bool alive = true, const QString& shortcut = {}, bool checked = false) {
    QVariantMap row;
    row.insert(QStringLiteral("actId"), id);
    row.insert(QStringLiteral("label"), label);
    row.insert(QStringLiteral("shortcut"), shortcut);
    row.insert(QStringLiteral("sep"), false);
    row.insert(QStringLiteral("checked"), checked);
    row.insert(QStringLiteral("alive"), alive);
    return row;
}

QVariantMap sep() {
    QVariantMap row = item(QString(), QString(), false);
    row.insert(QStringLiteral("sep"), true);
    return row;
}

// File/Edit verbs per studio → action id run on that page's bridge.
// call:<Q_INVOKABLE ()>  ·  click:<MeshBridge::clickId id>  ·  home:open (route by file type).
QString page_verb(const QString& page, const QString& verb) {
    static const QHash<QString, QHash<QString, QString>> table = {
        {QStringLiteral("home"), {{QStringLiteral("open"), QStringLiteral("home:open")}}},
        {QStringLiteral("mesh"), {{QStringLiteral("open"), QStringLiteral("click:open")}, {QStringLiteral("save"), QStringLiteral("click:save")}, {QStringLiteral("saveAs"), QStringLiteral("click:saveAs")}}},
        {QStringLiteral("sounds"), {{QStringLiteral("open"), QStringLiteral("call:browse")}, {QStringLiteral("saveAs"), QStringLiteral("call:saveAs")}}},
        {QStringLiteral("engine"), {{QStringLiteral("open"), QStringLiteral("call:openFile")}, {QStringLiteral("save"), QStringLiteral("call:saveFile")}, {QStringLiteral("saveAs"), QStringLiteral("call:saveFileAs")}, {QStringLiteral("undo"), QStringLiteral("call:undoEdit")}, {QStringLiteral("redo"), QStringLiteral("call:redoEdit")}}},
        {QStringLiteral("assets"), {{QStringLiteral("open"), QStringLiteral("call:openFolder")}, {QStringLiteral("save"), QStringLiteral("call:viewerSave")}}},
        {QStringLiteral("texmesh"), {{QStringLiteral("open"), QStringLiteral("call:openFolder")}, {QStringLiteral("undo"), QStringLiteral("call:undoEdit")}, {QStringLiteral("redo"), QStringLiteral("call:redoEdit")}}},
        {QStringLiteral("trainzutil"), {{QStringLiteral("open"), QStringLiteral("call:addFiles")}}},
    };
    return table.value(page).value(verb);
}

QSettings studio_settings() { return QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")); }

QString qml_dir() {
return res_qml_dir();
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
        {QStringLiteral("theme"), QStringLiteral("Theme")},
        {QStringLiteral("lang"), QStringLiteral("Lang")},
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

bool ShellBridge::dark() const { return ui_dark(); }

void ShellBridge::set_dark(bool dark) { UiTheme::instance()->set_dark(dark); }

void ShellBridge::bump_menu() {
    ++menu_gen_;
    emit menuOpened();
}

void ShellBridge::openStudio(const QString& studio_id) {
    set_page(studio_id);
}

void ShellBridge::dropUrls(const QVariantList& urls) { emit filesDropped(urls); }

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
    else if (act_id.contains(QLatin1Char(':'))) emit actionRequested(act_id);
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
    // Desktop GL for the mesh view. Quick stays on the software scene graph:
    // a D3D QQuickWidget in the same HWND paints its transparent center black
    // and hides the QOpenGLWidget underneath.
    QSurfaceFormat fmt;
    fmt.setDepthBufferSize(24);
    fmt.setVersion(3, 3);
    fmt.setProfile(QSurfaceFormat::CoreProfile);
    QSurfaceFormat::setDefaultFormat(fmt);
    QCoreApplication::setAttribute(Qt::AA_UseDesktopOpenGL);
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    qputenv("QSG_RHI_BACKEND", "software");
}

void ShellWindow::boot_stage(const QString& text, int pct) {
    if (boot_) boot_(text, pct);
}

ShellWindow::~ShellWindow() {
    UiLang::instance()->flush_harvest();
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
    boot_stage(QStringLiteral("Loading language catalog"), 16);
    UiLang::instance();
    boot_stage(QStringLiteral("Loading Material Icons font"), 20);
    load_material_icons();
    boot_stage(QStringLiteral("Building title bar (TitleBar.qml)"), 24);
    title_ = load_quick(QStringLiteral("TitleBar.qml"), true);
    boot_stage(QStringLiteral("Building home page (HomePage.qml)"), 28);
    home_ = load_quick(QStringLiteral("HomePage.qml"), false);
    home_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    boot_stage(QStringLiteral("Building menu dropdown (MenuDrop.qml)"), 32);
    menu_ = load_quick(QStringLiteral("MenuDrop.qml"), true);
    // Tool, not Popup: Popup on this frameless host never took the mouse grab, so the menu stayed up.
    menu_->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint | Qt::WindowStaysOnTopHint | Qt::WindowDoesNotAcceptFocus);
    menu_->setAttribute(Qt::WA_TranslucentBackground, true);
    menu_->setAttribute(Qt::WA_ShowWithoutActivating, true);
    menu_->hide();
    boot_stage(QStringLiteral("Building status toast (Toast.qml)"), 35);
    toast_ = load_quick(QStringLiteral("Toast.qml"), true);
    // Own tool window like the menu: a translucent child over the GL mesh view paints black.
    toast_->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint | Qt::WindowDoesNotAcceptFocus | Qt::WindowTransparentForInput);
    toast_->setAttribute(Qt::WA_TranslucentBackground, true);
    toast_->setAttribute(Qt::WA_ShowWithoutActivating, true);
    toast_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    toast_->hide();
    boot_stage(QStringLiteral("Building status bar (StatusBar.qml)"), 38);
    footer_ = load_quick(QStringLiteral("StatusBar.qml"), false);
    footer_->setFixedHeight(30);
    qApp->installEventFilter(this);

    blank_ = new QLabel(QStringLiteral("Home"));
    blank_->setAlignment(Qt::AlignCenter);
    apply_themed_qss(blank_, QStringLiteral("background:#12161c;color:#f2f4f8;font-size:28px;"));

    stack_ = new QStackedWidget(this);
    stack_->addWidget(home_);
    stack_->addWidget(blank_);
    slot_trainz_ = new QWidget(this);
    slot_engine_ = new QWidget(this);
    slot_assets_ = new QWidget(this);
    slot_sounds_ = new QWidget(this);
    slot_mesh_ = new QWidget(this);
    stack_->addWidget(slot_trainz_);
    stack_->addWidget(slot_engine_);
    stack_->addWidget(slot_assets_);
    stack_->addWidget(slot_sounds_);
    stack_->addWidget(slot_mesh_);
    boot_stage(QStringLiteral("Assembling window layout, menus and shortcuts"), 94);

    title_->setFixedHeight(60);
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    layout->addWidget(title_);
    layout->addWidget(stack_, 1);
    layout->addWidget(footer_);

    StatusHub* hub = StatusHub::instance();
    connect(hub, &StatusHub::toastChanged, this, [this, hub] {
        if (hub->toastShown()) {
            place_toast();
            if (!toast_->isVisible() && isVisible() && !isMinimized()) toast_->show();
            toast_->raise();
            return;
        }
        QTimer::singleShot(240, toast_, [this, hub] {
            if (!hub->toastShown()) toast_->hide();
        });
    });
    connect(hub, &StatusHub::logRequested, this, [hub] {
        const QStringList lines = hub->history();
        show_crash_dialog(QStringLiteral("Status log"), QStringLiteral("Recent status messages this session · %1 lines").arg(lines.size()),
                          lines.isEmpty() ? QStringLiteral("(empty)") : lines.join(QLatin1Char('\n')), QStringLiteral("log"));
    });
    connect(hub, &StatusHub::veRequested, this, [this] { run_ve(QStringLiteral("last")); });

    connect(bridge_, &ShellBridge::pageChanged, this, [this](const QString& page) {
        const bool home = page == QLatin1String("home");
        const bool trainz = page == QLatin1String("trainzutil");
        const bool engine = page == QLatin1String("engine");
        const bool assets = page == QLatin1String("assets");
        const bool texmesh = page == QLatin1String("texmesh");
        const bool sounds = page == QLatin1String("sounds");
        const bool mesh = page == QLatin1String("mesh");
        ensure_studio(page);
        if (assets || texmesh) assets_->setSuite(page);
        const int next = home ? 0 : trainz ? 2 : engine ? 3 : (assets || texmesh) ? 4 : sounds ? 5 : mesh ? 6 : 1;
        const int prev = stack_->currentIndex();
        QPixmap snap;
        if (prev != next && (prev == 0 || next == 0) && stack_->currentWidget())
            snap = stack_->currentWidget()->grab();
        stack_->setCurrentIndex(next);
        if (!snap.isNull()) fade_out(snap);
        if (UiLang::instance()->lang() != QLatin1String("en")) retranslate_widgets(stack_->currentWidget());
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
    connect(bridge_, &ShellBridge::actionRequested, this, &ShellWindow::run_action);
    connect(bridge_, &ShellBridge::filesDropped, this, [this](const QVariantList& urls) {
        QStringList paths;
        for (const QVariant& value : urls) {
            const QUrl url(value.toString());
            const QString path = url.isLocalFile() ? url.toLocalFile() : value.toString();
            if (!path.isEmpty()) paths << path;
        }
        open_paths(paths);
    });
    connect(UiTheme::instance(), &UiTheme::changed, bridge_, &ShellBridge::changed);
    connect(UiTheme::instance(), &UiTheme::changed, this, [this] {
        const QColor clear(ui_dark() ? QStringLiteral("#12161c") : QStringLiteral("#e9edf2"));
        QPalette pal = palette();
        pal.setColor(QPalette::Window, clear);
        setPalette(pal);
        setAutoFillBackground(true);
        update();
        for (QQuickWidget* view : findChildren<QQuickWidget*>()) {
            if (view->quickWindow() && view->quickWindow()->color().alpha() == 255) view->setClearColor(clear);
        }
    });
    bridge_->set_dark(studio_settings().value(QStringLiteral("ui/theme")).toString() != QLatin1String("light"));

    // Window-wide so they fire over the QQuickWidget pages; focused QML text fields still keep their own Ctrl+Z.
    const QList<QPair<QKeySequence, QString>> keys = {
        {QKeySequence(QStringLiteral("Ctrl+O")), QStringLiteral("verb:open")},
        {QKeySequence(QStringLiteral("Ctrl+S")), QStringLiteral("verb:save")},
        {QKeySequence(QStringLiteral("Ctrl+Shift+S")), QStringLiteral("verb:saveAs")},
        {QKeySequence(QStringLiteral("Ctrl+Z")), QStringLiteral("verb:undo")},
        {QKeySequence(QStringLiteral("Ctrl+Y")), QStringLiteral("verb:redo")},
        {QKeySequence(QStringLiteral("Ctrl+Shift+Z")), QStringLiteral("verb:redo")},
        {QKeySequence(QStringLiteral("Ctrl+T")), QStringLiteral("theme:toggle")},
        {QKeySequence(QStringLiteral("Ctrl+L")), QStringLiteral("app:log")},
        {QKeySequence(QStringLiteral("Ctrl+Shift+V")), QStringLiteral("ve:current")},
        {QKeySequence(QStringLiteral("Ctrl+Shift+R")), QStringLiteral("ve:folder")},
    };
    for (const auto& key : keys) {
        auto* shortcut = new QShortcut(key.first, this);
        const QString act = key.second;
        // Save has to reach the focused editor. Other keys stay window-wide so text fields keep Ctrl+Z.
        shortcut->setContext(act == QLatin1String("verb:save") ? Qt::ApplicationShortcut : Qt::WindowShortcut);
        connect(shortcut, &QShortcut::activated, this, [this, act] { run_action(act); });
    }
    auto* quit = new QShortcut(QKeySequence(QStringLiteral("Ctrl+Q")), this);
    connect(quit, &QShortcut::activated, this, &QWidget::close);
    auto* settings = new QShortcut(QKeySequence(QStringLiteral("Ctrl+,")), this);
    connect(settings, &QShortcut::activated, this, [this] {
        if (bridge_->page() == QLatin1String("mesh")) run_action(QStringLiteral("setpage:settings"));
    });
    boot_stage(QStringLiteral("Ready — opening window"), 100);
}

void ShellWindow::ensure_studio(const QString& page) {
    if (page == QLatin1String("trainzutil")) studio_trainz();
    else if (page == QLatin1String("engine")) studio_engine();
    else if (page == QLatin1String("assets") || page == QLatin1String("texmesh")) studio_assets();
    else if (page == QLatin1String("sounds")) studio_sounds();
    else if (page == QLatin1String("mesh")) studio_mesh();
}

void ShellWindow::take_slot(QWidget*& slot, QWidget* page) {
    const int index = stack_->indexOf(slot);
    stack_->removeWidget(slot);
    slot->deleteLater();
    slot = nullptr;
    stack_->insertWidget(index, page);
    for (QObject* child : page->children()) {
        if (QByteArray(child->metaObject()->className()).endsWith("Bridge"))
            connect(UiTheme::instance(), SIGNAL(changed()), child, SIGNAL(changed()));
    }
}

TrainzUtilPage* ShellWindow::studio_trainz() {
    if (trainz_) return trainz_;
    trainz_ = new TrainzUtilPage(this);
    connect(trainz_, &TrainzUtilPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    connect(trainz_, &TrainzUtilPage::engineRequested, this, [this](const QString& kuid, const QString& text, const QString&) {
        engine_kuid_ = kuid;
        studio_engine()->loadCdpText(text);
        bridge_->set_page(QStringLiteral("engine"));
    });
    connect(trainz_, &TrainzUtilPage::sceneRequested, this, [this](const QStringList& paths, const QStringList& labels, const QList<double>& yaws) {
        // Switch first so Mesh Studio's load sheet (Mesh i / n) is visible while the scene builds.
        bridge_->set_page(QStringLiteral("mesh"));
        QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
        studio_mesh()->loadScene(paths, labels, yaws);
    });
    connect(trainz_, &TrainzUtilPage::packagesRequested, this, [this](const QString& folder) {
        bridge_->set_page(QStringLiteral("assets"));
        studio_assets()->setPage(QStringLiteral("packages"));
        if (!folder.isEmpty()) studio_assets()->openPaths({folder});
    });
    take_slot(slot_trainz_, trainz_);
    return trainz_;
}

EngineTunerPage* ShellWindow::studio_engine() {
    if (engine_) return engine_;
    engine_ = new EngineTunerPage(this);
    connect(engine_, &EngineTunerPage::homeRequested, this, [this] {
        if (!engine_kuid_.isEmpty()) {
            engine_kuid_.clear();
            bridge_->set_page(QStringLiteral("trainzutil"));
            return;
        }
        bridge_->set_page(engine_->cdpSession() ? QStringLiteral("assets") : QStringLiteral("home"));
    });
    connect(engine_, &EngineTunerPage::cdpSaveRequested, this, [this](const QString& text) {
        if (!engine_kuid_.isEmpty()) {
            studio_trainz()->commit_enginespec(engine_kuid_, text);
            engine_kuid_.clear();
            bridge_->set_page(QStringLiteral("trainzutil"));
            return;
        }
        studio_assets()->applyEngineText(text);
        bridge_->set_page(QStringLiteral("assets"));
    });
    take_slot(slot_engine_, engine_);
    return engine_;
}

AssetsPage* ShellWindow::studio_assets() {
    if (assets_) return assets_;
    assets_ = new AssetsPage(this);
    connect(assets_, &AssetsPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    connect(assets_, &AssetsPage::meshRequested, this, [this](const QString& path) {
        bridge_->set_page(QStringLiteral("mesh"));
        studio_mesh()->loadFile(path);
    });
    connect(assets_, &AssetsPage::engineRequested, this, [this](const QString& text, const QString&) {
        studio_engine()->loadCdpText(text);
        bridge_->set_page(QStringLiteral("engine"));
    });
    take_slot(slot_assets_, assets_);
    return assets_;
}

SoundsPage* ShellWindow::studio_sounds() {
    if (sounds_) return sounds_;
    sounds_ = new SoundsPage(this);
    connect(sounds_, &SoundsPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    take_slot(slot_sounds_, sounds_);
    return sounds_;
}

MeshStudioPage* ShellWindow::studio_mesh() {
    if (mesh_) return mesh_;
    mesh_ = new MeshStudioPage(this);
    connect(mesh_, &MeshStudioPage::homeRequested, this, [this] { bridge_->set_page(QStringLiteral("home")); });
    take_slot(slot_mesh_, mesh_);
    return mesh_;
}

QQuickWidget* ShellWindow::load_quick(const QString& file, bool translucent) {
    auto* view = new QQuickWidget(this);
    view->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view->engine()->rootContext()->setContextProperty(QStringLiteral("hub"), StatusHub::instance());
    if (translucent) {
        view->setClearColor(Qt::transparent);
        view->setAttribute(Qt::WA_TranslucentBackground, true);
        view->setAttribute(Qt::WA_AlwaysStackOnTop, false);
    } else {
        view->setClearColor(QColor(QStringLiteral("#12161c")));
        view->setAttribute(Qt::WA_OpaquePaintEvent, true);
    }
    view->setSource(res_url(qml_dir() + QLatin1Char('/') + file));
    return view;
}

void ShellWindow::fill_menu(const QString& key) { bridge_->set_items(menuRows(key)); }

QVariantList ShellWindow::menuRows(const QString& key) {
    const QString page = bridge_->page();
    const auto verb = [&](const QString& name, const QString& label, const QString& shortcut) {
        const QString act = page_verb(page, name);
        return item(act, label, !act.isEmpty() && actionOk(act), shortcut);
    };
    QVariantList rows;
    if (key == QLatin1String("file")) {
        rows << verb(QStringLiteral("open"), QStringLiteral("Open…"), QStringLiteral("Ctrl+O"));
        if (page == QLatin1String("mesh")) {
            rows << item(QStringLiteral("call:openFixture"), QStringLiteral("Open sample mesh"), actionOk(QStringLiteral("call:openFixture")));
            rows << item(QStringLiteral("click:clearMesh"), QStringLiteral("Clear meshes"), actionOk(QStringLiteral("click:clearMesh")));
        }
        if (page == QLatin1String("trainzutil")) rows << item(QStringLiteral("call:scanLibrary"), QStringLiteral("Scan library"), actionOk(QStringLiteral("call:scanLibrary")));
        rows << sep();
        rows << verb(QStringLiteral("save"), QStringLiteral("Save"), QStringLiteral("Ctrl+S"));
        rows << verb(QStringLiteral("saveAs"), QStringLiteral("Save As…"), QStringLiteral("Ctrl+Shift+S"));
        rows << sep();
        rows << item(QStringLiteral("quit"), QStringLiteral("Quit"), true, QStringLiteral("Ctrl+Q"));
    } else if (key == QLatin1String("edit")) {
        rows << verb(QStringLiteral("undo"), QStringLiteral("Undo"), QStringLiteral("Ctrl+Z"));
        rows << verb(QStringLiteral("redo"), QStringLiteral("Redo"), QStringLiteral("Ctrl+Y"));
    } else if (key == QLatin1String("view")) {
        const QList<QPair<QString, QString>> studios = {
            {QStringLiteral("home"), QStringLiteral("Home")},
            {QStringLiteral("mesh"), QStringLiteral("Mesh Studio")},
            {QStringLiteral("sounds"), QStringLiteral("Sounds Studio")},
            {QStringLiteral("engine"), QStringLiteral("Engine Tuner")},
            {QStringLiteral("assets"), QStringLiteral("Assets Tools")},
            {QStringLiteral("texmesh"), QStringLiteral("Texture & Mesh Lods")},
            {QStringLiteral("trainzutil"), QStringLiteral("TrainzUtil")},
        };
        for (const auto& studio : studios) rows << item(studio.first, studio.second, true, {}, studio.first == page);
        if (page == QLatin1String("mesh")) {
            QObject* mesh = page_bridge();
            rows << sep();
            rows << item(QStringLiteral("click:resetCam"), QStringLiteral("Reset camera"));
            rows << item(QStringLiteral("check:face"), QStringLiteral("Face Orientation"), true, {}, mesh && mesh->property("faceOn").toBool());
            rows << item(QStringLiteral("check:ground"), QStringLiteral("Ground"), true, {}, mesh && mesh->property("groundOn").toBool());
            rows << item(QStringLiteral("setpage:settings"), QStringLiteral("Settings…"), true, QStringLiteral("Ctrl+,"));
            if (mesh && mesh->property("pbrOn").toBool()) {
                rows << sep();
                const QStringList labels = mesh->property("pbrLabels").toStringList();
                for (int i = 0; i < labels.size(); ++i)
                    rows << item(QStringLiteral("pbr:%1").arg(i), QStringLiteral("PBR ") + labels[i], true, {}, mesh->property("pbr").toInt() == i);
            }
        }
    } else if (key == QLatin1String("tools")) {
        rows << item(QStringLiteral("ve:current"), QStringLiteral("VE Rules scan current"), true, QStringLiteral("Ctrl+Shift+V"));
        rows << item(QStringLiteral("ve:folder"), QStringLiteral("VE Rules scan folder…"), true, QStringLiteral("Ctrl+Shift+R"));
        rows << item(QStringLiteral("ve:fix"), QStringLiteral("VE Rules fix current…"), true);
        rows << sep();
        rows << item(QStringLiteral("ve:last"), QStringLiteral("Show last VE report"));
        rows << item(QStringLiteral("app:log"), QStringLiteral("Status log"), true, QStringLiteral("Ctrl+L"));
    } else if (key == QLatin1String("theme")) {
        rows << item(QStringLiteral("theme:dark"), QStringLiteral("Dark"), true, {}, bridge_->dark());
        rows << item(QStringLiteral("theme:light"), QStringLiteral("Light"), true, {}, !bridge_->dark());
        rows << sep();
        rows << item(QStringLiteral("theme:toggle"), QStringLiteral("Toggle light / dark"), true, QStringLiteral("Ctrl+T"));
    } else if (key == QLatin1String("lang")) {
        const QString cur = UiLang::instance()->lang();
        for (const auto& lang : ui_languages()) rows << item(QStringLiteral("lang:") + lang.first, lang.second, true, {}, lang.first == cur);
    }
    return rows;
}

void ShellWindow::run_ve(const QString& mode) {
    StatusHub* hub = StatusHub::instance();
    if (mode == QLatin1String("last") && !ve_last_.isEmpty()) {
        show_crash_dialog(ui_tr(QStringLiteral("VE Rules")), ve_summarize(ve_last_).line, ve_format_reports(ve_last_), QStringLiteral("log"));
        return;
    }
    QStringList paths;
    if (mode == QLatin1String("folder")) {
        const QString dir = QFileDialog::getExistingDirectory(this, ui_tr(QStringLiteral("VE Rules scan folder…")));
        if (dir.isEmpty()) return;
        paths << dir;
    } else {
        QObject* target = page_bridge();
        if (target && target->metaObject()->indexOfMethod("veContextPaths()") >= 0)
            QMetaObject::invokeMethod(target, "veContextPaths", Q_RETURN_ARG(QStringList, paths));
        if (paths.isEmpty()) paths = QFileDialog::getOpenFileNames(this, ui_tr(QStringLiteral("VE Rules scan current")));
        if (paths.isEmpty()) return;
    }
    if (mode == QLatin1String("fix")) {
        const auto answer = ui_box(QMessageBox::Question, this, ui_tr(QStringLiteral("VE Rules")),
                                                  ui_tr(QStringLiteral("Apply safe VE fixes to %1 path(s)? Each changed file keeps a .bak copy.")).arg(paths.size()));
        if (answer != QMessageBox::Yes) return;
        const QList<VeFix> fixes = ve_fix_reports(ve_scan_paths(paths));
        const auto ok = std::count_if(fixes.begin(), fixes.end(), [](const VeFix& f) { return f.ok; });
        hub->notify(ok == fixes.size() ? QStringLiteral("save") : QStringLiteral("error"), ui_tr(QStringLiteral("VE Rules fix")),
                    ui_tr(QStringLiteral("%1 applied · %2 failed")).arg(ok).arg(fixes.size() - ok));
    }
    hub->progress(ui_tr(QStringLiteral("VE Rules")), 0, ui_tr(QStringLiteral("Scanning %1 path(s)…")).arg(paths.size()));
    ve_last_ = ve_scan_paths(paths);
    const VeSummary sum = ve_summarize(ve_last_);
    hub->finish(sum.line);
    hub->set_ve_state(sum.errors > 0 ? QStringLiteral("bad") : QStringLiteral("ok"));
    show_crash_dialog(ui_tr(QStringLiteral("VE Rules")), sum.line, ve_format_reports(ve_last_), QStringLiteral("log"));
}

QObject* ShellWindow::page_bridge() const {
    QWidget* page = stack_ ? stack_->currentWidget() : nullptr;
    if (!page) return nullptr;
    for (QObject* child : page->children()) {
        if (QByteArray(child->metaObject()->className()).endsWith("Bridge")) return child;
    }
    return nullptr;
}

bool ShellWindow::actionOk(const QString& act_id) const {
    QObject* target = page_bridge();
    const QMetaObject* meta = target ? target->metaObject() : nullptr;
    if (act_id.startsWith(QLatin1String("call:"))) return meta && meta->indexOfMethod((act_id.mid(5) + QStringLiteral("()")).toLatin1()) >= 0;
    if (act_id.startsWith(QLatin1String("click:"))) return meta && meta->indexOfMethod("clickId(QString)") >= 0;
    if (act_id.startsWith(QLatin1String("setpage:"))) return meta && meta->indexOfMethod("setPage(QString)") >= 0;
    return true;
}

void ShellWindow::run_action(const QString& act_id) {
    StatusHub* hub = StatusHub::instance();
    const QString arg = act_id.section(QLatin1Char(':'), 1);
    if (act_id.startsWith(QLatin1String("verb:"))) {
        const QString act = page_verb(bridge_->page(), arg);
        if (!act.isEmpty() && actionOk(act)) run_action(act);
        return;
    }
    if (!actionOk(act_id)) return;
    QObject* target = page_bridge();
    if (act_id.startsWith(QLatin1String("call:"))) QMetaObject::invokeMethod(target, arg.toLatin1().constData());
    else if (act_id.startsWith(QLatin1String("click:"))) QMetaObject::invokeMethod(target, "clickId", Q_ARG(QString, arg));
    else if (act_id.startsWith(QLatin1String("setpage:"))) QMetaObject::invokeMethod(target, "setPage", Q_ARG(QString, arg));
    else if (act_id.startsWith(QLatin1String("check:")) && target) QMetaObject::invokeMethod(target, "setChecked", Q_ARG(QString, arg), Q_ARG(bool, !target->property((arg + QStringLiteral("On")).toLatin1()).toBool()));
    else if (act_id.startsWith(QLatin1String("pbr:")) && target) QMetaObject::invokeMethod(target, "setPbr", Q_ARG(int, arg.toInt()));
    else if (act_id == QLatin1String("home:open")) open_any();
    else if (act_id == QLatin1String("app:log")) hub->openLog();
    else if (act_id.startsWith(QLatin1String("ve:"))) run_ve(arg);
    else if (act_id.startsWith(QLatin1String("theme:"))) {
        const bool dark = arg == QLatin1String("toggle") ? !bridge_->dark() : arg == QLatin1String("dark");
        bridge_->set_dark(dark);
        studio_settings().setValue(QStringLiteral("ui/theme"), dark ? QStringLiteral("dark") : QStringLiteral("light"));
        hub->notify(QStringLiteral("info"), dark ? QStringLiteral("Dark theme") : QStringLiteral("Light theme"));
    } else if (act_id.startsWith(QLatin1String("lang:"))) {
        UiLang::instance()->set_lang(arg);
        for (const auto& lang : ui_languages()) {
            if (lang.first == arg) hub->notify(QStringLiteral("info"), lang.second);
        }
    }
}

void ShellWindow::open_any() {
    const QString path = QFileDialog::getOpenFileName(this, QStringLiteral("Open"), {}, QStringLiteral("Trainz files (*.trainzmesh *.im *.fbx *.wav *.cdp *.zip *.txt);;All files (*)"));
    if (!path.isEmpty()) open_paths({path});
}

void ShellWindow::open_paths(const QStringList& paths) {
    QStringList meshes;
    QStringList packs;
    QString wav;
    QString text;
    for (const QString& path : paths) {
        if (path.isEmpty()) continue;
        const QString ext = QFileInfo(path).suffix().toLower();
        if (ext == QLatin1String("trainzmesh") || ext == QLatin1String("im") || ext == QLatin1String("fbx")) meshes << path;
        else if (ext == QLatin1String("cdp") || ext == QLatin1String("zip") || ext == QLatin1String("tzarc")) packs << path;
        else if (ext == QLatin1String("wav")) {
            if (wav.isEmpty()) wav = path;
        } else if (text.isEmpty()) text = path;
    }
    if (!meshes.isEmpty()) {
        bridge_->set_page(QStringLiteral("mesh"));
        if (meshes.size() == 1) {
            studio_mesh()->loadFile(meshes.first());
            return;
        }
        QStringList labels;
        for (const QString& path : meshes) labels << QFileInfo(path).fileName();
        studio_mesh()->loadScene(meshes, labels, {});
        return;
    }
    if (!packs.isEmpty()) {
        bridge_->set_page(QStringLiteral("assets"));
        studio_assets()->openPaths(packs);
        return;
    }
    const QString path = !wav.isEmpty() ? wav : text;
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        post_status(QStringLiteral("Could not open ") + QFileInfo(path).fileName());
        return;
    }
    if (!wav.isEmpty()) {
        bridge_->set_page(QStringLiteral("sounds"));
        studio_sounds()->loadBytes(file.readAll(), wav);
        return;
    }
    bridge_->set_page(QStringLiteral("engine"));
    studio_engine()->loadText(QString::fromUtf8(file.readAll()));
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

void ShellWindow::place_toast() {
    // Hang 6 px under the title capsule (60 px strip, capsule bottom margin 14).
    constexpr int w = 480;
    constexpr int h = 96;
    const QPoint anchor = title_->mapToGlobal(QPoint(title_->width() / 2, title_->height() - 14 + 6));
    toast_->setGeometry(anchor.x() - w / 2, anchor.y(), w, h);
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
    int height = 12;
    for (const QVariant& row : bridge_->items()) height += row.toMap().value(QStringLiteral("sep")).toBool() ? 11 : 34;
    menu_->resize(key == QLatin1String("view") || key == QLatin1String("tools") ? 290 : 260, height);
    menu_->move(x, y);
    menu_->show();
    menu_->raise();
    bridge_->bump_menu();
}

bool ShellWindow::qmlReady() const {
    const auto ready = [](const QQuickWidget* view) { return view && view->status() == QQuickWidget::Ready; };
    return ready(home_) && ready(title_) && ready(menu_) && ready(toast_) && ready(footer_);
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
    collect(toast_);
    collect(footer_);
    return lines;
}

bool ShellWindow::eventFilter(QObject* watched, QEvent* event) {
    if (event->type() == QEvent::MouseButtonRelease) moving_ = false;
    if (watched == this && toast_ && toast_->isVisible()) {
        if (event->type() == QEvent::Move || event->type() == QEvent::Resize) place_toast();
        else if (event->type() == QEvent::Hide) toast_->hide();
    }
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

void ShellWindow::closeEvent(QCloseEvent* event) {
    if (closing_) return QWidget::closeEvent(event);
    event->ignore();  // fade out first, then close for real
    closing_ = true;
    hide_menu();
    auto* anim = new QPropertyAnimation(this, "windowOpacity", this);
    anim->setDuration(180);
    anim->setStartValue(windowOpacity());
    anim->setEndValue(0.0);
    anim->setEasingCurve(QEasingCurve::OutCubic);
    connect(anim, &QPropertyAnimation::finished, this, &QWidget::close);
    anim->start(QAbstractAnimation::DeleteWhenStopped);
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
            if (!screen) return QWidget::nativeEvent(eventType, message, result);
            const QRect sg = screen->geometry(), ag = screen->availableGeometry();
            if (cursor.y() <= sg.top() + 1) showMaximized();
            else if (cursor.x() <= sg.left() + 1)  // Windows-style half snap
                setGeometry(ag.x(), ag.y(), ag.width() / 2, ag.height());
            else if (cursor.x() >= sg.right() - 1)
                setGeometry(ag.x() + ag.width() / 2, ag.y(), ag.width() - ag.width() / 2, ag.height());
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
