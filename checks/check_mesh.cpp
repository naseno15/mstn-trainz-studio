#undef NDEBUG
#include <cassert>
#include <cmath>
#include <cstdio>

#include <QApplication>
#include <QKeyEvent>
#include <QDir>
#include <QFileInfo>
#include <QImage>
#include <QUrl>

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
    assert(page.sideJson().contains(QStringLiteral("\"atts\":")));
    {
        auto* mesh = page.findChild<MeshBridge*>();
        assert(mesh);
        const QString was = mesh->dockJson();
        mesh->setText(QStringLiteral("matName"), QStringLiteral("undo_probe"));
        assert(mesh->dockJson().contains(QStringLiteral("undo_probe")));
        mesh->undoEdit();
        assert(!mesh->dockJson().contains(QStringLiteral("undo_probe")) && mesh->dockJson() == was);
        mesh->redoEdit();
        assert(mesh->dockJson().contains(QStringLiteral("undo_probe")));
        mesh->undoEdit();
        mesh->setChecked(QStringLiteral("ground"), true);  // view toggle, not an edit: no undo step
        mesh->undoEdit();
        assert(!mesh->dockJson().contains(QStringLiteral("undo_probe")));
    }
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
    // Several meshes: each .kin binds to the mesh holding its bone, and each plays on its own.
    const QString ats = QStringLiteral("c:/trs22/editing/kuid 1190880 100112 MSTN KIHA _ ______40/mesh/");
    if (QFileInfo::exists(ats + QStringLiteral("atsleft_scene.kin"))) {
        auto* mesh = page.findChild<MeshBridge*>();
        page.loadScene({ats + QStringLiteral("atsleft.trainzmesh"), ats + QStringLiteral("atsright.trainzmesh"), ats + QStringLiteral("ats_box.trainzmesh")}, {}, {});
        app.processEvents();
        const QString side = page.sideJson();
        assert(side.contains(QStringLiteral("atsleft ▸ atsleft_scene.kin")));
        assert(side.contains(QStringLiteral("atsright ▸ atsright_scene.kin")));
        assert(!side.contains(QStringLiteral("ats_box ▸")));
        mesh->pickList(QStringLiteral("anim"), 0);
        mesh->clickId(QStringLiteral("play"));
        mesh->pickList(QStringLiteral("anim"), 1);
        mesh->clickId(QStringLiteral("play"));
        assert(page.sideJson().count(QStringLiteral(" ▶")) == 2);
        mesh->clickId(QStringLiteral("play"));  // stops only the selected clip
        assert(page.sideJson().count(QStringLiteral(" ▶")) == 1);
        mesh->clickId(QStringLiteral("clearMesh"));
        page.loadScene({ats + QStringLiteral("atsleft.trainzmesh"), ats + QStringLiteral("ats_box.trainzmesh")}, {}, {});
        app.processEvents();
        assert(page.sideJson().contains(QStringLiteral("atsleft ▸ atsleft_scene.kin")));
        mesh->dropUrls({QUrl::fromLocalFile(ats + QStringLiteral("atsright_scene.kin")).toString()});
        assert(!page.sideJson().contains(QStringLiteral("atsright_scene.kin")));  // its bone is not in this scene
    }
    const QString body = QStringLiteral("c:/trs22/editing/kuid 1125787 100059 MSTN KIHA _ ______40/body/body.trainzmesh");
    if (QFileInfo::exists(body)) {
        page.loadFile(body);
        app.processEvents();
        assert(page.sideJson().contains(QStringLiteral("a.airdryer")));
    }
    {
        const double deg[3] = {10.0, -35.0, 120.0};
        float q[4] = {};
        att_quat(deg, q);
        double back[3] = {};
        att_euler(q, back);
        for (int k = 0; k < 3; ++k) assert(std::fabs(back[k] - deg[k]) < 1e-3);
        const double yaw[3] = {0.0, 0.0, 90.0};
        att_quat(yaw, q);
        assert(std::fabs(q[2] - 0.70710678f) < 1e-5f && std::fabs(q[3] - 0.70710678f) < 1e-5f);
        const float flip[4] = {0.f, 0.f, 1.f, -1.947e-7f};
        att_euler(flip, back);
        assert(std::fabs(std::fabs(back[2]) - 180.0) < 1e-3 && std::fabs(back[0]) < 1e-3 && std::fabs(back[1]) < 1e-3);
    }
    assert(pie_sector(0.f, -40.f, 4, 3) == 0);
    assert(pie_sector(40.f, 0.f, 4, 3) == 1);
    assert(pie_sector(0.f, 40.f, 4, 3) == 2);
    assert(pie_sector(-40.f, 0.f, 4, 3) == 3);
    assert(pie_sector(0.f, 0.f, 4, 2) == 2);
    assert(pie_sector(0.f, 40.f, 2, 0) == 1);
    assert(pie_sector(-30.f, -40.f, 2, 1) == 0);  // upper-left is still the top (Move) slice
    assert(pie_sector(-40.f, 30.f, 2, 0) == 1);
    assert(pie_sector(-20.f, -40.f, 4, 1) == 0);
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
