#undef NDEBUG
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>

#include <QApplication>
#include <QDir>
#include <QFile>

#include "io/cdp.h"
#include "ui/assets_page.h"
#include "ui/shell_window.h"
#include "ui/texmesh.h"

#ifndef FIXTURE_DIR
#define FIXTURE_DIR "checks/fixtures"
#endif

int main(int argc, char** argv) {
    const std::string path = std::string(FIXTURE_DIR) + "/demo.cdp";
    std::ifstream in(path, std::ios::binary);
    assert(in);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    const auto assets = list_cdp_assets(bytes.data(), bytes.size());
    assert(assets.size() == 1);
    assert(assets[0].kuid == "<kuid:1:2>");
    assert(assets[0].username == "Demo");
    assert(assets[0].kind == "scenery");
    bool saw_note = false;
    for (const std::string& file : assets[0].files) {
        if (file == "note.txt") saw_note = true;
    }
    assert(saw_note);
    const auto note = read_cdp_file(bytes.data(), bytes.size(), assets[0].kuid, "note.txt");
    assert(std::string(note.begin(), note.end()) == "hello cdp");

    prepare_qt_runtime();
    QApplication app(argc, argv);
    AssetsPage page;
    page.loadBytes(QByteArray(reinterpret_cast<const char*>(bytes.data()), static_cast<int>(bytes.size())), QStringLiteral("demo.cdp"));
    page.show();
    app.processEvents();
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    assert(page.assetCount() == 1);
    assert(page.cell(0, 0) == QLatin1String("<kuid:1:2>"));
    assert(page.cell(0, 1) == QLatin1String("Demo"));
    assert(page.cell(0, 2) == QLatin1String("scenery"));
    assert(page.fileText(0, QStringLiteral("note.txt")) == QLatin1String("hello cdp"));
    const QString dest = QDir::temp().filePath(QStringLiteral("trainz-studio-phase5"));
    QDir(dest).removeRecursively();
    assert(page.extractTo(dest) == 1);
    QFile extracted(QDir(dest).filePath(QStringLiteral("kuid_1_2/note.txt")));
    assert(extracted.open(QIODevice::ReadOnly));
    assert(extracted.readAll() == "hello cdp");
    page.setPage(QStringLiteral("kuid"));
    app.processEvents();
    assert(page.pageName() == QLatin1String("kuid"));
    page.setSuite(QStringLiteral("texmesh"));
    assert(page.pageName() == QLatin1String("meshops"));
    assert(page.formOn());
    assert(page.centerList() == QLatin1String("Mesh files"));
    page.setPage(QStringLiteral("texture"));
    app.processEvents();
    assert(page.pageName() == QLatin1String("texture"));
    assert(page.centerList().startsWith(QLatin1String("Images")));
    unsigned char sample[4 * 4 * 4] = {};
    for (int i = 0; i < 16; ++i) {
        sample[i * 4] = 200;
        sample[i * 4 + 3] = 255;
    }
    sample[(1 * 4 + 1) * 4 + 0] = 10;
    sample[(1 * 4 + 1) * 4 + 1] = 10;
    sample[(1 * 4 + 1) * 4 + 2] = 10;
    sample[(1 * 4 + 1) * 4 + 3] = 10;
    sample[(1 * 4 + 2) * 4 + 0] = 12;
    sample[(1 * 4 + 2) * 4 + 1] = 12;
    sample[(1 * 4 + 2) * 4 + 2] = 12;
    sample[(1 * 4 + 2) * 4 + 3] = 12;
    sample[(2 * 4 + 2) * 4 + 0] = 200;
    assert(magic_pick_count(sample, 4, 4, 1, 1, 8, true) >= 2);
    assert(magic_pick_count(sample, 4, 4, 1, 1, 8, true) < 16);
    page.setSuite(QStringLiteral("assets"));
    assert(page.pageName() == QLatin1String("packages"));
    page.close();
    std::printf("check_assets: ok\n");
    return 0;
}
