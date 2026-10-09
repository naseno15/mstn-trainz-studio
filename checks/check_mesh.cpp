#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QDir>
#include <QFileInfo>

#include "ui/mesh_page.h"
#include "ui/mesh_view.h"
#include "ui/shell_window.h"

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    MeshStudioPage page;
    page.show();
    app.processEvents();
    if (!page.qmlReady()) {
        for (const QString& line : page.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(page.qmlReady());
    }
    const QString fixture = QFileInfo(QStringLiteral(QML_DIR)).dir().filePath(QStringLiteral("../../trainz_studio_cpp/checks/fixtures/tri.trainzmesh"));
    page.loadFile(QFileInfo(fixture).absoluteFilePath());
    app.processEvents();
    assert(page.sideJson().contains(QStringLiteral("mesh_0")));
    assert(studio_softbox_peak() == 255);
    page.close();
    std::printf("check_mesh: ok\n");
    return 0;
}
