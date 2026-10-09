#pragma once

#include "ui/status_hub.h"

#include <QString>
#include <QStringList>
#include <QWidget>

#include "ui/icons.h"

#include <vector>

#include "io/wav.h"

class QPaintEvent;
class QQuickWidget;

class WaveView : public QWidget {
public:
    explicit WaveView(QWidget* parent = nullptr);
    void set_samples(const std::vector<int16_t>& samples);

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    std::vector<int16_t> samples_;
};

class SoundsBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(QString ffmpeg READ ffmpeg NOTIFY changed)
    Q_PROPERTY(QString meta READ meta NOTIFY changed)
    Q_PROPERTY(QString amp READ amp NOTIFY changed)
    Q_PROPERTY(QString qc READ qc NOTIFY changed)
#pragma push_macro("slots")
#undef slots
    Q_PROPERTY(QString slots READ slotsText NOTIFY changed)
#pragma pop_macro("slots")
    Q_PROPERTY(QString phase READ phase NOTIFY changed)
    Q_PROPERTY(QString playLabel READ playLabel NOTIFY changed)
    Q_PROPERTY(QString loopLabel READ loopLabel NOTIFY changed)
    Q_PROPERTY(QString title READ title NOTIFY changed)
    Q_PROPERTY(QString clipsTitle READ clipsTitle NOTIFY changed)
    Q_PROPERTY(QString qcTitle READ qcTitle NOTIFY changed)
    Q_PROPERTY(QString ffmpegBtn READ ffmpegBtn NOTIFY changed)
    Q_PROPERTY(QString dropHint READ dropHint NOTIFY changed)
    Q_PROPERTY(QString setA READ setA NOTIFY changed)
    Q_PROPERTY(QString setB READ setB NOTIFY changed)
    Q_PROPERTY(QString playAB READ playAbLabel NOTIFY changed)
    Q_PROPERTY(QString stopLabel READ stopLabel NOTIFY changed)
    Q_PROPERTY(QString fixLabel READ fixLabel NOTIFY changed)
    Q_PROPERTY(QString barTip READ barTip NOTIFY changed)
    Q_PROPERTY(QString homeLabel READ homeLabel NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString openGlyph READ openGlyph NOTIFY changed)
    Q_PROPERTY(QString saveGlyph READ saveGlyph NOTIFY changed)
    Q_PROPERTY(int current READ current NOTIFY changed)
    Q_PROPERTY(QStringList clips READ clips NOTIFY changed)

public:
    explicit SoundsBridge(QObject* parent = nullptr);

    bool dark() const { return ui_dark(); }
    QString ffmpeg() const { return ffmpeg_; }
    QString meta() const { return meta_; }
    QString amp() const { return amp_; }
    QString qc() const { return qc_; }
    QString slotsText() const { return slots_; }
    QString phase() const { return phase_; }
    QString playLabel() const { return play_; }
    QString loopLabel() const { return loop_; }
    QString title() const { return QStringLiteral("Sounds Studio"); }
    QString clipsTitle() const { return QStringLiteral("Clips"); }
    QString qcTitle() const { return QStringLiteral("Loop QC"); }
    QString ffmpegBtn() const { return QStringLiteral("ffmpeg…"); }
    QString dropHint() const { return QStringLiteral("Drop WAV here"); }
    QString setA() const { return QStringLiteral("Set A"); }
    QString setB() const { return QStringLiteral("Set B"); }
    QString playAbLabel() const { return QStringLiteral("Play A→B"); }
    QString stopLabel() const { return QStringLiteral("Stop"); }
    QString fixLabel() const { return QStringLiteral("Fix"); }
    QString barTip() const { return bar_tip_; }
    QString homeLabel() const { return QStringLiteral("Home"); }
    QString iconFont() const { return material_icon_family(); }
    QString openGlyph() const { return material_glyph("file_open"); }
    QString saveGlyph() const { return material_glyph("save_as"); }
    int current() const { return current_; }
    QStringList clips() const { return clips_; }
    const PcmClip& clip() const { return clip_; }

    void load_bytes(const QByteArray& bytes, const QString& path);
    bool save_as(const QString& dest);

    Q_INVOKABLE void browse();
    Q_INVOKABLE void pickFfmpeg();
    Q_INVOKABLE void selectClip(int index);
    Q_INVOKABLE void dropUrls(const QVariantList& urls);
    Q_INVOKABLE void waveRect(double x, double y, double w, double h);
    Q_INVOKABLE void setSlotA();
    Q_INVOKABLE void setSlotB();
    Q_INVOKABLE void playAB();
    Q_INVOKABLE void togglePlay();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void toggleLoop();
    Q_INVOKABLE void fix();
    Q_INVOKABLE void saveAs();
    Q_INVOKABLE void goHome();
    Q_INVOKABLE QStringList veContextPaths() const { return source_.isEmpty() ? QStringList() : QStringList{source_}; }

signals:
    void changed();
    void homeRequested();
    void waveRectRequested(int x, int y, int w, int h);

private:
    void refresh();
    PcmClip clip_;
    QString source_;
    QString ffmpeg_;
    QString meta_ = QStringLiteral("No clip");
    QString amp_ = QStringLiteral("Peak —   RMS —");
    QString qc_;
    QString slots_;
    QString phase_;
    QString play_ = QStringLiteral("Play");
    QString loop_ = QStringLiteral("Loop: Off");
    QString bar_tip_ = QStringLiteral("Save As only");
    QStringList clips_;
    int current_ = -1;
    int slot_a_ = -1;
    int slot_b_ = -1;
    bool loop_on_ = false;
};

class SoundsPage : public QWidget {
    Q_OBJECT

public:
    explicit SoundsPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadBytes(const QByteArray& bytes, const QString& path);
    bool saveAsTo(const QString& dest);
    QString qcText() const;
    QString metaText() const;

signals:
    void homeRequested();

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    SoundsBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
    WaveView* wave_ = nullptr;
};
