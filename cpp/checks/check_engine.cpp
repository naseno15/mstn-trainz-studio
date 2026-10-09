#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include "io/enginespec.h"
#include "ui/engine_page.h"
#include "ui/shell_window.h"

int main(int argc, char** argv) {
    const char* sample = R"(
kind enginespec
username "Phase4"
motor
{
  throttle-notches 8
}
pressure
{
  main-reservoir 0.011227
}
throttle-power
{
  1
  {
    10 20
  }
}
)";
    EngineSpec spec = parse_enginespec(sample);
    assert(spec.header["username"] == "Phase4");
    assert(spec.throttle[1].size() == 1);
    assert(fmt_kmh(spec.throttle[1][0].first) == "36");
    assert(fmt_kn(spec.throttle[1][0].second) == "20");
    assert(fmt_bar(spec.blocks["pressure"]["main-reservoir"]) == "11.227");
    assert(edit_throttle_point(spec, 1, 0, 1, "25"));
    const std::string written = write_enginespec(spec);
    EngineSpec again = parse_enginespec(written);
    assert(fmt_kn(again.throttle[1][0].second) == "25");
    assert(again.header["kind"] == "enginespec");

    prepare_qt_runtime();
    QApplication app(argc, argv);
    EngineTunerPage page;
    page.loadText(QString::fromLatin1(sample));
    page.show();
    app.processEvents();
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    const QJsonObject before = QJsonDocument::fromJson(page.centerJson().toUtf8()).object();
    const auto notches = before.value(QStringLiteral("notches")).toArray();
    assert(notches.size() == 9);
    const auto pts = notches.at(1).toObject().value(QStringLiteral("pts")).toArray();
    assert(pts.at(0).toObject().value(QStringLiteral("kmh")).toString() == QLatin1String("36"));
    assert(pts.at(0).toObject().value(QStringLiteral("kn")).toString() == QLatin1String("20"));
    page.editPoint(1, 0, 1, QStringLiteral("25"));
    assert(page.specText().contains(QStringLiteral("25")));
    assert(page.centerJson().contains(QStringLiteral("\"kn\":\"25\"")));
    page.setPage(QStringLiteral("simulation"));
    app.processEvents();
    assert(page.pageName() == QLatin1String("simulation"));
    page.close();
    std::printf("check_engine: ok\n");
    return 0;
}
