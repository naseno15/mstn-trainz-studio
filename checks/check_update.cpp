#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>

#include "ui/app_update.h"

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    assert(version_is_newer(QStringLiteral("v4.2.2"), QStringLiteral("4.2.1")));
    assert(!version_is_newer(QStringLiteral("v4.2.1"), QStringLiteral("4.2.1")));
    assert(!version_is_newer(QStringLiteral("4.2.0"), QStringLiteral("4.2.1")));
    assert(version_is_newer(QStringLiteral("4.10.0"), QStringLiteral("4.9.9")));
    assert(version_is_newer(QStringLiteral("v5"), QStringLiteral("4.2.1")));
    assert(!version_is_newer(QStringLiteral("nope"), QStringLiteral("4.2.1")));

    const QByteArray json = R"json({
      "tag_name":"v9.1.0","body":"notes",
      "assets":[
        {"name":"notes.txt","browser_download_url":"https://example.invalid/n.txt"},
        {"name":"other.zip","browser_download_url":"https://example.invalid/o.zip"},
        {"name":"TrainzStudio-9.1.0-win64.zip","browser_download_url":"https://example.invalid/w.zip"}
      ]
    })json";
    UpdateOffer offer;
    assert(parse_release_offer(json, QStringLiteral("4.2.1"), &offer));
    assert(offer.version == QLatin1String("9.1.0"));
    assert(offer.assetName == QLatin1String("TrainzStudio-9.1.0-win64.zip"));
    assert(offer.assetUrl.endsWith(QLatin1String("/w.zip")));
    assert(!parse_release_offer(json, QStringLiteral("9.1.0"), &offer));

    const QByteArray list = R"json([
      {"tag_name":"v4.3.0","name":"Trainz Studio 4.3.0","published_at":"2026-10-12T04:00:00Z","body":"Fixed the dock.","assets":[{"name":"TrainzStudio-4.3.0-win64.zip","browser_download_url":"https://example.invalid/a.zip"}]},
      {"tag_name":"v4.2.1","name":"Trainz Studio 4.2.1","published_at":"2026-10-11T12:00:00Z","body":"Line numbers.","prerelease":false}
    ])json";
    const QVariantList notes = release_notes(list, QStringLiteral("4.2.1"));
    assert(notes.size() == 2);
    assert(notes.at(0).toMap().value(QStringLiteral("version")).toString() == QLatin1String("4.3.0"));
    assert(notes.at(0).toMap().value(QStringLiteral("newer")).toBool());
    assert(notes.at(1).toMap().value(QStringLiteral("installed")).toBool());
    assert(!notes.at(1).toMap().value(QStringLiteral("newer")).toBool());
    QString sha, title, when;
    assert(parse_commit_summary(R"json([{"sha":"abcdef0123456789","commit":{"message":"Fix the viewer\n\nbody","author":{"date":"2026-10-12T04:10:00Z"}}}])json", &sha, &title, &when));
    assert(sha == QLatin1String("abcdef0"));
    assert(title == QLatin1String("Fix the viewer"));
    assert(!when.isEmpty());

    const QStringList errors = load_update_qml();
    for (const QString& line : errors) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
    assert(errors.isEmpty());
    return 0;
}
