#include "ui/crash_report.h"
#include "ui/feedback.h"
#include "ui/shell_window.h"

#include <QApplication>
#include <QDialog>
#include <QElapsedTimer>
#include <QEasingCurve>
#include <QFrame>
#include <QLabel>
#include <QProgressBar>
#include <QScreen>
#include <QThread>
#include <QVBoxLayout>

#include <windows.h>

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
        setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
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

        auto* root = new QVBoxLayout(this);
        root->setContentsMargins(0, 0, 0, 0);
        root->addWidget(card);
        if (const QScreen* screen = QGuiApplication::primaryScreen()) move(screen->availableGeometry().center() - rect().center());
    }

    void showEvent(QShowEvent* event) override {
        QDialog::showEvent(event);
        enable_acrylic(reinterpret_cast<HWND>(winId()));
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
        pump(260);
    }
    void dissolve() {
        QElapsedTimer clock;
        clock.start();
        constexpr int ms = 320;
        while (clock.elapsed() < ms) {
            setWindowOpacity(1.0 - QEasingCurve(QEasingCurve::InOutQuad).valueForProgress(double(clock.elapsed()) / ms));
            pump(8);
        }
        close();
    }

private:
    static void pump(int ms) {
        QElapsedTimer clock;
        clock.start();
        do {
            QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
            QThread::msleep(4);
        } while (clock.elapsed() < ms);
    }

    // Eased glide of bar + percent toward the target; the pause is deliberate so each step is readable.
    void glide_to(int pct) {
        const int from = bar_->value(), to = pct * 10;
        const int ms = std::clamp(180 + std::abs(to - from) * 2 / 3, 180, 520);
        QElapsedTimer clock;
        clock.start();
        const QEasingCurve curve(QEasingCurve::OutCubic);
        while (clock.elapsed() < ms) {
            const int now = from + int((to - from) * curve.valueForProgress(double(clock.elapsed()) / ms));
            bar_->setValue(now);
            pct_->setText(QStringLiteral("%1%").arg(now / 10));
            pump(8);
        }
        bar_->setValue(to);
        pct_->setText(QStringLiteral("%1%").arg(pct));
        QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
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
};

}  // namespace

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    install_crash_log();
    app.installEventFilter(new DropHighlight(&app));
    BootDialog boot;
    boot.show();
    QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    ShellWindow window(nullptr, [&boot](const QString& text, int pct) { boot.set_stage(text, pct); });
    boot.finish();
    window.showMaximized();  // fills the work area, not full screen
    boot.dissolve();
    if (const QString tail = previous_crash_tail(); !tail.isEmpty())
        show_crash_dialog(QStringLiteral("Trainz Studio closed unexpectedly"), QStringLiteral("The last session did not exit cleanly. The end of its log is below."), tail, QStringLiteral("warning"));
    const int code = app.exec();
    end_crash_session();
    return code;
}
