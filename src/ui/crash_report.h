#pragma once

#include "ui/status_hub.h"

#include <QImage>
#include <QObject>
#include <QPoint>
#include <QString>

class QDialog;

// Session log + crash marker. A marker left behind by the previous run means it
// did not reach end_crash_session(), so the next launch shows CrashDialog.qml.
void install_crash_log();
void end_crash_session();
QString crash_log_path();
QString previous_crash_tail();

#include <QMessageBox>

// Every app dialog is frameless; ui_box replaces QMessageBox::warning/information/question/critical.
void make_borderless(QDialog* dialog);
QMessageBox::StandardButton ui_box(QMessageBox::Icon icon, QWidget* parent, const QString& title, const QString& text,
                                   QMessageBox::StandardButtons buttons = QMessageBox::Ok, QMessageBox::StandardButton def = QMessageBox::NoButton,
                                   bool translate = true);

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
    Q_PROPERTY(bool hasShot READ hasShot CONSTANT)
    Q_PROPERTY(int shotX READ shotX CONSTANT)
    Q_PROPERTY(int shotY READ shotY CONSTANT)
    Q_PROPERTY(int shotW READ shotW CONSTANT)
    Q_PROPERTY(int shotH READ shotH CONSTANT)

public:
    CrashBridge(QDialog* dialog, QString title, QString summary, QString detail, QString kind, bool quit_on_ok);

    bool dark() const { return ui_dark(); }
    QString logPath() const { return crash_log_path(); }
    QString copyLabel() const { return copied_ ? QStringLiteral("Copied") : QStringLiteral("Copy"); }
    bool hasShot() const { return has_shot_; }
    int shotX() const { return shot_x_; }
    int shotY() const { return shot_y_; }
    int shotW() const { return shot_w_; }
    int shotH() const { return shot_h_; }
    // Window pixels behind this sheet, in dialog coordinates. Empty grab leaves the card matte only.
    void set_backdrop(const QImage& image, const QPoint& origin);

    Q_INVOKABLE void openFolder();
    Q_INVOKABLE void openUrl(const QString& url);
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
    bool has_shot_ = false;
    int shot_x_ = 0;
    int shot_y_ = 0;
    int shot_w_ = 0;
    int shot_h_ = 0;
};
