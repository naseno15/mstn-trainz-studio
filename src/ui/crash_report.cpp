#include "ui/crash_report.h"
#include "res_path.h"
#include "shell_window.h"

#include <QApplication>
#include <QClipboard>
#include <QDateTime>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QMouseEvent>
#include <QMutex>
#include <QPointer>
#include <QScreen>
#include <QTimer>
#include <QWindow>
#include "ui/i18n.h"
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickImageProvider>
#include <QQuickWidget>
#include <QStandardPaths>
#include <QUrl>
#include <QVBoxLayout>

#include <exception>

#ifdef Q_OS_WIN
#include <windows.h>
#endif

namespace {

QString g_log_path;
QString g_marker_path;
QString g_previous_tail;
QMutex g_log_mutex;
QtMessageHandler g_prev_handler = nullptr;

QString qml_dir() {
{ const QString d = res_qml_dir(); return d.isEmpty() ? QCoreApplication::applicationDirPath() + QStringLiteral("/qml") : d; }
}

QString tail_lines(const QString& path, int count) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) return {};
    const QStringList lines = QString::fromUtf8(f.readAll()).split(QLatin1Char('\n'));
    return lines.mid(qMax(0, lines.size() - count)).join(QLatin1Char('\n')).trimmed();
}

void append_log(const QString& line) {
    QMutexLocker lock(&g_log_mutex);
    QFile f(g_log_path);
    if (!f.open(QIODevice::Append | QIODevice::Text)) return;
    f.write(QDateTime::currentDateTime().toString(Qt::ISODate).toUtf8() + ' ' + line.toUtf8() + '\n');
}

void message_handler(QtMsgType type, const QMessageLogContext& ctx, const QString& msg) {
    static const char* names[] = {"debug", "warning", "critical", "fatal", "info"};
    const char* name = type >= 0 && type <= 4 ? names[type] : "log";
    if (type != QtDebugMsg) append_log(QStringLiteral("[%1] %2%3").arg(QLatin1String(name), msg, ctx.file ? QStringLiteral(" (%1:%2)").arg(QLatin1String(ctx.file)).arg(ctx.line) : QString()));
    if (g_prev_handler) g_prev_handler(type, ctx, msg);
}

#ifdef Q_OS_WIN
wchar_t g_log_path_w[MAX_PATH * 2] = {};

// Runs inside a crashed process: Win32 calls only, no Qt, no heap.
void raw_append(const char* text) {
    HANDLE h = CreateFileW(g_log_path_w, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD n = 0;
    WriteFile(h, text, static_cast<DWORD>(lstrlenA(text)), &n, nullptr);
    CloseHandle(h);
}

LONG WINAPI seh_filter(EXCEPTION_POINTERS* info) {
    const EXCEPTION_RECORD* rec = info->ExceptionRecord;
    char module[MAX_PATH] = "?";
    HMODULE mod = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, static_cast<LPCSTR>(rec->ExceptionAddress), &mod)) GetModuleFileNameA(mod, module, MAX_PATH);
    char line[MAX_PATH + 160];
    wsprintfA(line, "[crash] exception 0x%08lX at %p in %s (offset 0x%lX)\n", rec->ExceptionCode, rec->ExceptionAddress, module, static_cast<unsigned long>(reinterpret_cast<const char*>(rec->ExceptionAddress) - reinterpret_cast<const char*>(mod)));
    raw_append(line);
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

void terminate_handler() {
    QString what = QStringLiteral("unknown exception");
    if (auto e = std::current_exception()) {
        try {
            std::rethrow_exception(e);
        } catch (const std::exception& ex) {
            what = QString::fromUtf8(ex.what());
        } catch (...) {
        }
    }
    append_log(QStringLiteral("[crash] std::terminate: ") + what);
    std::abort();
}

class DialogShot final : public QQuickImageProvider {
public:
    explicit DialogShot(QImage image) : QQuickImageProvider(Image), image_(std::move(image)) {}
    QImage requestImage(const QString&, QSize* size, const QSize&) override {
        if (size) *size = image_.size();
        return image_;
    }

private:
    QImage image_;
};

}  // namespace

QString crash_log_path() { return g_log_path; }
QString previous_crash_tail() { return g_previous_tail; }

void install_crash_log() {
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + QStringLiteral("/TrainzStudio");
    QDir().mkpath(dir);
    g_log_path = dir + QStringLiteral("/trainz_studio.log");
    g_marker_path = dir + QStringLiteral("/session.lock");
    if (QFile::exists(g_marker_path)) g_previous_tail = tail_lines(g_log_path, 80);
    // ponytail: one rotation at 1 MB; enough for a desktop tool's warnings.
    if (QFileInfo(g_log_path).size() > 1024 * 1024) {
        QFile::remove(g_log_path + QStringLiteral(".old"));
        QFile::rename(g_log_path, g_log_path + QStringLiteral(".old"));
    }
    QFile marker(g_marker_path);
    if (marker.open(QIODevice::WriteOnly)) marker.write(QByteArray::number(QCoreApplication::applicationPid()));
    append_log(QStringLiteral("[session] start"));
    g_prev_handler = qInstallMessageHandler(message_handler);
    std::set_terminate(terminate_handler);
#ifdef Q_OS_WIN
    QDir::toNativeSeparators(g_log_path).toWCharArray(g_log_path_w);
    SetUnhandledExceptionFilter(seh_filter);
#endif
}

void end_crash_session() {
    append_log(QStringLiteral("[session] clean exit"));
    QFile::remove(g_marker_path);
}

CrashBridge::CrashBridge(QDialog* dialog, QString title, QString summary, QString detail, QString kind, bool quit_on_ok)
    : QObject(dialog), dialog_(dialog), title_(std::move(title)), summary_(std::move(summary)), detail_(std::move(detail)), kind_(std::move(kind)), quit_on_ok_(quit_on_ok) {}

void CrashBridge::set_backdrop(const QImage& image, const QPoint& origin) {
    has_shot_ = !image.isNull();
    shot_x_ = origin.x();
    shot_y_ = origin.y();
    shot_w_ = image.width();
    shot_h_ = image.height();
}

void CrashBridge::openFolder() { QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(crash_log_path()).absolutePath())); }

void CrashBridge::openUrl(const QString& url) {
    const QUrl parsed(url);
    const QString scheme = parsed.scheme().toLower();
    if (scheme != QLatin1String("https") && scheme != QLatin1String("http") && scheme != QLatin1String("mailto")) return;
    QDesktopServices::openUrl(parsed);
}

void CrashBridge::copyError(const QString& selected) {
    const QString all = QStringList{title_, summary_, detail_, crash_log_path()}.join(QStringLiteral("\n\n"));
    QApplication::clipboard()->setText(selected.isEmpty() ? all : selected);
    copied_ = true;
    emit changed();
}

void CrashBridge::dismiss() {
    // Close after the click handler returns; the QML tap that called us is still on the stack.
    QPointer<QDialog> dialog = dialog_;
    const bool quit = quit_on_ok_;
    QTimer::singleShot(0, qApp, [dialog, quit] {
        if (dialog) {
            dialog->hide();  // translucent QQuickWidget windows can linger on Windows until hidden explicitly
            dialog->accept();
        }
        if (quit) QCoreApplication::quit();
    });
}

namespace {
// Drag a frameless dialog by any background press the content did not take.
class DragFilter : public QObject {
public:
    using QObject::QObject;
    bool eventFilter(QObject* obj, QEvent* event) override {
        auto* dialog = qobject_cast<QDialog*>(obj);
        if (dialog && event->type() == QEvent::MouseButtonPress && static_cast<QMouseEvent*>(event)->button() == Qt::LeftButton && dialog->windowHandle())
            dialog->windowHandle()->startSystemMove();
        return false;
    }
};
}  // namespace

void make_borderless(QDialog* dialog) {
    dialog->setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint);
    dialog->setAttribute(Qt::WA_TranslucentBackground, true);  // no grey square behind rounded corners
    dialog->installEventFilter(new DragFilter(dialog));
}

QMessageBox::StandardButton ui_box(QMessageBox::Icon icon, QWidget* parent, const QString& title, const QString& text,
                                   QMessageBox::StandardButtons buttons, QMessageBox::StandardButton def, bool translate) {
    QMessageBox box(icon, translate ? ui_tr(title) : title, translate ? ui_tr(text) : text, buttons, parent);
    make_borderless(&box);
    box.setDefaultButton(def);
    box.setStyleSheet(themed_qss(QStringLiteral(
        "QMessageBox { background:#12161c; border:1px solid #ff5a1f; border-radius:12px; }"
        "QLabel { color:#f2f4f8; font-size:13px; }"
        "QPushButton { background:#2a3140; color:#f2f4f8; border:none; border-radius:8px; padding:6px 18px; min-width:64px; }"
        "QPushButton:hover { background:#ff5a1f; }")));
    return static_cast<QMessageBox::StandardButton>(box.exec());
}

QDialog* make_crash_dialog(const QString& title, const QString& summary, const QString& detail, const QString& kind, bool quit_on_ok) {
    auto* dialog = new QDialog;
    // Full-screen translucent sheet: QML paints a soft scrim over the app and centres the card.
    // No drag filter here, so a press can never start a system move and swallow the button release.
    dialog->setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint);
    dialog->setAttribute(Qt::WA_TranslucentBackground, true);
    dialog->setWindowTitle(QStringLiteral("Trainz Studio"));
    QWidget* anchor = QApplication::activeWindow();
    const QScreen* screen = anchor && anchor->screen() ? anchor->screen() : QGuiApplication::primaryScreen();
    dialog->setGeometry(screen ? screen->availableGeometry() : QRect(0, 0, 640, 560));
    QImage shot;
    QPoint origin;
    if (anchor && anchor != dialog) {
        shot = anchor->grab().toImage();
        origin = anchor->mapToGlobal(QPoint(0, 0)) - dialog->geometry().topLeft();
    }
    auto* view = new QQuickWidget(dialog);
    auto* bridge = new CrashBridge(dialog, title, summary, detail, kind, quit_on_ok);
    bridge->set_backdrop(shot, origin);
    view->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view->setAttribute(Qt::WA_AlwaysStackOnTop, true);
    view->setClearColor(Qt::transparent);
    view->engine()->addImageProvider(QStringLiteral("dialogshot"), new DialogShot(shot));
    view->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge);
    view->setSource(res_url(qml_dir() + QStringLiteral("/CrashDialog.qml")));
    auto* lay = new QVBoxLayout(dialog);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->addWidget(view);
    return dialog;
}

void show_crash_dialog(const QString& title, const QString& summary, const QString& detail, const QString& kind, bool quit_on_ok) {
    QDialog* dialog = make_crash_dialog(title, summary, detail, kind, quit_on_ok);
    dialog->show();
    dialog->raise();
    dialog->activateWindow();  // first click must hit the button, not just activate the window
    dialog->exec();
    delete dialog;
}
