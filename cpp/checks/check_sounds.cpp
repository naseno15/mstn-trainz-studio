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
    page.show();
    app.processEvents();
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
    page.close();
    std::printf("check_sounds: ok\n");
    return 0;
}
