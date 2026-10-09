#include "ui/crash_report.h"
#include "ui/feedback.h"
#include "ui/shell_window.h"

#include <QApplication>
#include <QDialog>
#include <QFrame>
#include <QLabel>
#include <QProgressBar>
#include <QVBoxLayout>

namespace {

class BootDialog : public QDialog {
public:
    BootDialog() {
        setWindowTitle(QStringLiteral("Trainz Studio"));
        setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
        setAttribute(Qt::WA_TranslucentBackground);
        setFixedSize(460, 168);

        auto* card = new QFrame(this);
        card->setObjectName(QStringLiteral("loadingCard"));
        card->setStyleSheet(QStringLiteral(
            "QFrame#loadingCard { background:#161a20; border:1px solid #3a241c; border-radius:16px; }"
            "QLabel#overlayBrand { color:#f2f4f8; font-size:22px; background:transparent; }"
            "QLabel#overlayStage { color:#c8cdd6; font-size:13px; background:transparent; }"
            "QProgressBar { background:#2a2e36; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#ff5a1f; border-radius:4px; }"));

        brand_ = new QLabel(QStringLiteral("Trainz Studio"), card);
        brand_->setObjectName(QStringLiteral("overlayBrand"));
        brand_->setAlignment(Qt::AlignCenter);
        stage_ = new QLabel(QStringLiteral("Starting…"), card);
        stage_->setObjectName(QStringLiteral("overlayStage"));
        stage_->setAlignment(Qt::AlignCenter);
        bar_ = new QProgressBar(card);
        bar_->setRange(0, 100);
        bar_->setValue(8);
        bar_->setTextVisible(false);
        bar_->setFixedHeight(8);

        auto* lay = new QVBoxLayout(card);
        lay->setContentsMargins(28, 22, 28, 18);
        lay->setSpacing(10);
        lay->addWidget(brand_);
        lay->addWidget(bar_);
        lay->addWidget(stage_);

        auto* root = new QVBoxLayout(this);
        root->setContentsMargins(0, 0, 0, 0);
        root->addWidget(card);
    }

    void set_stage(const QString& text, int pct) {
        stage_->setText(text);
        bar_->setValue(pct);
        QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    }

private:
    QLabel* brand_ = nullptr;
    QLabel* stage_ = nullptr;
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
    window.show();
    boot.close();
    if (const QString tail = previous_crash_tail(); !tail.isEmpty())
        show_crash_dialog(QStringLiteral("Trainz Studio closed unexpectedly"), QStringLiteral("The last session did not exit cleanly. The end of its log is below."), tail, QStringLiteral("warning"));
    const int code = app.exec();
    end_crash_session();
    return code;
}
