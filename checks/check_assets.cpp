#undef NDEBUG
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

#include <QApplication>
#include <QColor>
#include <QDir>
#include <QFile>
#include <QImage>
#include <QWidget>

#include "io/acs_tree.h"
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

void check_acs() {
    const QString sample = QStringLiteral(
        "kind \"traincar\"\n"
        "interior <kuid:1:2>\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    mesh \"body.lm\"\n"
        "    mesh-asset <kuid:1:9>\n"
        "    effects\n"
        "    {\n"
        "      body-albedo\n"
        "      {\n"
        "        kind \"texture-replacement\"\n"
        "        texture \"body.texture\"\n"
        "      }\n"
        "      glow\n"
        "      {\n"
        "        kind \"corona\"\n"
        "        texture-kuid <kuid:1:8>\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
        "kuid-table\n"
        "{\n"
        "  0 <kuid:1:7>\n"
        "  lib <kuid:2:3>\n"
        "}\n");
    const AcsFile file = parse_acs(sample);
    assert(file.ok);
    assert(file.root.kids.size() == 4);
    const QList<int> effect = {2, 0, 2, 0};
    const AcsNode* node = acs_at(file.root, effect);
    assert(node != nullptr && node->name == QLatin1String("body-albedo"));
    const QStringList parents = acs_parents(file.root, {2, 0, 2, 0});
    assert(parents.last() == QLatin1String("body-albedo"));
    const AcsHint kind = acs_hint(parents, QStringLiteral("kind"), QStringLiteral("texture-replacement"), false);
    assert(kind.editor == QLatin1String("enum"));
    assert(kind.options.contains(QLatin1String("texture-replacement")));
    const AcsHint mass = acs_hint({}, QStringLiteral("mass"), QStringLiteral("37300"), false);
    assert(mass.editor == QLatin1String("number") && mass.unit == QLatin1String("kg"));
    const AcsHint mesh = acs_hint(acs_parents(file.root, {2, 0}), QStringLiteral("mesh-asset"), QStringLiteral("<kuid:1:9>"), false);
    assert(mesh.editor == QLatin1String("kuid") && mesh.filter.contains(QLatin1String("MESH")));
    const AcsHint alias = acs_hint(QStringList{QStringLiteral("kuid-table")}, QStringLiteral("0"), QStringLiteral("<kuid:1:7>"), false);
    assert(alias.editor == QLatin1String("alias"));
    const AcsHint named = acs_hint(QStringList{QStringLiteral("kuid-table")}, QStringLiteral("lib"), QStringLiteral("<kuid:2:3>"), false);
    assert(named.editor == QLatin1String("kuid"));
    const AcsHint build = acs_hint({}, QStringLiteral("trainz-build"), QStringLiteral("4.6"), false);
    assert(build.editor == QLatin1String("menu"));
    assert(acs_menu_text(QStringLiteral("4.6"), build.options).contains(QLatin1String("TRS19 SP1")));
    assert(acs_menu_text(QStringLiteral("5"), build.options).contains(QLatin1String("TRS19 SP5")));
    assert(acs_format(QStringLiteral("menu"), QStringLiteral("4.6"), false) == QLatin1String("4.6"));
    QString edited = sample;
    const AcsNode* texture = acs_at(file.root, {2, 0, 2, 0, 1});
    assert(texture != nullptr && texture->name == QLatin1String("texture"));
    edited.replace(texture->begin, texture->end - texture->begin, acs_format(QStringLiteral("file"), QStringLiteral("cab.texture"), texture->quoted));
    const AcsFile again = parse_acs(edited);
    const AcsNode* updated = acs_at(again.root, {2, 0, 2, 0, 1});
    assert(updated != nullptr && updated->value == QLatin1String("cab.texture"));
}

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

    check_acs();
    {
        const QString root = QDir::temp().filePath(QStringLiteral("trainz-studio-folder-scan"));
        QDir(root).removeRecursively();
        assert(QDir().mkpath(root + QStringLiteral("/mesh")));
        assert(QDir().mkpath(root + QStringLiteral("/nested")));
        auto write = [](const QString& path, const char* body) {
            QFile file(path);
            assert(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
            assert(file.write(body) == qint64(std::char_traits<char>::length(body)));
        };
        write(root + QStringLiteral("/config.chump"), "chump");
        write(root + QStringLiteral("/mesh/body.trainzmesh"), "mesh");
        write(root + QStringLiteral("/.stamp"), "stamp");
        write(root + QStringLiteral("/nested/config.txt"), "kuid <kuid:1:2>\n");
        write(root + QStringLiteral("/nested/only-here.txt"), "child");
        const FolderAssetScan scan = scan_folder_assets(root);
        assert(scan.assets.size() == 2);
        const CdpAssetEntry* parent = nullptr;
        const CdpAssetEntry* child = nullptr;
        for (const CdpAssetEntry& row : scan.assets) {
            if (QString::fromStdString(row.kuid) == QStringLiteral("nested")) child = &row;
            else parent = &row;
        }
        assert(parent != nullptr && child != nullptr);
        auto has = [](const CdpAssetEntry& row, const char* name) {
            return std::find(row.files.begin(), row.files.end(), std::string(name)) != row.files.end();
        };
        assert(has(*parent, "config.chump"));
        assert(has(*parent, "mesh/body.trainzmesh"));
        assert(!has(*parent, ".stamp"));
        assert(!has(*parent, "nested/only-here.txt"));
        assert(has(*child, "config.txt"));
        assert(has(*child, "only-here.txt"));
        assert(parent->files.size() == parent->sizes.size());
        QDir(root).removeRecursively();
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
    {
        // Texture Params writes what the form shows, and keeps keys it has no field for.
        const QString dir = QDir::temp().filePath(QStringLiteral("trainz-texparams"));
        QDir(dir).removeRecursively();
        QDir().mkpath(dir);
        QImage img(4, 4, QImage::Format_RGBA8888);
        img.fill(QColor(200, 100, 50, 128));
        const QString a = QDir(dir).filePath(QStringLiteral("a.tga"));
        const QString b = QDir(dir).filePath(QStringLiteral("b_normal.png"));
        assert(img.save(a) && img.save(b));
        auto write = [](const QString& path, const QByteArray& text) {
            QFile f(path);
            assert(f.open(QIODevice::WriteOnly));
            f.write(text);
        };
        auto read = [](const QString& path) {
            QFile f(path);
            assert(f.open(QIODevice::ReadOnly));
            return QString::fromUtf8(f.readAll());
        };
        const QString a_txt = QDir(dir).filePath(QStringLiteral("a.texture.txt"));
        const QString b_txt = QDir(dir).filePath(QStringLiteral("b_normal.texture.txt"));
        write(b_txt, "Primary=b_normal.png\nAlphaHint=masked\nUsageHint=parameter\n");
        QWidget host;
        Texmesh tex(&host);
        tex.set_page(QStringLiteral("texture"));
        tex.drop_paths({a, b});
        tex.set_field(QStringLiteral("alphaOn"), QStringLiteral("1"));  // no file picked: Primary's own alpha
        tex.run_action(QStringLiteral("tex_save_all"));
        assert(read(a_txt).contains(QStringLiteral("Alpha=a.tga\n")));
        QString bt = read(b_txt);
        assert(bt.contains(QStringLiteral("AlphaHint=masked\n")) && bt.contains(QStringLiteral("UsageHint=parameter\n")));
        assert(!bt.contains(QStringLiteral("UsageHint=normal")) && !bt.contains(QStringLiteral("\nAlpha=")));
        tex.pick_row(1);  // b: its .texture.txt loads into the form, nothing carried over from a
        tex.set_field(QStringLiteral("compress"), QStringLiteral("dxt5"));
        tex.run_action(QStringLiteral("tex_save_all"));
        bt = read(b_txt);
        assert(bt.contains(QStringLiteral("Compression=dxt5\n")) && bt.contains(QStringLiteral("AlphaHint=masked\n")) && !bt.contains(QStringLiteral("\nAlpha=")));
        const QString at = read(a_txt);
        assert(at.contains(QStringLiteral("Alpha=a.tga\n")) && at.contains(QStringLiteral("Compression=dxt5\n")));
        QDir(dir).removeRecursively();
    }
    page.setSuite(QStringLiteral("assets"));
    assert(page.pageName() == QLatin1String("packages"));
    page.close();
    std::printf("check_assets: ok\n");
    return 0;
}
