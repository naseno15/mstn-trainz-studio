#pragma once

#include <functional>

#include <QList>
#include <QObject>
#include <QString>
#include <QStringList>

bool install_ok(const QString& output);

struct InstallJob {
    QString id;
    QString path;
};

class InstallQueue : public QObject {
    Q_OBJECT

public:
    using Done = std::function<void(bool, const QString&)>;
    using Runner = std::function<void(const InstallJob&, const Done&)>;

    explicit InstallQueue(QObject* parent = nullptr);

    void set_exe(const QString& exe);
    void set_runner(Runner runner);
    void enqueue(const QList<InstallJob>& jobs);
    void stop();

    int active() const { return active_; }
    QStringList finished() const { return finished_; }
    int pending() const { return pending_.size(); }

signals:
    void jobFinished(const QString& id, bool ok, const QString& message);
    void jobLine(const QString& id, const QString& line);

private:
    void start_next();
    void finish_current(bool ok, const QString& message);

    QString exe_;
    Runner runner_;
    QList<InstallJob> pending_;
    QStringList finished_;
    QString current_;
    int active_ = 0;
    bool stopped_ = false;
    class QProcess* proc_ = nullptr;
};
