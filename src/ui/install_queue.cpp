#include "install_queue.h"

#include <memory>

#include <QFileInfo>
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

bool install_ok(const QString& output) {
    const QString low = output.toLower();
    if (low.contains(QLatin1String("not running"))) return false;
    return !low.startsWith(QLatin1String("error")) && !low.contains(QLatin1String("\nerror"));
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
    proc->setProcessChannelMode(QProcess::MergedChannels);
    const QString verb = job.path.endsWith(QStringLiteral(".cdp"), Qt::CaseInsensitive) ? QStringLiteral("installCDP")
                                                                                        : QStringLiteral("installfrompath");
    auto output = std::make_shared<QString>();
    const QString id = job.id;
    connect(proc, &QProcess::readyRead, this, [this, proc, output, id] {
        while (proc->canReadLine()) {
            const QString line = QString::fromUtf8(proc->readLine()).trimmed();
            if (line.isEmpty()) continue;
            *output += line + QLatin1Char('\n');
            emit jobLine(id, line);
        }
    });
    connect(proc, &QProcess::finished, this, [this, proc, output](int, QProcess::ExitStatus status) {
        *output += QString::fromUtf8(proc->readAll());
        proc_ = nullptr;
        proc->deleteLater();
        const QString text = output->trimmed();
        const bool ok = status == QProcess::NormalExit && install_ok(text);
        finish_current(ok, text.isEmpty() ? (ok ? QStringLiteral("Installed") : QStringLiteral("Install failed")) : text.right(400));
    });
    proc->setWorkingDirectory(QFileInfo(exe_).absolutePath());
    proc->start(exe_, {verb, job.path});
}

void InstallQueue::finish_current(bool ok, const QString& message) {
    if (active_ == 0) return;
    const QString id = current_;
    active_ = 0;
    finished_ << current_;
    current_.clear();
    emit jobFinished(id, ok, message);
    if (stopped_) return;
    QTimer::singleShot(0, this, [this] { start_next(); });
}
