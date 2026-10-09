#pragma once

#include <functional>

#include <QQuickImageProvider>
#include <QString>
#include <QVariantList>
#include <QWidget>

#include "ui/icons.h"
#include "ui/ve_rules.h"

class QLabel;
class QPixmap;
class QPropertyAnimation;
class QQuickWidget;
class QStackedWidget;
class AssetsPage;
class EngineTunerPage;
class MeshStudioPage;
class SoundsPage;
class TrainzUtilPage;

class ShellBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(QString brand READ brand NOTIFY changed)
    Q_PROPERTY(QString sub READ sub NOTIFY changed)
    Q_PROPERTY(QString copy READ copy NOTIFY changed)
    Q_PROPERTY(QString cta READ cta NOTIFY changed)
    Q_PROPERTY(QString dropTitle READ dropTitle NOTIFY changed)
    Q_PROPERTY(QString dropHint READ dropHint NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QVariantList cards READ cards NOTIFY changed)
    Q_PROPERTY(QString windowTitle READ windowTitle NOTIFY changed)
    Q_PROPERTY(QString openKey READ openKey NOTIFY changed)
    Q_PROPERTY(bool zoomed READ zoomed NOTIFY changed)
    Q_PROPERTY(int menuGen READ menuGen NOTIFY menuOpened)
    Q_PROPERTY(QVariantList menus READ menus NOTIFY changed)
    Q_PROPERTY(QVariantList items READ items NOTIFY changed)

public:
    explicit ShellBridge(QObject* parent = nullptr);

    bool dark() const;
    QString brand() const { return QStringLiteral("MSTN Trainz Studio"); }
    QString sub() const { return QStringLiteral("Meshes · sounds · engine · assets · maps"); }
    QString copy() const { return QStringLiteral("Copyright MSTN Production"); }
    QString cta() const { return QStringLiteral("Open  →"); }
    QString dropTitle() const { return QStringLiteral("Drop files"); }
    QString dropHint() const { return QStringLiteral(".trainzmesh  ·  .fbx  ·  .wav  ·  .cdp"); }
    QString iconFont() const { return material_icon_family(); }
    QVariantList cards() const { return cards_; }
    QString windowTitle() const { return title_; }
    QString openKey() const { return open_key_; }
    bool zoomed() const { return zoomed_; }
    int menuGen() const { return menu_gen_; }
    QVariantList menus() const { return menus_; }
    QVariantList items() const { return items_; }
    QString page() const { return page_; }

    void set_title(const QString& title);
    void set_page(const QString& page);
    void set_open_key(const QString& key);
    void set_zoomed(bool zoomed);
    void set_items(const QVariantList& items);
    void set_dark(bool dark);
    void bump_menu();

    Q_INVOKABLE void openStudio(const QString& studio_id);
    Q_INVOKABLE void dropUrls(const QVariantList& urls);
    Q_INVOKABLE void requestClose();
    Q_INVOKABLE void requestMin();
    Q_INVOKABLE void requestZoom();
    Q_INVOKABLE void startMove();
    Q_INVOKABLE void toggleMenu(const QString& key, double x, double y);
    Q_INVOKABLE void triggerItem(const QString& act_id);

signals:
    void changed();
    void menuOpened();
    void menuDismiss();
    void pageChanged(const QString& page);
    void menuRequested(const QString& key, int x, int y);
    void closeRequested();
    void minRequested();
    void zoomRequested();
    void moveRequested();
    void actionRequested(const QString& act_id);

private:
    QString title_ = QStringLiteral("Trainz Studio");
    QString open_key_;
    bool zoomed_ = false;
    int menu_gen_ = 0;
    QString page_ = QStringLiteral("home");
    QVariantList cards_;
    QVariantList menus_;
    QVariantList items_;
};

class LogoProvider : public QQuickImageProvider {
public:
    LogoProvider();
    QPixmap requestPixmap(const QString& id, QSize* size, const QSize& requested) override;
};

class ShellWindow : public QWidget {
    Q_OBJECT

public:
    explicit ShellWindow(QWidget* parent = nullptr, std::function<void(const QString&, int)> boot = {});
    ~ShellWindow() override;

    bool qmlReady() const;
    QString page() const;
    QStringList qmlErrors() const;
    void openStudio(const QString& studio_id);
    void triggerItem(const QString& act_id);
    // Rows the top-bar menu `key` shows on the current page (actId, label, shortcut, sep, checked, alive).
    QVariantList menuRows(const QString& key);
    // False when an action id names a bridge method the current page does not have.
    bool actionOk(const QString& act_id) const;

protected:
    bool eventFilter(QObject* watched, QEvent* event) override;
    void changeEvent(QEvent* event) override;
    bool nativeEvent(const QByteArray& eventType, void* message, qintptr* result) override;

private:
    void show_menu(const QString& key, int x, int y);
    void hide_menu();
    void begin_move();
    void fade_out(const QPixmap& snap);
    void fill_menu(const QString& key);
    void place_toast();
    void run_action(const QString& act_id);
    void open_any();
    void run_ve(const QString& mode);  // current · folder · fix · last
    QObject* page_bridge() const;
    QList<VeReport> ve_last_;
    QQuickWidget* load_quick(const QString& file, bool translucent);

    ShellBridge* bridge_ = nullptr;
    QQuickWidget* home_ = nullptr;
    QQuickWidget* title_ = nullptr;
    QQuickWidget* menu_ = nullptr;
    QQuickWidget* toast_ = nullptr;
    QQuickWidget* footer_ = nullptr;
    QStackedWidget* stack_ = nullptr;
    QLabel* blank_ = nullptr;
    QLabel* cover_ = nullptr;
    QPropertyAnimation* fade_ = nullptr;
    TrainzUtilPage* trainz_ = nullptr;
    EngineTunerPage* engine_ = nullptr;
    AssetsPage* assets_ = nullptr;
    SoundsPage* sounds_ = nullptr;
    MeshStudioPage* mesh_ = nullptr;
    QString engine_kuid_;
    std::function<void(const QString&, int)> boot_;
    bool moving_ = false;

    void boot_stage(const QString& text, int pct);
};

bool chrome_click_dismisses_menu(const QRect& menu, const QRect& title, const QPoint& global);

void prepare_qt_runtime();
