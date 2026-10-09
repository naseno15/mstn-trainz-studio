#pragma once

#include "ui/status_hub.h"

#include <QMap>
#include <QString>
#include <QStringList>
#include <QWidget>

#include "ui/icons.h"

#include <vector>

#include "io/wav.h"
#include "ui/wave_player.h"

#include <QTimer>

class QPaintEvent;
class QQuickWidget;

class WaveView : public QWidget {
public:
    explicit WaveView(QWidget* parent = nullptr);
    void set_samples(const std::vector<int16_t>& samples);
    void set_playhead(double frac);
    void set_marks(const std::vector<double>& fractions);

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    std::vector<int16_t> samples_;
    double playhead_ = -1;
    std::vector<double> marks_;
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
    Q_PROPERTY(double gainDb READ gainDb WRITE setGainDb NOTIFY changed)
    Q_PROPERTY(int current READ current NOTIFY changed)
    Q_PROPERTY(QStringList devices READ devices NOTIFY changed)
    Q_PROPERTY(int deviceIndex READ deviceIndex WRITE setDeviceIndex NOTIFY changed)
    Q_PROPERTY(bool engineOn READ engineOn NOTIFY changed)
    Q_PROPERTY(QString engineName READ engineName NOTIFY changed)
    Q_PROPERTY(QString engineText READ engineText NOTIFY changed)
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
    double gainDb() const { return gain_db_; }
    QStringList devices() const;
    int deviceIndex() const { return device_index_; }
    void setDeviceIndex(int index);
    bool engineOn() const { return eng_.start >= 0 || !eng_.idle.isEmpty(); }
    QString engineName() const { return eng_.name; }
    QString engineText() const { return eng_text_; }
    const std::vector<double>& marks() const { return marks_; }
    bool load_engine(const QString& dir);
    void setGainDb(double db);
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
    Q_INVOKABLE void engStart();
    Q_INVOKABLE void engUp();
    Q_INVOKABLE void engDown();
    Q_INVOKABLE void engStop();
    Q_INVOKABLE QStringList veContextPaths() const { return source_.isEmpty() ? QStringList() : QStringList{source_}; }

signals:
    void changed();
    void homeRequested();
    void waveRectRequested(int x, int y, int w, int h);
    void playheadChanged(double frac);

private:
    void refresh();
    void tick();
    void update_slots();
    void add_clip(const QString& name, const QString& path, PcmClip clip, bool select = true);
    void start_play(bool ab);
    void eng_step();
    void eng_play(int head, int tail, bool loop);
    struct EngineSet {
        QString name;
        int start = -1, stop = -1;
        QMap<int, int> idle, up, down;  // up[n]: n->n+1, down[n]: n+1->n
        int top() const { int n = 0; while (idle.contains(n + 1)) ++n; return n; }
    } eng_;
    bool engine_mode_ = false, eng_in_transition_ = false;
    int eng_notch_ = 0, eng_target_ = 0, eng_next_ = 0;
    QString eng_text_;
    int device_index_ = 0;
    std::vector<double> marks_;
    struct Entry {
        QString name, path;
        PcmClip pcm;
    };
    std::vector<Entry> data_;
    WavePlayer player_;
    QTimer timer_;
    bool ab_ = false;
    double gain_db_ = 0;
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
    bool loadEngine(const QString& dir);
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
