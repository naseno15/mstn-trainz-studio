#pragma once

#include "ui/status_hub.h"

#include <QObject>
#include <QString>

class QDialog;

// Session log + crash marker. A marker left behind by the previous run means it
// did not reach end_crash_session(), so the next launch shows CrashDialog.qml.
void install_crash_log();
void end_crash_session();
QString crash_log_path();
QString previous_crash_tail();

QDialog* make_crash_dialog(const QString& title, const QString& summary, const QString& detail, const QString& kind, bool quit_on_ok);
void show_crash_dialog(const QString& title, const QString& summary, const QString& detail, const QString& kind = QStringLiteral("error"), bool quit_on_ok = false);

class CrashBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark CONSTANT)
    Q_PROPERTY(QString kind MEMBER kind_ CONSTANT)
    Q_PROPERTY(QString title MEMBER title_ CONSTANT)
    Q_PROPERTY(QString summary MEMBER summary_ CONSTANT)
    Q_PROPERTY(QString detail MEMBER detail_ CONSTANT)
    Q_PROPERTY(QString logPath READ logPath CONSTANT)
    Q_PROPERTY(bool quitOnOk MEMBER quit_on_ok_ CONSTANT)
    Q_PROPERTY(QString copyLabel READ copyLabel NOTIFY changed)

public:
    CrashBridge(QDialog* dialog, QString title, QString summary, QString detail, QString kind, bool quit_on_ok);

    bool dark() const { return ui_dark(); }
    QString logPath() const { return crash_log_path(); }
    QString copyLabel() const { return copied_ ? QStringLiteral("Copied") : QStringLiteral("Copy"); }

    Q_INVOKABLE void openFolder();
    Q_INVOKABLE void copyError(const QString& selected);
    Q_INVOKABLE void dismiss();

signals:
    void changed();

private:
    QDialog* dialog_;
    QString title_;
    QString summary_;
    QString detail_;
    QString kind_;
    bool quit_on_ok_;
    bool copied_ = false;
};
