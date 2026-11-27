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

    // Multi-line description must stay one header — body lines like "Engine:" must not become root tags (VE45).
    const char* multi = R"(
kind enginespec
description "line1
Engine: not a tag
Air: still description
max-accel / note"
motor
{
  throttle-notches 1
}
throttle-power
{
  1
  {
    0 1
  }
}
)";
    EngineSpec multi_spec = parse_enginespec(multi);
    assert(multi_spec.header.count("Engine:") == 0);
    assert(multi_spec.header.count("Air:") == 0);
    assert(multi_spec.header["description"].find("Engine: not a tag") != std::string::npos);
    const std::string multi_out = write_enginespec(multi_spec);
    EngineSpec multi_back = parse_enginespec(multi_out);
    assert(multi_back.header.count("Engine:") == 0);
    assert(multi_back.header.count("Air:") == 0);
    assert(multi_back.header["description"].find("Air: still description") != std::string::npos);
    // Writer must not emit description body lines as extra root keys after the closing quote.
    const auto desc_end = multi_out.find("max-accel / note\"");
    assert(desc_end != std::string::npos);
    const std::string after_desc = multi_out.substr(desc_end + 16);
    assert(after_desc.find("\nEngine:") == std::string::npos);
    assert(after_desc.find("\nAir:") == std::string::npos);

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
    const QJsonObject fitted = QJsonDocument::fromJson(page.centerJson().toUtf8()).object();
    // load_text auto-fits axes from throttle extents (sample point 36 km/h × 20→25 kN).
    assert(fitted.value(QStringLiteral("maxKmh")).toString().toDouble() >= 36.0);
    assert(fitted.value(QStringLiteral("maxKn")).toString().toDouble() >= 20.0);
    page.setPage(QStringLiteral("simulation"));
    app.processEvents();
    assert(page.pageName() == QLatin1String("simulation"));
    page.close();
    std::printf("check_engine: ok\n");
    return 0;
}
