#include "sounds_page.h"
#include "feedback.h"

#include "shell_window.h"

#include <algorithm>
#include <cmath>

#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QPainter>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QDir>
#include <QPolygon>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QShortcut>
#include <QUrl>
#include <QVBoxLayout>

namespace {

QString qml_dir() {
#ifdef QML_DIR
    return QStringLiteral(QML_DIR);
#else
    return {};
#endif
}

bool same_file(const QString& left, const QString& right) {
    if (left.isEmpty() || right.isEmpty()) return false;
    return QFileInfo(left).absoluteFilePath().compare(QFileInfo(right).absoluteFilePath(), Qt::CaseInsensitive) == 0;
}

}  // namespace

WaveView::WaveView(QWidget* parent) : QWidget(parent) { setAttribute(Qt::WA_TransparentForMouseEvents); }

void WaveView::set_samples(const std::vector<int16_t>& samples) {
    samples_ = samples;
    update();
}

void WaveView::set_playhead(double frac) {
    playhead_ = frac;
    update();
}

void WaveView::set_marks(const std::vector<double>& fractions) {
    marks_ = fractions;
    update();
}

void WaveView::paintEvent(QPaintEvent*) {
    QPainter paint(this);
    const bool dark = ui_dark();
    paint.fillRect(rect(), dark ? QColor(18, 22, 28) : QColor(246, 247, 249));
    const int mid = height() / 2;
    // amplitude grid: 0, -6, -12, -24 dBFS (both polarities) + zero line
    paint.setFont(QFont(QStringLiteral("Consolas"), 7));
    for (double db : {0.0, -6.0, -12.0, -24.0}) {
        const int dy = static_cast<int>(std::pow(10.0, db / 20.0) * mid);
        paint.setPen(QColor(128, 138, 150, db == 0.0 ? 90 : 55));
        paint.drawLine(0, mid - dy, width(), mid - dy);
        paint.drawLine(0, mid + dy, width(), mid + dy);
        paint.setPen(QColor(128, 138, 150, 170));
        paint.drawText(3, mid - dy - 1, QStringLiteral("%1 dB").arg(db, 0, 'f', 0));
    }
    paint.setPen(QColor(128, 138, 150, 140));
    paint.drawLine(0, mid, width(), mid);
    if (samples_.empty() || width() < 2) return;
    const int columns = std::max(1, width());
    std::vector<int> rms_y(static_cast<size_t>(columns));
    for (int x = 0; x < columns; ++x) {
        const size_t begin = samples_.size() * static_cast<size_t>(x) / static_cast<size_t>(columns);
        const size_t end = std::min(samples_.size(), std::max(begin + 1, samples_.size() * static_cast<size_t>(x + 1) / static_cast<size_t>(columns)));
        int16_t lo = samples_[begin];
        int16_t hi = samples_[begin];
        double sum = 0;
        for (size_t i = begin; i < end; ++i) {
            lo = std::min(lo, samples_[i]);
            hi = std::max(hi, samples_[i]);
            sum += static_cast<double>(samples_[i]) * samples_[i];
        }
        rms_y[static_cast<size_t>(x)] = static_cast<int>(std::sqrt(sum / static_cast<double>(end - begin)) / 32768.0 * mid);
        paint.setPen(QColor(255, 90, 31, 150));
        paint.drawLine(x, mid - static_cast<int>(hi / 32768.0 * mid), x, mid - static_cast<int>(lo / 32768.0 * mid));
    }
    // RMS envelope (mirrored)
    paint.setPen(QPen(QColor(60, 190, 255), 1));
    for (int x = 1; x < columns; ++x) {
        paint.drawLine(x - 1, mid - rms_y[static_cast<size_t>(x - 1)], x, mid - rms_y[static_cast<size_t>(x)]);
        paint.drawLine(x - 1, mid + rms_y[static_cast<size_t>(x - 1)], x, mid + rms_y[static_cast<size_t>(x)]);
    }
    for (double m : marks_) {
        const int mx = std::clamp(static_cast<int>(m * width()), 0, width() - 1);
        paint.setPen(QPen(QColor(255, 60, 60, 220), 1));
        paint.drawLine(mx, 0, mx, height());
        paint.setBrush(QColor(255, 60, 60));
        paint.drawPolygon(QPolygon({QPoint(mx - 5, 0), QPoint(mx + 5, 0), QPoint(mx, 8)}));
    }
    if (playhead_ >= 0) {
        paint.setPen(QPen(QColor(255, 255, 255), 2));
        const int px = std::clamp(static_cast<int>(playhead_ * width()), 0, width() - 1);
        paint.drawLine(px, 0, px, height());
    }
}
SoundsBridge::SoundsBridge(QObject* parent) : QObject(parent) {
    timer_.setInterval(33);
    connect(&timer_, &QTimer::timeout, this, &SoundsBridge::tick);
}

void SoundsBridge::load_bytes(const QByteArray& bytes, const QString& path) {
    try {
        const QString name = QFileInfo(path).fileName();
        add_clip(name.isEmpty() ? QStringLiteral("clip.wav") : name, path,
                 read_wav_pcm16(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size())));
    } catch (const std::exception& error) {
        bar_tip_ = QStringLiteral("Cannot read WAV: ") + QString::fromUtf8(error.what());
        emit changed();
    }
}

void SoundsBridge::add_clip(const QString& name, const QString& path, PcmClip clip, bool select) {
    data_.push_back({name, path, std::move(clip)});
    clips_ << name;
    if (select) selectClip(static_cast<int>(data_.size()) - 1);
}
void SoundsBridge::refresh() {
    if (clip_.samples.empty() || clip_.rate < 1) {
        meta_ = QStringLiteral("No clip");
        amp_ = QStringLiteral("Peak —   RMS —");
        qc_.clear();
        marks_.clear();
        emit changed();
        return;
    }
    const double seconds = static_cast<double>(clip_.samples.size()) / clip_.rate;
    int peak = 0;
    double sum = 0;
    for (int16_t sample : clip_.samples) {
        peak = std::max(peak, std::abs(static_cast<int>(sample)));
        sum += static_cast<double>(sample) * sample;
    }
    const double rms = std::sqrt(sum / static_cast<double>(clip_.samples.size())) / 32768.0;
    meta_ = QStringLiteral("%1 Hz · %2 samples · %3 s")
                .arg(clip_.rate)
                .arg(clip_.samples.size())
                .arg(seconds, 0, 'f', 2);
    const auto dbfs = [](double v) { return v > 1e-9 ? 20.0 * std::log10(v) : -120.0; };
    amp_ = QStringLiteral("Peak %1 (%2 dBFS)   RMS %3 (%4 dBFS)")
               .arg(peak / 32768.0, 0, 'f', 3).arg(dbfs(peak / 32768.0), 0, 'f', 1).arg(rms, 0, 'f', 5).arg(dbfs(rms), 0, 'f', 1);
    const auto findings = analyze_pcm(clip_.samples, clip_.rate, clips_.value(current_).toStdString());
    QStringList lines;
    for (const QcFinding& finding : findings) lines << QString::fromStdString(finding.severity + "  " + finding.message);
    qc_ = lines.join(QLatin1Char('\n'));
    marks_.clear();
    for (const QcFinding& finding : findings)
        if (finding.time >= 0 && seconds > 0) marks_.push_back(finding.time / seconds);
    emit changed();
}

bool SoundsBridge::save_as(const QString& dest) {
    if (clip_.samples.empty() || dest.isEmpty() || same_file(dest, source_)) {
        bar_tip_ = QStringLiteral("Save As will not overwrite the open file");
        emit changed();
        return false;
    }
    const auto bytes = write_wav_pcm16(apply_gain_db(clip_.samples, gain_db_), clip_.rate);
    QFile file(dest);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    file.write(reinterpret_cast<const char*>(bytes.data()), static_cast<qint64>(bytes.size()));
    bar_tip_ = QStringLiteral("Saved ") + QFileInfo(dest).fileName();
    post_status(bar_tip_);
    emit changed();
    return true;
}

void SoundsBridge::browse() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open WAV"), {}, QStringLiteral("WAV (*.wav)"));
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return;
    load_bytes(file.readAll(), path);
}

void SoundsBridge::pickFfmpeg() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("ffmpeg"), {}, QStringLiteral("ffmpeg (ffmpeg.exe)"));
    if (path.isEmpty()) return;
    ffmpeg_ = path;
    emit changed();
}

void SoundsBridge::selectClip(int index) {
    if (index < 0 || index >= static_cast<int>(data_.size())) return;
    current_ = index;
    clip_ = data_[static_cast<size_t>(index)].pcm;
    source_ = data_[static_cast<size_t>(index)].path;
    refresh();
}

void SoundsBridge::dropUrls(const QVariantList& urls) {
    for (const QVariant& item : urls) {
        const QUrl url(item.toString());
        const QString path = url.isLocalFile() ? url.toLocalFile() : item.toString();
        const QFileInfo info(path);
        if (info.isDir() || info.fileName().compare(QStringLiteral("config.txt"), Qt::CaseInsensitive) == 0) {
            load_engine(info.isDir() ? path : info.absolutePath());
            continue;
        }
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) continue;
        BusyToast busy({path}, QStringLiteral("Reading ") + QFileInfo(path).fileName() + QStringLiteral("..."));
        const QByteArray bytes = file.readAll();
        busy.step(QStringLiteral("Analysing ") + QFileInfo(path).fileName() + QStringLiteral("..."), 0);
        load_bytes(bytes, path);
    }
}

void SoundsBridge::waveRect(double x, double y, double w, double h) { emit waveRectRequested(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)); }

void SoundsBridge::setSlotA() {
    slot_a_ = current_;
    update_slots();
}
void SoundsBridge::setSlotB() {
    slot_b_ = current_;
    update_slots();
}
void SoundsBridge::setGainDb(double db) {
    gain_db_ = std::clamp(std::round(db * 2) / 2, -24.0, 12.0);
    if (player_.playing() && !engine_mode_) start_play(ab_);
    else emit changed();
}
void SoundsBridge::update_slots() {
    const auto name = [this](int i) { return i >= 0 && i < clips_.size() ? clips_[i] : QStringLiteral("-"); };
    slots_ = QStringLiteral("A (transition) = %1    B (steady loop) = %2").arg(name(slot_a_), name(slot_b_));
    emit changed();
}
void SoundsBridge::start_play(bool ab) {
    player_.stop();
    engine_mode_ = false;
    ab_ = ab;
    if (ab) {
        if (slot_a_ < 0 || slot_b_ < 0) {
            bar_tip_ = QStringLiteral("Select a clip and press Set A (transition), then another and Set B (steady loop)");
            emit changed();
            return;
        }
        const PcmClip& a = data_[static_cast<size_t>(slot_a_)].pcm;
        const PcmClip& b = data_[static_cast<size_t>(slot_b_)].pcm;
        player_.start(apply_gain_db(a.samples, gain_db_), apply_gain_db(resample_linear(b.samples, b.rate, a.rate), gain_db_), true, a.rate);
        phase_ = QStringLiteral("A->B");
    } else {
        if (clip_.samples.empty()) return;
        player_.start({}, apply_gain_db(clip_.samples, gain_db_), loop_on_, clip_.rate);
        phase_.clear();
    }
    play_ = QStringLiteral("Playing");
    timer_.start();
    emit changed();
}
void SoundsBridge::tick() {
    if (!player_.playing()) {
        stop();
        return;
    }
    if (engine_mode_) {
        if (eng_in_transition_ && player_.position() >= player_.head_size()) {
            eng_in_transition_ = false;
            eng_notch_ = eng_next_;
            eng_text_ = QStringLiteral("Notch %1").arg(eng_notch_);
            if (eng_notch_ != eng_target_) eng_step();
            emit changed();
        }
        return;
    }
    const size_t pos = player_.position();
    double frac = 0;
    if (ab_) {
        const size_t head = player_.head_size();
        const bool in_head = pos < head;
        const int want = in_head ? slot_a_ : slot_b_;
        if (want != current_) selectClip(want);
        frac = in_head ? static_cast<double>(pos) / static_cast<double>(head)
                       : static_cast<double>((pos - head) % player_.tail_size()) / static_cast<double>(player_.tail_size());
    } else {
        const size_t size = player_.tail_size();
        frac = static_cast<double>(loop_on_ ? pos % size : std::min(pos, size)) / static_cast<double>(size);
    }
    emit playheadChanged(frac);
}
void SoundsBridge::playAB() { start_play(true); }
void SoundsBridge::togglePlay() {
    if (player_.playing()) stop();
    else start_play(false);
}
void SoundsBridge::stop() {
    player_.stop();
    if (engine_mode_) {
        engine_mode_ = false;
        eng_in_transition_ = false;
        eng_notch_ = eng_target_ = 0;
        eng_text_ = QStringLiteral("Off");
    }
    timer_.stop();
    play_ = QStringLiteral("Play");
    phase_.clear();
    emit playheadChanged(-1);
    emit changed();
}
void SoundsBridge::toggleLoop() {
    loop_on_ = !loop_on_;
    loop_ = loop_on_ ? QStringLiteral("Loop: On") : QStringLiteral("Loop: Off");
    if (player_.playing() && !ab_ && !engine_mode_) start_play(false);
    else emit changed();
}
void SoundsBridge::fix() {
    if (clip_.samples.empty()) {
        bar_tip_ = QStringLiteral("Open a WAV first");
        emit changed();
        return;
    }
    const bool trans = current_ == slot_a_ && slot_b_ >= 0 && slot_b_ != slot_a_;
    PcmClip out;
    out.rate = clip_.rate;
    const QString stem = QFileInfo(clips_.value(current_)).completeBaseName();
    if (trans) {
        const PcmClip& b = data_[static_cast<size_t>(slot_b_)].pcm;
        out.samples = make_transition(clip_.samples, resample_linear(b.samples, b.rate, clip_.rate), clip_.rate);
    } else {
        out.samples = make_loop(clip_.samples, clip_.rate);
    }
    add_clip(stem + (trans ? QStringLiteral("_trans.wav") : QStringLiteral("_loop.wav")), {}, std::move(out));
    bar_tip_ = trans ? QStringLiteral("Crossfaded A into the end of B � Set A to the new clip, Play A?B, then Save As")
                     : QStringLiteral("Seamless loop built (new clip) � Play with Loop On, then Save As");
    emit changed();
}void SoundsBridge::saveAs() {
    const QString dest = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Save As"), {}, QStringLiteral("WAV (*.wav)"));
    if (!dest.isEmpty()) save_as(dest);
}
void SoundsBridge::goHome() { emit homeRequested(); }

SoundsPage::SoundsPage(QWidget* parent) : QWidget(parent) {
    bridge_ = new SoundsBridge(this);
    connect(bridge_, &SoundsBridge::homeRequested, this, &SoundsPage::homeRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setSource(QUrl::fromLocalFile(qml_dir() + QStringLiteral("/SoundsPage.qml")));
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addWidget(view_);
    wave_ = new WaveView(this);
    connect(UiTheme::instance(), &UiTheme::changed, wave_, qOverload<>(&QWidget::update));
    wave_->hide();
    connect(bridge_, &SoundsBridge::waveRectRequested, this, [this](int x, int y, int w, int h) {
        if (w < 8 || h < 8) {
            wave_->hide();
            return;
        }
        wave_->setGeometry(x, y, w, h);
        wave_->show();
        wave_->raise();
    });
    connect(bridge_, &SoundsBridge::playheadChanged, wave_, &WaveView::set_playhead);
    connect(bridge_, &SoundsBridge::changed, this, [this] {
        wave_->set_samples(bridge_->clip().samples);
        wave_->set_marks(bridge_->marks());
    });
    auto* space = new QShortcut(QKeySequence(Qt::Key_Space), this);
    space->setContext(Qt::WidgetWithChildrenShortcut);
    connect(space, &QShortcut::activated, bridge_, &SoundsBridge::togglePlay);
}

void SoundsPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
}

bool SoundsPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList SoundsPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void SoundsPage::loadBytes(const QByteArray& bytes, const QString& path) { bridge_->load_bytes(bytes, path); }
bool SoundsPage::loadEngine(const QString& dir) { return bridge_->load_engine(dir); }
bool SoundsPage::saveAsTo(const QString& dest) { return bridge_->save_as(dest); }
QString SoundsPage::qcText() const { return bridge_->qc(); }
QString SoundsPage::metaText() const { return bridge_->meta(); }

QStringList SoundsBridge::devices() const {
    QStringList list{QStringLiteral("Default (Windows)")};
    for (const std::string& name : WavePlayer::devices()) list << QString::fromLocal8Bit(name.c_str());
    return list;
}

void SoundsBridge::setDeviceIndex(int index) {
    device_index_ = std::max(0, index);
    player_.set_device(device_index_ - 1);
    // the open waveOut device cannot be re-routed live; restart plain playback on the new device, engine picks it up on its next step
    if (player_.playing() && !engine_mode_) start_play(ab_);
    else emit changed();
}

// Engine sound folder: start/stop, "idle N", "up N - M", "down N - M" (the Trainz enginesound layout).
bool SoundsBridge::load_engine(const QString& dir) {
    const QDir folder(dir);
    const QStringList files = folder.entryList({QStringLiteral("*.wav")}, QDir::Files, QDir::Name | QDir::IgnoreCase);
    if (files.isEmpty()) {
        bar_tip_ = QStringLiteral("No WAV files in ") + dir;
        emit changed();
        return false;
    }
    stop();
    data_.clear();
    clips_.clear();
    eng_ = EngineSet();
    slot_a_ = slot_b_ = -1;
    slots_.clear();
    current_ = -1;
    clip_ = PcmClip();
    QFile config(folder.filePath(QStringLiteral("config.txt")));
    eng_.name = QFileInfo(dir).fileName();
    if (config.open(QIODevice::ReadOnly)) {
        static const QRegularExpression user(QStringLiteral("^username\\s+\"([^\"]*)\""), QRegularExpression::MultilineOption | QRegularExpression::CaseInsensitiveOption);
        const auto match = user.match(QString::fromUtf8(config.readAll()));
        if (match.hasMatch()) eng_.name = match.captured(1);
    }
    static const QRegularExpression idle(QStringLiteral("^idle\\s*(\\d+)$")), up(QStringLiteral("^up\\s*(\\d+)\\s*-\\s*(\\d+)$")), down(QStringLiteral("^down\\s*(\\d+)\\s*-\\s*(\\d+)$"));
    BusyToast busy(files, QStringLiteral("Loading engine sound..."));
    int done = 0;
    for (const QString& file : files) {
        busy.step(file, done++);
        QFile wav(folder.filePath(file));
        if (!wav.open(QIODevice::ReadOnly)) continue;
        const QByteArray bytes = wav.readAll();
        PcmClip clip;
        try {
            clip = read_wav_pcm16(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
        } catch (const std::exception&) {
            continue;
        }
        const QString stem = QFileInfo(file).completeBaseName().toLower();
        const int index = static_cast<int>(data_.size());
        if (stem == QLatin1String("start")) eng_.start = index;
        else if (stem == QLatin1String("stop")) eng_.stop = index;
        else if (const auto m = idle.match(stem); m.hasMatch()) eng_.idle[m.captured(1).toInt()] = index;
        else if (const auto m2 = up.match(stem); m2.hasMatch()) eng_.up[m2.captured(1).toInt()] = index;
        else if (const auto m3 = down.match(stem); m3.hasMatch()) eng_.down[std::min(m3.captured(1).toInt(), m3.captured(2).toInt())] = index;
        add_clip(file, folder.filePath(file), std::move(clip), false);
    }
    selectClip(eng_.idle.isEmpty() ? 0 : eng_.idle.first());
    eng_text_ = QStringLiteral("Off  (%1 notches)").arg(eng_.top());
    bar_tip_ = QStringLiteral("Engine sound loaded: ") + eng_.name;
    post_status(bar_tip_);
    emit changed();
    return true;
}

void SoundsBridge::eng_play(int head, int tail, bool loop) {
    const auto at = [this](int i) -> const PcmClip* { return i >= 0 && i < static_cast<int>(data_.size()) ? &data_[static_cast<size_t>(i)].pcm : nullptr; };
    const PcmClip* lead = at(head) ? at(head) : at(tail);
    if (!lead) return;
    const auto prep = [&](const PcmClip* c) {
        return c ? apply_gain_db(resample_linear(c->samples, c->rate, lead->rate), gain_db_) : std::vector<int16_t>();
    };
    player_.stop();
    player_.set_device(device_index_ - 1);
    player_.start(prep(at(head)), prep(at(tail)), loop, lead->rate);
    engine_mode_ = true;
    ab_ = false;
    play_ = QStringLiteral("Playing");
    phase_ = QStringLiteral("Engine");
    timer_.start();
}

// One notch per step; the next step waits until the transition clip has played out (like the sim queues notch changes).
// ponytail: each step restarts waveOut, so there can be a few ms gap/click between the transition and the idle loop.
void SoundsBridge::eng_step() {
    if (eng_notch_ == 0) {
        if (!eng_.idle.contains(1)) return;
        eng_next_ = 1;
        eng_in_transition_ = eng_.start >= 0;
        eng_text_ = QStringLiteral("Starting");
        eng_play(eng_.start, eng_.idle[1], true);
        if (!eng_in_transition_) eng_notch_ = 1;
        return;
    }
    const bool rising = eng_notch_ < eng_target_;
    const int next = eng_notch_ + (rising ? 1 : -1);
    if (next < 1 || !eng_.idle.contains(next)) return;
    const int head = rising ? eng_.up.value(eng_notch_, -1) : eng_.down.value(next, -1);
    eng_next_ = next;
    eng_in_transition_ = head >= 0;
    eng_text_ = QStringLiteral("Notch %1 -> %2").arg(eng_notch_).arg(next);
    eng_play(head, eng_.idle[next], true);
    if (!eng_in_transition_) eng_notch_ = next;
}

void SoundsBridge::engStart() {
    if (!engineOn()) return;
    if (engine_mode_ && eng_notch_ > 0) return;
    eng_notch_ = 0;
    eng_target_ = 1;
    eng_step();
    emit changed();
}
void SoundsBridge::engUp() {
    if (!engine_mode_ || eng_target_ < 1) return engStart();
    eng_target_ = std::min(eng_.top(), eng_target_ + 1);
    if (!eng_in_transition_ && eng_notch_ != eng_target_) eng_step();
    emit changed();
}
void SoundsBridge::engDown() {
    if (!engine_mode_) return;
    eng_target_ = std::max(1, eng_target_ - 1);
    if (!eng_in_transition_ && eng_notch_ != eng_target_) eng_step();
    emit changed();
}
void SoundsBridge::engStop() {
    if (!engine_mode_ || eng_.stop < 0) {
        stop();
        return;
    }
    eng_target_ = 0;
    eng_notch_ = 0;
    eng_in_transition_ = false;
    eng_text_ = QStringLiteral("Stopping");
    eng_play(eng_.stop, -1, false);
    emit changed();
}
