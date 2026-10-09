#undef NDEBUG
#include <cassert>
#include <cstdio>

#include <QApplication>
#include <QClipboard>
#include <QDialog>
#include <QQmlEngine>
#include <QQuickWidget>
#include <QThread>

#include "ui/crash_report.h"
#include "ui/i18n.h"
#include "ui/shell_window.h"
#include "ui/status_hub.h"

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
    const auto alive = [&](const QString& menu_key, const QString& label) {
        for (const QVariant& row : window.menuRows(menu_key)) {
            const QVariantMap map = row.toMap();
            if (map.value(QStringLiteral("label")).toString() == label) return map.value(QStringLiteral("alive")).toBool();
        }
        return false;
    };
    for (const char* page : {"home", "mesh", "sounds", "engine", "assets", "texmesh", "trainzutil"}) {
        window.triggerItem(QString::fromLatin1(page));
        app.processEvents();
        if (!alive(QStringLiteral("file"), QStringLiteral("Open…"))) std::fprintf(stderr, "Open… dead on %s\n", page);
        assert(alive(QStringLiteral("file"), QStringLiteral("Open…")));
        for (const char* key : {"file", "edit", "view", "tools", "theme", "lang"}) assert(!window.menuRows(QString::fromLatin1(key)).isEmpty());
    }
    window.triggerItem(QStringLiteral("engine"));
    assert(alive(QStringLiteral("edit"), QStringLiteral("Undo")) && alive(QStringLiteral("file"), QStringLiteral("Save As…")));
    window.triggerItem(QStringLiteral("mesh"));
    assert(alive(QStringLiteral("file"), QStringLiteral("Save")) && alive(QStringLiteral("view"), QStringLiteral("Reset camera")));
    window.triggerItem(QStringLiteral("home"));
    assert(!alive(QStringLiteral("edit"), QStringLiteral("Undo")));
    const bool was_dark = alive(QStringLiteral("theme"), QStringLiteral("Dark")) && window.menuRows(QStringLiteral("theme")).first().toMap().value(QStringLiteral("checked")).toBool();
    window.triggerItem(QStringLiteral("theme:toggle"));
    assert(window.menuRows(QStringLiteral("theme")).first().toMap().value(QStringLiteral("checked")).toBool() != was_dark);
    window.triggerItem(QStringLiteral("theme:toggle"));
    assert(window.menuRows(QStringLiteral("theme")).first().toMap().value(QStringLiteral("checked")).toBool() == was_dark);

    const QRect menu(10, 10, 40, 20);
    const QRect title(0, 0, 200, 40);
    assert(!chrome_click_dismisses_menu(menu, title, QPoint(12, 12)));
    assert(!chrome_click_dismisses_menu(menu, title, QPoint(80, 8)));
    assert(chrome_click_dismisses_menu(menu, title, QPoint(400, 200)));

    assert(is_save_notice(QStringLiteral("Saved body.lm.txt")));
    assert(is_save_notice(QStringLiteral("Wrote 3 texture.txt")));
    assert(!is_save_notice(QStringLiteral("Unsaved changes")));
    assert(!is_save_notice(QStringLiteral("Save failed")));
    assert(is_error_notice(QStringLiteral("createCDP failed")));
    assert(parse_progress_pct(QStringLiteral("Loading mesh… 42%")) == 42);
    assert(parse_progress_pct(QStringLiteral("Loaded")) == -1);
    assert(short_progress_detail(QStringLiteral("Loading"), QStringLiteral("Loading 40%")).isEmpty());

    StatusHub* hub = StatusHub::instance();
    const int before = hub->logCount();
    hub->post(QStringLiteral("Loading mesh 40%"));
    assert(hub->toastShown() && hub->toastKind() == QLatin1String("progress") && hub->toastPct() == 40);
    hub->post(QStringLiteral("Loaded body.im"));
    assert(hub->toastPct() == 100);
    for (int i = 0; i < 30 && hub->toastKind() == QLatin1String("progress"); ++i) {
        QThread::msleep(20);
        app.processEvents();
    }
    assert(hub->toastKind() == QLatin1String("save") && hub->toastTitle() == QLatin1String("Done"));
    hub->post(QStringLiteral("Save failed — cannot write a.im"));
    assert(hub->toastKind() == QLatin1String("error") && hub->textKind() == QLatin1String("error"));
    assert(hub->logCount() == before + 3);
    assert(hub->history().last().contains(QLatin1String("Save failed")));
    window.close();

    QDialog* crash = make_crash_dialog(QStringLiteral("Status log"), QStringLiteral("S"), QStringLiteral("trace"), QStringLiteral("log"), false);
    auto* view = crash->findChild<QQuickWidget*>();
    int qml_warnings = 0;
    QObject::connect(view->engine(), &QQmlEngine::warnings, [&](const QList<QQmlError>& list) {
        for (const QQmlError& e : list) std::fprintf(stderr, "%s\n", e.toString().toUtf8().constData());
        qml_warnings += static_cast<int>(list.size());
    });
    crash->show();
    app.processEvents();
    assert(view->status() == QQuickWidget::Ready);
    assert(qml_warnings == 0);
    auto* bridge = crash->findChild<CrashBridge*>();
    bridge->copyError(QString());
    assert(QApplication::clipboard()->text().contains(QLatin1String("trace")));
    assert(bridge->copyLabel() == QLatin1String("Copied"));
    bridge->dismiss();
    delete crash;
    const QString was = UiLang::instance()->lang();
    UiLang::instance()->set_lang(QStringLiteral("th"));
    assert(ui_tr(QStringLiteral("Save As")) == QStringLiteral("บันทึกเป็น"));
    assert(QCoreApplication::translate("Main", "Open") == QStringLiteral("เปิด"));
    UiLang::instance()->set_lang(QStringLiteral("ja"));
    assert(ui_tr(QStringLiteral("Save As")) == QStringLiteral("名前を付けて保存"));
    UiLang::instance()->set_lang(was);
    std::printf("check_shell: ok\n");
    return 0;
}
