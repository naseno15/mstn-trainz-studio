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

namespace {

std::vector<uint8_t> read_bytes(const char* path) {
    std::ifstream in(path, std::ios::binary);
    assert(in);
    return {(std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>()};
}

int check_real_cdp(const char* source, const char* destination) {
    constexpr const char* marker = "MSTN_CPP_ROUNDTRIP_20261009";
    const std::vector<uint8_t> original = read_bytes(source);
    const auto before = list_cdp_assets(original.data(), original.size());
    assert(!before.empty());

    std::string config = asset_config_text(original.data(), original.size(), before[0].kuid);
    const size_t username = config.find("username");
    assert(username != std::string::npos);
    size_t line_end = config.find('\n', username);
    if (line_end == std::string::npos) line_end = config.size();
    config.replace(username, line_end - username, std::string("username \"") + marker + "\"");

    const auto edited = replace_asset_config(
        original.data(), original.size(), before[0].kuid, config);
    QFile output(QString::fromLocal8Bit(destination));
    assert(output.open(QIODevice::WriteOnly | QIODevice::Truncate));
    assert(output.write(
               reinterpret_cast<const char*>(edited.data()),
               static_cast<qint64>(edited.size())) == static_cast<qint64>(edited.size()));
    output.close();

    const std::vector<uint8_t> saved = read_bytes(destination);
    const auto after = list_cdp_assets(saved.data(), saved.size());
    assert(after.size() == before.size());
    assert(after[0].username == marker);

    size_t checked_files = 0;
    for (size_t asset_index = 0; asset_index < before.size(); ++asset_index) {
        assert(after[asset_index].kuid == before[asset_index].kuid);
        assert(after[asset_index].files == before[asset_index].files);
        assert(before[asset_index].sizes.size() == before[asset_index].files.size());
        assert(after[asset_index].sizes == before[asset_index].sizes);
        if (asset_index > 0) {
            assert(
                asset_config_text(saved.data(), saved.size(), after[asset_index].kuid) ==
                asset_config_text(original.data(), original.size(), before[asset_index].kuid));
        }
        for (size_t file_index = 0; file_index < before[asset_index].files.size(); ++file_index) {
            const std::string& rel = before[asset_index].files[file_index];
            const auto original_file = read_cdp_file(original.data(), original.size(), before[asset_index].kuid, rel);
            assert(original_file.size() == before[asset_index].sizes[file_index]);
            assert(
                original_file ==
                read_cdp_file(saved.data(), saved.size(), after[asset_index].kuid, rel));
            ++checked_files;
        }
    }
    std::printf(
        "real_cdp_roundtrip: ok; assets=%zu files=%zu marker=%s output=%s\n",
        after.size(), checked_files, marker, destination);
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc == 3) return check_real_cdp(argv[1], argv[2]);
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
    assert(assets[0].sizes.size() == assets[0].files.size());
    const std::string cfg = asset_config_text(bytes.data(), bytes.size(), assets[0].kuid);
    assert(cfg.find("Demo") != std::string::npos);
    const auto note = read_cdp_file(bytes.data(), bytes.size(), assets[0].kuid, "note.txt");
    assert(std::string(note.begin(), note.end()) == "hello cdp");
    auto edited = replace_asset_config(
        bytes.data(), bytes.size(), assets[0].kuid,
        "username \"Changed\"\nkind \"scenery\"\nkuid <kuid:1:2>\n");
    assert(list_cdp_assets(edited.data(), edited.size())[0].username == "Changed");
    const std::string replacement = "changed note";
    edited = replace_cdp_file(
        edited.data(), edited.size(), assets[0].kuid, "note.txt",
        reinterpret_cast<const uint8_t*>(replacement.data()), replacement.size());
    const auto changed_note = read_cdp_file(edited.data(), edited.size(), assets[0].kuid, "note.txt");
    assert(std::string(changed_note.begin(), changed_note.end()) == replacement);
    edited = remove_cdp_file(edited.data(), edited.size(), assets[0].kuid, "note.txt");
    assert(list_cdp_assets(edited.data(), edited.size())[0].files.empty());
    const QString saved_cdp = QDir::temp().filePath(QStringLiteral("trainz-studio-edited.cdp"));
    {
        QFile saved(saved_cdp);
        assert(saved.open(QIODevice::WriteOnly | QIODevice::Truncate));
        assert(saved.write(
                   reinterpret_cast<const char*>(edited.data()),
                   static_cast<qint64>(edited.size())) == static_cast<qint64>(edited.size()));
    }
    {
        QFile saved(saved_cdp);
        assert(saved.open(QIODevice::ReadOnly));
        const QByteArray round_trip = saved.readAll();
        assert(list_cdp_assets(
                   reinterpret_cast<const uint8_t*>(round_trip.constData()),
                   static_cast<size_t>(round_trip.size()))[0]
                   .username == "Changed");
    }

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
