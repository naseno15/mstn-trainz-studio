#undef NDEBUG
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <QApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QStringList>
#include <QTemporaryDir>

#include "io/chump.h"
#include "io/config_id.h"
#include "ui/icons.h"
#include "ui/install_queue.h"
#include "ui/shell_window.h"
#include "ui/trainzutil_page.h"

static std::vector<uint8_t> tzarc_v1(const std::string& name, const std::string& payload) {
    std::vector<uint8_t> out = {'T', 'Z', 'a', 'c', 0, 0, 0, 1, 0, 0, 0, 1};
    out.push_back(static_cast<uint8_t>(name.size()));
    out.insert(out.end(), name.begin(), name.end());
    uint64_t size = payload.size();
    for (int shift = 56; shift >= 0; shift -= 8) out.push_back(static_cast<uint8_t>((size >> shift) & 0xFF));
    out.insert(out.end(), {0, 0, 0, 0});
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}

static ChumpTag text_tag(const char* name, const char* value) {
    ChumpTag tag;
    tag.name = name;
    tag.type = ChumpType::Text;
    tag.text = value;
    return tag;
}

static void check_identity() {
    const std::string text =
        "username \"\xE3\x82\xAD\xE3\x83\x8F\x34\x30\"\n"
        "author \"Boonnop\"\n"
        "trainz-build 4.6\n"
        "kuid <kuid:1:2>\n";
    const ConfigIdentity text_id = config_identity(reinterpret_cast<const uint8_t*>(text.data()), text.size());
    assert(text_id.username == "\xE3\x82\xAD\xE3\x83\x8F\x34\x30");
    assert(text_id.author == "Boonnop");
    assert(text_id.build == "4.6");
    assert(text_id.kuid == "<kuid:1:2>");
    assert(author_label("4.6", "4.6").empty());
    assert(author_label("3.7", "").empty());
    assert(author_label("Boonnop", "4.6") == "Boonnop");

    ChumpFile file;
    ChumpTag soup;
    soup.name = "route";
    soup.type = ChumpType::Soup;
    soup.children.push_back(text_tag("username", "hidden"));
    file.root.push_back(soup);
    file.root.push_back(text_tag("author", "Boonnop"));
    file.root.push_back(text_tag("trainz-build", "4.6"));
    file.root.push_back(text_tag("username", "KIHA"));
    const std::vector<uint8_t> chump = encode_chump(file);
    const ConfigIdentity chump_id = config_identity(chump.data(), chump.size());
    assert(chump_id.username == "KIHA");
    assert(chump_id.author == "Boonnop");
    assert(chump_id.build == "4.6");

    const std::string config =
        "username \"KIHA\"\nauthor \"Boonnop\"\ntrainz-build 4.6\nkuid <kuid2:1190880:100078:1>\n";
    const std::vector<uint8_t> archive = tzarc_v1("config.txt", config);
    const QString path = QDir::temp().filePath(QStringLiteral("trainz-studio-phase3.tzarc"));
    QFile out(path);
    assert(out.open(QIODevice::WriteOnly));
    out.write(reinterpret_cast<const char*>(archive.data()), static_cast<qint64>(archive.size()));
    out.close();

    TrainzUtilPage page;
    page.open_archive(path);
    assert(page.library_rows() == 1);
    assert(page.cell(0, 0) == QLatin1String("KIHA"));
    assert(page.cell(0, 1) == QLatin1String("<kuid2:1190880:100078:1>"));
    assert(page.cell(0, 2) == QLatin1String("Boonnop"));
    assert(page.cell(0, 3) == QLatin1String("4.6"));
}

static void check_find() {
    QTemporaryDir dir;
    assert(dir.isValid());
    const QString common = dir.filePath(QStringLiteral("steamapps/common"));
    auto touch = [](const QString& path) {
        QDir().mkpath(QFileInfo(path).path());
        QFile file(path);
        assert(file.open(QIODevice::WriteOnly));
    };
    touch(common + QStringLiteral("/Trainz A New Era/TrainzUtil.exe"));
    touch(common + QStringLiteral("/Trainz Railroad Simulator 2022/TrainzUtil.exe"));
    touch(common + QStringLiteral("/Some Other Game/TrainzUtil.exe"));
    const QString newer = QFileInfo(common + QStringLiteral("/Trainz Railroad Simulator 2022/TrainzUtil.exe")).absoluteFilePath();
    assert(trainzutil_under_common(common) == newer);
    assert(trainzutil_under_common(dir.filePath(QStringLiteral("missing"))).isEmpty());
    const QString saved = dir.filePath(QStringLiteral("saved/TrainzUtil.exe"));
    touch(saved);
    assert(find_trainzutil(saved) == QFileInfo(saved).absoluteFilePath());
}

static void check_queue() {
    InstallQueue queue;
    QStringList order;
    QList<InstallQueue::Done> waiting;
    queue.set_runner([&](const InstallJob& job, const InstallQueue::Done& done) {
        assert(queue.active() == 1);
        order << job.id;
        waiting << done;
    });
    queue.enqueue({
        {QStringLiteral("a"), QStringLiteral("a.cdp")},
        {QStringLiteral("b"), QStringLiteral("b.cdp")},
        {QStringLiteral("c"), QStringLiteral("c.cdp")},
    });
    assert(order == QStringList({QStringLiteral("a")}));
    assert(queue.pending() == 2);
    waiting.takeFirst()(true, QString());
    QApplication::processEvents();
    assert(order == QStringList({QStringLiteral("a"), QStringLiteral("b")}));
    queue.stop();
    waiting.takeFirst()(true, QString());
    QApplication::processEvents();
    assert(queue.finished() == QStringList({QStringLiteral("a"), QStringLiteral("b")}));
    assert(!order.contains(QStringLiteral("c")));
}

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    check_identity();
    check_find();
    check_queue();
    TrainzUtilPage page;
    page.show();
    app.processEvents();
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    page.close();
    std::printf("check_trainzutil: ok\n");
    return 0;
}
