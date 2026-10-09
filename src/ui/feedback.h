#pragma once

#include <QAbstractScrollArea>
#include <QApplication>
#include <QDragEnterEvent>
#include <QFileInfo>
#include <QMimeData>
#include <QPainter>
#include <QPointer>
#include <QStringList>
#include <QUrl>

#include "ui/status_hub.h"

// Orange dashed frame over whichever widget drop target the cursor is dragging files over.
// QML pages use DropZone.qml for the same look.
class DropHighlight : public QObject {
public:
    using QObject::QObject;

protected:
    bool eventFilter(QObject* watched, QEvent* event) override {
        const QEvent::Type type = event->type();
        if (type == QEvent::DragEnter) {
            auto* widget = qobject_cast<QWidget*>(watched);
            const auto* drag = static_cast<QDragEnterEvent*>(event);
            if (widget && widget->acceptDrops() && drag->mimeData()->hasUrls()) show_on(widget);
        } else if (type == QEvent::Drop && watched == target_) {
            QStringList paths;
            for (const QUrl& url : static_cast<QDropEvent*>(event)->mimeData()->urls()) paths << url.toString();
            hide();
            StatusHub::instance()->drop(paths);
        } else if (type == QEvent::DragLeave || type == QEvent::Drop) {
            if (watched == target_) hide();
        }
        return false;
    }

private:
    class Frame : public QWidget {
    public:
        using QWidget::QWidget;

    protected:
        void paintEvent(QPaintEvent*) override {
            QPainter painter(this);
            painter.setRenderHint(QPainter::Antialiasing);
            painter.fillRect(rect(), QColor(255, 90, 31, 28));
            QPen pen(QColor(QStringLiteral("#ff5a1f")), 2, Qt::DashLine);
            painter.setPen(pen);
            painter.drawRoundedRect(QRectF(rect()).adjusted(2, 2, -2, -2), 8, 8);
        }
    };

    void show_on(QWidget* widget) {
        // Scroll-area viewports receive the drag; outline the whole table instead.
        if (auto* area = qobject_cast<QAbstractScrollArea*>(widget->parentWidget()); area && area->viewport() == widget) widget = area;
        hide();
        target_ = widget;
        frame_ = new Frame(widget);
        frame_->setAttribute(Qt::WA_TransparentForMouseEvents);
        frame_->setGeometry(widget->rect());
        frame_->raise();
        frame_->show();
    }
    void hide() {
        if (frame_) {
            frame_->hide();
            frame_->deleteLater();
        }
        frame_ = nullptr;
        target_ = nullptr;
    }

    QPointer<QWidget> target_;
    QPointer<Frame> frame_;
};

// Glass progress chip under the title bar (StatusHub), closed with "Done" on scope exit.
// ponytail: the work stays on the UI thread, so the chip only repaints between step() calls
// (one big readAll still pauses it, but with the file name on screen). Upgrade: run the parse in a QThread and post step() back.
class BusyToast {
public:
    BusyToast(const QStringList& paths, const QString& title) : title_(title), total_(static_cast<int>(paths.size())) {
        if (!worth_showing(paths)) return;
        on_ = true;
        StatusHub::instance()->progress(title_, 0);
        QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    }
    ~BusyToast() {
        if (on_) StatusHub::instance()->finish(last_);
    }
    void step(const QString& text, int done) {
        if (!on_) return;
        last_ = text;
        StatusHub::instance()->progress(title_, total_ > 0 ? qMin(99, done * 100 / total_) : 0, text);
        QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    }

private:
    static bool worth_showing(const QStringList& paths) {
        if (paths.size() > 3) return true;
        for (const QString& path : paths) {
            const QFileInfo info(QUrl(path).isLocalFile() ? QUrl(path).toLocalFile() : path);
            if (info.isDir() || info.size() > 8 * 1024 * 1024) return true;
        }
        return false;
    }

    QString title_;
    QString last_;
    int total_ = 0;
    bool on_ = false;
};
