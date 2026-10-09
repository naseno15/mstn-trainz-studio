#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>

#include "ui/shell_window.h"

int main(int argc, char** argv) {
    prepare_qt_runtime();
    QApplication app(argc, argv);
    int stages = 0;
    ShellWindow window(nullptr, [&](const QString&, int pct) {
        assert(pct >= 0 && pct <= 100);
        ++stages;
    });
    assert(stages >= 4);
    window.show();
    app.processEvents();
    if (!window.qmlReady()) {
        for (const QString& line : window.qmlErrors()) std::fprintf(stderr, "%s\n", line.toUtf8().constData());
        assert(window.qmlReady());
    }
    window.openStudio(QStringLiteral("mesh"));
    app.processEvents();
    assert(window.page() == QLatin1String("mesh"));
    window.triggerItem(QStringLiteral("home"));
    app.processEvents();
    assert(window.page() == QLatin1String("home"));
    window.triggerItem(QStringLiteral("sounds"));
    assert(window.page() == QLatin1String("sounds"));
    const QRect menu(10, 10, 40, 20);
    const QRect title(0, 0, 200, 40);
    assert(!chrome_click_dismisses_menu(menu, title, QPoint(12, 12)));
    assert(!chrome_click_dismisses_menu(menu, title, QPoint(80, 8)));
    assert(chrome_click_dismisses_menu(menu, title, QPoint(400, 200)));
    window.close();
    std::printf("check_shell: ok\n");
    return 0;
}
