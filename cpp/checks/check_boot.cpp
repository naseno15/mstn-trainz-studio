#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QWidget>

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    QWidget window;
    window.setWindowTitle(QStringLiteral("check_boot"));
    assert(window.windowTitle() == QStringLiteral("check_boot"));
    std::printf("check_boot: ok\n");
    return 0;
}
