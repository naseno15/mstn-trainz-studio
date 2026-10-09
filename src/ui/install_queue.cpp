#include "install_queue.h"

#include <QProcess>
#include <QTimer>

InstallQueue::InstallQueue(QObject* parent) : QObject(parent) {}

void InstallQueue::set_exe(const QString& exe) { exe_ = exe; }

void InstallQueue::set_runner(Runner runner) { runner_ = std::move(runner); }

void InstallQueue::enqueue(const QList<InstallJob>& jobs) {
    stopped_ = false;
    pending_ += jobs;
    start_next();
}

void InstallQueue::stop() {
    stopped_ = true;
    pending_.clear();
    if (proc_) proc_->kill();
}

void InstallQueue::start_next() {
    if (stopped_ || active_ != 0 || pending_.isEmpty()) return;
    const InstallJob job = pending_.takeFirst();
    current_ = job.id;
    active_ = 1;
    if (runner_) {
        runner_(job, [this](bool ok, const QString& message) { finish_current(ok, message); });
        return;
    }
    if (exe_.isEmpty()) {
        finish_current(false, QStringLiteral("TrainzUtil not found"));
        return;
    }
    auto* proc = new QProcess(this);
    proc_ = proc;
    const QString verb = job.path.endsWith(QStringLiteral(".cdp"), Qt::CaseInsensitive) ? QStringLiteral("installCDP")
                                                                                        : QStringLiteral("installfrompath");
    connect(proc, &QProcess::finished, this, [this, proc](int, QProcess::ExitStatus) {
        proc_ = nullptr;
        proc->deleteLater();
        finish_current(true, QStringLiteral("Installed"));
    });
    proc->start(exe_, {verb, job.path});
}

void InstallQueue::finish_current(bool ok, const QString&) {
    if (active_ == 0) return;
    const QString id = current_;
    active_ = 0;
    finished_ << current_;
    current_.clear();
    emit jobFinished(id, ok);
    if (stopped_) return;
    QTimer::singleShot(0, this, [this] { start_next(); });
}
