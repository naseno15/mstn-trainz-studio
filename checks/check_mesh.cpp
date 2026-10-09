#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QKeyEvent>
#include <QDir>
#include <QFileInfo>
#include <QImage>

#include "ui/mesh_page.h"
#include "ui/mesh_view.h"
#include "ui/shell_window.h"

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    MeshStudioPage page;
    page.show();
    app.processEvents();
    QKeyEvent tab_down(QEvent::KeyPress, Qt::Key_Tab, Qt::NoModifier);
    QApplication::sendEvent(&page, &tab_down);
    assert(page.pieOpen());
    QKeyEvent tab_up(QEvent::KeyRelease, Qt::Key_Tab, Qt::NoModifier);
    QApplication::sendEvent(&page, &tab_up);
    assert(page.pieOpen());
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    const QString fixture = QDir(QStringLiteral(QML_DIR)).filePath(QStringLiteral("../../checks/fixtures/tri.trainzmesh"));
    page.resize(960, 640);
    page.loadFile(QFileInfo(fixture).absoluteFilePath());
    app.processEvents();
    assert(!page.loadOpen());
    assert(page.loadSteps() >= 4);
    assert(page.sideJson().contains(QStringLiteral("tri.trainzmesh")));
    assert(studio_softbox_peak() == 255);
    const QImage frame = page.grabView();
    assert(!frame.isNull());
    int lit = 0;
    for (int y = 0; y < frame.height(); y += 2) {
        for (int x = 0; x < frame.width(); x += 2) {
            if (qGray(frame.pixel(x, y)) > 48) ++lit;
        }
    }
    std::fprintf(stderr, "mesh frame %dx%d lit %d\n", frame.width(), frame.height(), lit);
    assert(lit > 40);
    // Preview Asset: two meshes in one scene, labelled per asset; a bad path is skipped, not fatal.
    const QString fx = QFileInfo(fixture).absoluteFilePath();
    page.loadScene({fx, fx, QStringLiteral("nope.im")}, {QStringLiteral("Alpha"), QStringLiteral("Beta"), QStringLiteral("Gone")}, {0.0, 3.14159, 0.0});
    app.processEvents();
    assert(!page.loadOpen());
    assert(page.sideJson().contains(QStringLiteral("Alpha: ")) && page.sideJson().contains(QStringLiteral("Beta: ")));
    assert(!page.sideJson().contains(QStringLiteral("Gone")));
    assert(page.sideJson().contains(QStringLiteral("2 meshes")));
    assert(pie_sector(0.f, -40.f, 4, 3) == 0);
    assert(pie_sector(40.f, 0.f, 4, 3) == 1);
    assert(pie_sector(0.f, 40.f, 4, 3) == 2);
    assert(pie_sector(-40.f, 0.f, 4, 3) == 3);
    assert(pie_sector(0.f, 0.f, 4, 2) == 2);
    assert(pie_sector(0.f, 40.f, 2, 0) == 1);
    const QImage page_shot = page.grab().toImage();
    int shown = 0;
    const int x0 = page_shot.width() * 3 / 10;
    const int x1 = page_shot.width() * 7 / 10;
    const int y0 = page_shot.height() / 5;
    const int y1 = page_shot.height() * 4 / 5;
    for (int y = y0; y < y1; y += 2) {
        for (int x = x0; x < x1; x += 2) {
            if (qGray(page_shot.pixel(x, y)) > 48) ++shown;
        }
    }
    std::fprintf(stderr, "page center lit %d\n", shown);
    assert(shown > 40);
    page.close();
    std::printf("check_mesh: ok\n");
    return 0;
}
