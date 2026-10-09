#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QFile>
#include <QImage>
#include <QTemporaryDir>

#include "ui/ve_rules.h"

namespace {

bool has(const QList<VeReport>& reports, int code) {
    for (const VeReport& r : reports)
        if (r.codes().contains(code)) return true;
    return false;
}

void write(const QString& path, const QByteArray& bytes) {
    QFile file(path);
    assert(file.open(QIODevice::WriteOnly));
    file.write(bytes);
}

}  // namespace

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    QTemporaryDir tmp;
    assert(tmp.isValid());
    const QString dir = tmp.path();

    QImage odd(300, 200, QImage::Format_RGBA8888);
    for (int y = 0; y < 200; ++y)
        for (int x = 0; x < 300; ++x) odd.setPixelColor(x, y, QColor(x % 256, y, 40));
    assert(odd.save(dir + "/body_albedo.png"));
    QImage solid(64, 64, QImage::Format_RGBA8888);
    solid.fill(QColor(10, 200, 30));
    assert(solid.save(dir + "/flat.png"));
    write(dir + "/config.txt", "trainz-build 2.0\nlight 1\nmesh-table\n{\n  default\n  {\n    mesh \"missing.im\"\n  }\n}\n");
    write(dir + "/single.lm.txt", "version 1.0\nmesh(\"1\") { name=\"nope.trainzmesh\"; }\n");
    write(dir + "/horn.wav", "not riff at all!");

    const QList<VeReport> reports = ve_scan_paths({dir});
    std::printf("%s\n", ve_format_reports(reports).toUtf8().constData());
    for (int code : {37, 65, 39, 49, 48, 44, 30, 84})
        if (!has(reports, code)) std::fprintf(stderr, "missing VE%d\n", code), assert(false);
    assert(ve_scan_sound(dir + "/horn.wav").codes() == QList<int>{102});

    VeReport flat = ve_scan_image(dir + "/flat.png");
    assert(flat.status() == QStringLiteral("VE39 #0AC81E"));
    const VeSummary before = ve_summarize(reports);
    assert(before.errors > 0 && before.fixable > 0 && before.line.contains(QStringLiteral("VE37")));

    const QList<VeFix> fixes = ve_fix_reports(reports);
    for (const VeFix& fix : fixes) assert(fix.ok);
    assert(QImage(dir + "/body_albedo.png").size() == QSize(256, 128));
    assert(QFile::exists(dir + "/body_albedo.png.bak"));
    assert(QFile::exists(dir + "/body_albedo.texture.txt"));
    assert(ve_scan_image(dir + "/flat.png").codes().isEmpty());
    const QList<VeReport> after = ve_scan_texture_folder(dir);
    assert(!has(after, 37) && !has(after, 39) && !has(after, 65));
    std::printf("check_ve: ok (%lld fixes)\n", static_cast<long long>(fixes.size()));
    return 0;
}
