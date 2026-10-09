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
#include <QResizeEvent>
#include <QUrl>

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

void WaveView::paintEvent(QPaintEvent*) {
    QPainter paint(this);
    paint.fillRect(rect(), ui_dark() ? QColor(18, 22, 28) : QColor(246, 247, 249));
    if (samples_.empty() || width() < 2) return;
    paint.setPen(QColor(255, 90, 31));
    const int mid = height() / 2;
    const int columns = std::max(1, width());
    for (int x = 0; x < columns; ++x) {
        const size_t begin = samples_.size() * static_cast<size_t>(x) / static_cast<size_t>(columns);
        const size_t end = std::max(begin + 1, samples_.size() * static_cast<size_t>(x + 1) / static_cast<size_t>(columns));
        int16_t lo = samples_[begin];
        int16_t hi = samples_[begin];
        for (size_t i = begin; i < end && i < samples_.size(); ++i) {
            lo = std::min(lo, samples_[i]);
            hi = std::max(hi, samples_[i]);
        }
        const int y0 = mid - static_cast<int>(hi / 32768.0 * mid);
        const int y1 = mid - static_cast<int>(lo / 32768.0 * mid);
        paint.drawLine(x, y0, x, y1);
    }
}

SoundsBridge::SoundsBridge(QObject* parent) : QObject(parent) {}

void SoundsBridge::load_bytes(const QByteArray& bytes, const QString& path) {
    clip_ = read_wav_pcm16(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
    source_ = path;
    clips_ = QStringList{QFileInfo(path).fileName().isEmpty() ? QStringLiteral("clip.wav") : QFileInfo(path).fileName()};
    current_ = 0;
    refresh();
}

void SoundsBridge::refresh() {
    if (clip_.samples.empty() || clip_.rate < 1) {
        meta_ = QStringLiteral("No clip");
        amp_ = QStringLiteral("Peak —   RMS —");
        qc_.clear();
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
    amp_ = QStringLiteral("Peak %1   RMS %2").arg(peak / 32768.0, 0, 'f', 3).arg(rms, 0, 'f', 5);
    const auto findings = analyze_pcm(clip_.samples, clip_.rate, clips_.value(current_).toStdString());
    QStringList lines;
    for (const QcFinding& finding : findings) lines << QString::fromStdString(finding.severity + "  " + finding.message);
    qc_ = lines.join(QLatin1Char('\n'));
    emit changed();
}

bool SoundsBridge::save_as(const QString& dest) {
    if (clip_.samples.empty() || dest.isEmpty() || same_file(dest, source_)) {
        bar_tip_ = QStringLiteral("Save As will not overwrite the open file");
        emit changed();
        return false;
    }
    const auto bytes = write_wav_pcm16(clip_.samples, clip_.rate);
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
    if (index < 0 || index >= clips_.size()) return;
    current_ = index;
    refresh();
}

void SoundsBridge::dropUrls(const QVariantList& urls) {
    if (urls.isEmpty()) return;
    const QUrl url(urls.front().toString());
    const QString path = url.isLocalFile() ? url.toLocalFile() : urls.front().toString();
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return;
    BusyToast busy({path}, QStringLiteral("Reading ") + QFileInfo(path).fileName() + QStringLiteral("…"));
    const QByteArray bytes = file.readAll();
    busy.step(QStringLiteral("Analysing ") + QFileInfo(path).fileName() + QStringLiteral("…"), 0);
    load_bytes(bytes, path);
}

void SoundsBridge::waveRect(double x, double y, double w, double h) { emit waveRectRequested(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)); }

void SoundsBridge::setSlotA() {
    slot_a_ = current_;
    slots_ = QStringLiteral("A = ") + clips_.value(current_);
    emit changed();
}
void SoundsBridge::setSlotB() {
    slot_b_ = current_;
    slots_ = QStringLiteral("B = ") + clips_.value(current_);
    emit changed();
}
void SoundsBridge::playAB() {
    phase_ = QStringLiteral("A→B");
    emit changed();
}
void SoundsBridge::togglePlay() {
    play_ = play_ == QLatin1String("Play") ? QStringLiteral("Playing") : QStringLiteral("Play");
    emit changed();
}
void SoundsBridge::stop() {
    play_ = QStringLiteral("Play");
    phase_.clear();
    emit changed();
}
void SoundsBridge::toggleLoop() {
    loop_on_ = !loop_on_;
    loop_ = loop_on_ ? QStringLiteral("Loop: On") : QStringLiteral("Loop: Off");
    emit changed();
}
void SoundsBridge::fix() {
    bar_tip_ = QStringLiteral("Fix stays in memory later — Save As writes a new file");
    emit changed();
}
void SoundsBridge::saveAs() {
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
    connect(bridge_, &SoundsBridge::changed, this, [this] { wave_->set_samples(bridge_->clip().samples); });
}

void SoundsPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (view_) view_->setGeometry(rect());
}

bool SoundsPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList SoundsPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void SoundsPage::loadBytes(const QByteArray& bytes, const QString& path) { bridge_->load_bytes(bytes, path); }
bool SoundsPage::saveAsTo(const QString& dest) { return bridge_->save_as(dest); }
QString SoundsPage::qcText() const { return bridge_->qc(); }
QString SoundsPage::metaText() const { return bridge_->meta(); }
