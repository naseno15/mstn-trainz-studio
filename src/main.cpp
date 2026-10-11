#include "ui/app_update.h"
#include "ui/crash_report.h"
#include "ui/feedback.h"
#include "ui/shell_window.h"

#include <QApplication>
#include <QCloseEvent>
#include <QDialog>
#include <QElapsedTimer>
#include <QEasingCurve>
#include <QFrame>
#include <QKeyEvent>
#include <QLabel>
#include <QMoveEvent>
#include <QProgressBar>
#include <QPushButton>
#include <QScreen>
#include <QThread>
#include <QVBoxLayout>

#include <atomic>
#include <cstdlib>
#include <thread>

#include <windows.h>

struct BootAbort {};

namespace {

// Windows acrylic (blur-behind) via the undocumented user32 call; falls back to a plain tint if missing.
void enable_acrylic(HWND hwnd) {
    struct Accent { int state; int flags; unsigned color; int anim; };
    struct Attrib { int attr; void* data; ULONG size; };
    using Fn = BOOL(WINAPI*)(HWND, Attrib*);
    const auto fn = reinterpret_cast<Fn>(reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowCompositionAttribute")));
    if (!fn) return;
    Accent accent{4 /* ACRYLICBLURBEHIND */, 2, 0x99161a20u /* AABBGGRR tint */, 0};
    Attrib attrib{19 /* WCA_ACCENT_POLICY */, &accent, sizeof(accent)};
    fn(hwnd, &attrib);
}

class BootDialog : public QDialog {
public:
    BootDialog() {
        setWindowTitle(QStringLiteral("Trainz Studio"));
        setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint);
        setAttribute(Qt::WA_TranslucentBackground);
        setFixedSize(560, 270);

        auto* card = new QFrame(this);
        card->setObjectName(QStringLiteral("loadingCard"));
        // Glass: the acrylic behind the window does the blur; the card only adds a tint, a hairline and a sheen.
        card->setStyleSheet(QStringLiteral(
            "QFrame#loadingCard { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,70), stop:0.5 rgba(40,44,58,110), stop:1 rgba(14,16,24,150));"
            " border:1px solid rgba(255,255,255,60); border-top:2px solid rgba(255,255,255,170); border-bottom:2px solid rgba(0,0,0,120); border-radius:18px; }"
            "QLabel { background:transparent; }"
            "QLabel#overlayBrand { color:#ffffff; font-size:24px; font-weight:600; }"
            "QLabel#overlayStage { color:#f2f4f8; font-size:13px; }"
            "QLabel#overlayPct { color:#ffb08f; font-size:12px; font-weight:600; }"
            "QLabel#overlayHistory { color:#9aa3b2; font-size:11px; background:rgba(0,0,0,70); border:1px solid rgba(0,0,0,110); border-bottom:1px solid rgba(255,255,255,50); border-radius:8px; padding:4px; }"
            "QProgressBar { background:rgba(0,0,0,110); border:1px solid rgba(0,0,0,150); border-bottom:1px solid rgba(255,255,255,70); border-radius:5px; }"
            "QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff5a1f, stop:1 #ffa24d); margin:1px; border-radius:4px; }"));

        brand_ = new QLabel(QStringLiteral("Trainz Studio"), card);
        brand_->setObjectName(QStringLiteral("overlayBrand"));
        brand_->setAlignment(Qt::AlignCenter);
        stage_ = new QLabel(QStringLiteral("Starting…"), card);
        stage_->setObjectName(QStringLiteral("overlayStage"));
        stage_->setAlignment(Qt::AlignCenter);
        stage_->setWordWrap(true);
        history_ = new QLabel(card);
        history_->setObjectName(QStringLiteral("overlayHistory"));
        history_->setAlignment(Qt::AlignLeft | Qt::AlignTop);
        history_->setTextFormat(Qt::RichText);
        history_->setMinimumHeight(58);
        pct_ = new QLabel(QStringLiteral("0%"), card);
        pct_->setObjectName(QStringLiteral("overlayPct"));
        pct_->setAlignment(Qt::AlignCenter);
        bar_ = new QProgressBar(card);
        bar_->setRange(0, 1000);  // tenths of a percent so the bar glides
        bar_->setTextVisible(false);
        bar_->setFixedHeight(12);

        auto* lay = new QVBoxLayout(card);
        lay->setContentsMargins(30, 24, 30, 18);
        lay->setSpacing(10);
        lay->addWidget(brand_);
        lay->addWidget(bar_);
        lay->addWidget(pct_);
        lay->addWidget(stage_);
        lay->addWidget(history_);

        close_ = new QPushButton(QStringLiteral("×"), card);
        close_->setCursor(Qt::PointingHandCursor);
        close_->setFocusPolicy(Qt::NoFocus);
        close_->setGeometry(width() - 46, 12, 28, 28);
        close_->setStyleSheet(QStringLiteral(
            "QPushButton { color:#f2f4f8; background:rgba(0,0,0,90); border:1px solid rgba(255,255,255,50); border-radius:14px; font-size:16px; font-weight:600; }"
            "QPushButton:hover { background:#ff5a1f; color:#ffffff; }"));
        connect(close_, &QPushButton::clicked, this, [this] { stop_ = true; });
        close_->raise();

        auto* root = new QVBoxLayout(this);
        root->setContentsMargins(0, 0, 0, 0);
        root->addWidget(card);
        if (const QScreen* screen = QGuiApplication::primaryScreen()) move(screen->availableGeometry().center() - rect().center());
    }

    ~BootDialog() override { stop_watch(); }

    void showEvent(QShowEvent* event) override {
        QDialog::showEvent(event);
        enable_acrylic(reinterpret_cast<HWND>(winId()));
        publish_hit();
        start_watch();
    }

    void moveEvent(QMoveEvent* event) override {
        QDialog::moveEvent(event);
        publish_hit();
    }

    void keyPressEvent(QKeyEvent* event) override {
        if (event->key() == Qt::Key_Escape) stop_ = true;
        else QDialog::keyPressEvent(event);
    }

    void closeEvent(QCloseEvent* event) override {
        if (allow_close_) {
            QDialog::closeEvent(event);
            return;
        }
        stop_ = true;
        event->ignore();
    }

    void stop_watch() {
        watch_run_ = false;
        if (watch_.joinable()) watch_.join();
    }

    void set_stage(const QString& text, int pct) {
        if (!stage_->text().isEmpty() && stage_->text() != text) done_ << stage_->text();
        while (done_.size() > 3) done_.removeFirst();
        render_history();
        stage_->setText(text);
        glide_to(pct);
    }

    // Hold the full bar for a beat, then dissolve the glass onto the freshly shown window.
    void finish() {
        if (!stage_->text().isEmpty()) done_ << stage_->text();
        while (done_.size() > 3) done_.removeFirst();
        render_history();
        stage_->setText(QStringLiteral("Ready"));
        glide_to(100);
        pump(40, true);
    }
    void dissolve() {
        QElapsedTimer clock;
        clock.start();
        constexpr int ms = 140;
        while (clock.elapsed() < ms) {
            setWindowOpacity(1.0 - QEasingCurve(QEasingCurve::InOutQuad).valueForProgress(double(clock.elapsed()) / ms));
            pump(8, false);
        }
        allow_close_ = true;
        close();
    }

private:
    void pump(int ms, bool input) {
        QElapsedTimer clock;
        clock.start();
        do {
            QApplication::processEvents(input ? QEventLoop::AllEvents : QEventLoop::ExcludeUserInputEvents);
            if (stop_) throw BootAbort{};
            QThread::msleep(4);
        } while (clock.elapsed() < ms);
    }

    // Eased glide of bar + percent toward the target; the pause is deliberate so each step is readable.
    void glide_to(int pct) {
        const int from = bar_->value(), to = pct * 10;
        const int ms = std::clamp(16 + std::abs(to - from) / 12, 16, 70);
        QElapsedTimer clock;
        clock.start();
        const QEasingCurve curve(QEasingCurve::OutCubic);
        while (clock.elapsed() < ms) {
            const int now = from + int((to - from) * curve.valueForProgress(double(clock.elapsed()) / ms));
            bar_->setValue(now);
            pct_->setText(QStringLiteral("%1%").arg(now / 10));
            pump(8, true);
        }
        bar_->setValue(to);
        pct_->setText(QStringLiteral("%1%").arg(pct));
        QApplication::processEvents();
        if (stop_) throw BootAbort{};
    }

    void publish_hit() {
        if (!close_) return;
        const QPoint g = close_->mapToGlobal(QPoint(0, 0));
        hit_l_ = g.x() - 8;
        hit_t_ = g.y() - 8;
        hit_r_ = g.x() + close_->width() + 8;
        hit_b_ = g.y() + close_->height() + 8;
    }

    // QML compile blocks the UI thread, so Esc, Alt+F4, and the × still have to be seen from outside the event loop.
    void start_watch() {
        if (watch_.joinable()) return;
        watch_run_ = true;
        watch_ = std::thread([this] {
            bool mouse_armed = (GetAsyncKeyState(VK_LBUTTON) & 0x8000) == 0;
            bool esc_armed = (GetAsyncKeyState(VK_ESCAPE) & 0x8000) == 0;
            bool f4_armed = (GetAsyncKeyState(VK_F4) & 0x8000) == 0;
            while (watch_run_) {
                const bool esc = (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0;
                const bool f4 = (GetAsyncKeyState(VK_F4) & 0x8000) != 0;
                const bool down = (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
                if (!esc_armed) esc_armed = !esc;
                if (!f4_armed) f4_armed = !f4;
                if (!mouse_armed) mouse_armed = !down;
                POINT cursor{};
                GetCursorPos(&cursor);
                const bool on_close = cursor.x >= hit_l_ && cursor.x < hit_r_ && cursor.y >= hit_t_ && cursor.y < hit_b_;
                if (watch_run_ && ((esc_armed && esc) || (f4_armed && f4 && (GetAsyncKeyState(VK_MENU) & 0x8000)) || (mouse_armed && down && on_close))) {
                    end_crash_session();
                    std::_Exit(0);
                }
                Sleep(16);
            }
        });
    }

    void render_history() {
        static const char* inks[] = {"#6b7280", "#8b93a1", "#aab2bf"};  // oldest dimmest
        QStringList lines;
        const int offset = 3 - int(done_.size());
        for (int i = 0; i < done_.size(); ++i) lines << QStringLiteral("<tr style='color:%1'><td>%2</td><td align='right'>✓</td></tr>").arg(QLatin1String(inks[i + offset]), done_[i].toHtmlEscaped());
        history_->setText(QStringLiteral("<table width='100%'>") + lines.join(QString()) + QStringLiteral("</table>"));
    }

    QLabel* brand_ = nullptr;
    QLabel* stage_ = nullptr;
    QLabel* history_ = nullptr;
    QLabel* pct_ = nullptr;
    QStringList done_;
    QProgressBar* bar_ = nullptr;
    QPushButton* close_ = nullptr;
    bool stop_ = false;
    bool allow_close_ = false;
    std::atomic<bool> watch_run_{false};
    std::atomic<int> hit_l_{0};
    std::atomic<int> hit_t_{0};
    std::atomic<int> hit_r_{0};
    std::atomic<int> hit_b_{0};
    std::thread watch_;
};

}  // namespace

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    apply_ui_font();
    install_crash_log();
    app.installEventFilter(new DropHighlight(&app));
    BootDialog boot;
    boot.show();
    QApplication::processEvents();
    try {
        ShellWindow window(nullptr, [&boot](const QString& text, int pct) { boot.set_stage(text, pct); });
        boot.stop_watch();
        boot.finish();
        window.showMaximized();  // fills the work area, not full screen
        boot.dissolve();
        if (const QString tail = previous_crash_tail(); !tail.isEmpty())
            show_crash_dialog(QStringLiteral("Trainz Studio closed unexpectedly"), QStringLiteral("The last session did not exit cleanly. The end of its log is below."), tail, QStringLiteral("warning"));
        start_update_check(&window);
        const int code = app.exec();
        end_crash_session();
        return code;
    } catch (const BootAbort&) {
        boot.stop_watch();
        end_crash_session();
        return 0;
    }
}
