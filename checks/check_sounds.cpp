#undef NDEBUG
#include <cassert>
#include <cstdio>
#include <fstream>

#include <QApplication>
#include <QDir>
#include <QFile>

#include "io/wav.h"
#include "ui/shell_window.h"
#include "ui/sounds_page.h"

static std::vector<int16_t> tone(int count, int16_t level) { return std::vector<int16_t>(static_cast<size_t>(count), level); }

int main(int argc, char** argv) {
    const auto steady = write_wav_pcm16(tone(8000, 16000), 8000);
    const PcmClip clip = read_wav_pcm16(steady.data(), steady.size());
    assert(clip.rate == 8000);
    assert(clip.samples.size() == 8000);
    assert(clip.samples[0] == 16000);
    const auto ok = analyze_pcm(clip.samples, clip.rate, "loop.wav");
    assert(ok.size() == 1);
    assert(ok[0].message == "ok");
    const auto short_clip = analyze_pcm(tone(400, 16000), 8000, "loop.wav");
    assert(!short_clip.empty());
    assert(short_clip[0].kind == "short");

    const QString dir = QDir::temp().filePath(QStringLiteral("trainz-studio-phase6"));
    QDir(dir).removeRecursively();
    QDir().mkpath(dir);
    const QString source = QDir(dir).filePath(QStringLiteral("loop.wav"));
    const QString copy = QDir(dir).filePath(QStringLiteral("loop-copy.wav"));
    {
        std::ofstream out(source.toStdString(), std::ios::binary);
        out.write(reinterpret_cast<const char*>(steady.data()), static_cast<std::streamsize>(steady.size()));
    }
    const auto before = QFile(source).size();

    prepare_qt_runtime();
    QApplication app(argc, argv);
    SoundsPage page;
    page.loadBytes(QByteArray(reinterpret_cast<const char*>(steady.data()), static_cast<int>(steady.size())), source);
    page.resize(1200, 700);
    page.show();
    app.processEvents();
    if (qEnvironmentVariableIsSet("TRAINZ_SNAP")) { app.processEvents(); page.grab().save(qEnvironmentVariable("TRAINZ_SNAP")); }
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    assert(page.metaText().contains(QStringLiteral("8000 Hz")));
    assert(page.qcText().contains(QStringLiteral("ok")));
    assert(!page.saveAsTo(source));
    assert(QFile(source).size() == before);
    assert(page.saveAsTo(copy));
    QFile saved(copy);
    assert(saved.open(QIODevice::ReadOnly));
    const QByteArray written = saved.readAll();
    const PcmClip again = read_wav_pcm16(reinterpret_cast<const uint8_t*>(written.constData()), static_cast<size_t>(written.size()));
    assert(again.samples.size() == 8000);
    assert(again.samples[0] == 16000);
    std::vector<int16_t> ramp(8000);
    for (size_t i = 0; i < ramp.size(); ++i) ramp[i] = static_cast<int16_t>(i * 4);
    const auto loop = make_loop(ramp, 8000);
    assert(loop.size() == 6000);
    assert(std::abs(loop[0] - ramp[5999]) < 40);  // wrap continues the source
    const auto trans = make_transition(tone(8000, 1000), tone(8000, 9000), 8000);
    assert(trans.size() == 8000 && trans.back() > 8800 && trans[5000] == 1000);
    assert(resample_linear(tone(100, 5), 8000, 16000).size() == 200);
    {   // whole-track glitch scan: noise bed with one splice pop at 1.0 s must be found, clean noise must not
        std::vector<int16_t> noise(44100 * 2);
        uint32_t seed = 12345;
        for (auto& v : noise) { seed = seed * 1664525u + 1013904223u; v = static_cast<int16_t>((static_cast<int>(seed >> 16) % 600) - 300); }
        assert(scan_glitches(noise, 44100).empty());
        for (size_t i = 44100; i < 44100 + 40; ++i) noise[i] = static_cast<int16_t>(20000 - static_cast<int>(i - 44100) * 500);
        const auto hits = scan_glitches(noise, 44100);
        assert(!hits.empty() && std::abs(hits.front().time - 1.0) < 0.01);
    }
    if (qEnvironmentVariableIsSet("TRAINZ_ENGINE_DIR")) {
        assert(page.loadEngine(qEnvironmentVariable("TRAINZ_ENGINE_DIR")));
        QFile idle2(QDir(qEnvironmentVariable("TRAINZ_ENGINE_DIR")).filePath(QStringLiteral("idle 2.wav")));
        assert(idle2.open(QIODevice::ReadOnly));
        page.loadBytes(idle2.readAll(), idle2.fileName());
        for (int i = 0; i < 10; ++i) app.processEvents();
        std::printf("%s\n", page.qcText().toUtf8().constData());
        if (qEnvironmentVariableIsSet("TRAINZ_SNAP")) page.grab().save(qEnvironmentVariable("TRAINZ_SNAP"));
    }
    page.close();
    std::printf("check_sounds: ok\n");
    return 0;
}
