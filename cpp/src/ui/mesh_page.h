#pragma once

#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QWidget>

class MeshView;
class QQuickWidget;

class MeshBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(bool mesh READ mesh NOTIFY changed)
    Q_PROPERTY(bool welcome READ welcome NOTIFY changed)
    Q_PROPERTY(bool sideOpen READ sideOpen NOTIFY changed)
    Q_PROPERTY(bool editorOpen READ editorOpen NOTIFY changed)
    Q_PROPERTY(bool settingsOpen READ settingsOpen NOTIFY changed)
    Q_PROPERTY(bool pbrOn READ pbrOn NOTIFY changed)
    Q_PROPERTY(bool bakeOn READ bakeOn NOTIFY changed)
    Q_PROPERTY(int pbr READ pbr NOTIFY changed)
    Q_PROPERTY(int bakePct READ bakePct NOTIFY changed)
    Q_PROPERTY(QString page READ page NOTIFY changed)
    Q_PROPERTY(QString sideJson READ sideJson NOTIFY changed)
    Q_PROPERTY(QString dockJson READ dockJson NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString iconFontUrl READ iconFontUrl NOTIFY changed)
    Q_PROPERTY(QString welcomeTitle READ welcomeTitle NOTIFY changed)
    Q_PROPERTY(QString welcomeBody READ welcomeBody NOTIFY changed)
    Q_PROPERTY(QString openLabel READ openLabel NOTIFY changed)
    Q_PROPERTY(QString fixtureLabel READ fixtureLabel NOTIFY changed)
    Q_PROPERTY(QString homeLabel READ homeLabel NOTIFY changed)
    Q_PROPERTY(QString tip READ tip NOTIFY changed)
    Q_PROPERTY(QString copy READ copy NOTIFY changed)
    Q_PROPERTY(QString shortcut READ shortcut NOTIFY changed)
    Q_PROPERTY(QString preview READ preview NOTIFY changed)
    Q_PROPERTY(QString meshes READ meshes NOTIFY changed)
    Q_PROPERTY(QString attachs READ attachs NOTIFY changed)
    Q_PROPERTY(QString settingsLabel READ settingsLabel NOTIFY changed)
    Q_PROPERTY(QString homeGlyph READ homeGlyph NOTIFY changed)
    Q_PROPERTY(QString openGlyph READ openGlyph NOTIFY changed)
    Q_PROPERTY(QString folderGlyph READ folderGlyph NOTIFY changed)
    Q_PROPERTY(QString saveGlyph READ saveGlyph NOTIFY changed)
    Q_PROPERTY(QString closeGlyph READ closeGlyph NOTIFY changed)
    Q_PROPERTY(QString bakeStage READ bakeStage NOTIFY changed)
    Q_PROPERTY(QString bakeEta READ bakeEta NOTIFY changed)
    Q_PROPERTY(QStringList pbrLabels READ pbrLabels NOTIFY changed)

public:
    explicit MeshBridge(QObject* parent = nullptr);

    bool dark() const { return true; }
    bool mesh() const { return true; }
    bool welcome() const { return welcome_; }
    bool sideOpen() const { return true; }
    bool editorOpen() const { return editor_open_; }
    bool settingsOpen() const { return page_ == QLatin1String("settings"); }
    bool pbrOn() const { return !welcome_; }
    bool bakeOn() const { return false; }
    int pbr() const { return pbr_; }
    int bakePct() const { return 0; }
    QString page() const { return page_; }
    QString sideJson() const { return side_json_; }
    QString dockJson() const { return dock_json_; }
    QString iconFont() const;
    QString iconFontUrl() const;
    QString welcomeTitle() const { return QStringLiteral("Mesh Studio"); }
    QString welcomeBody() const { return QStringLiteral("Open a .trainzmesh or .im file"); }
    QString openLabel() const { return QStringLiteral("Open mesh…"); }
    QString fixtureLabel() const { return QStringLiteral("Open sample mesh"); }
    QString homeLabel() const { return QStringLiteral("Home"); }
    QString tip() const { return tip_; }
    QString copy() const { return QStringLiteral("Copyright MSTN Production"); }
    QString shortcut() const { return shortcut_; }
    QString preview() const { return QStringLiteral("Preview"); }
    QString meshes() const { return QStringLiteral("Meshes Editor"); }
    QString attachs() const { return QStringLiteral("Attachs Editor"); }
    QString settingsLabel() const { return QStringLiteral("Settings"); }
    QString homeGlyph() const;
    QString openGlyph() const;
    QString folderGlyph() const;
    QString saveGlyph() const;
    QString closeGlyph() const;
    QString bakeStage() const { return {}; }
    QString bakeEta() const { return {}; }
    QStringList pbrLabels() const;

    void attach(MeshView* view, QWidget* chrome);
    void reveal_view();
    void load_file(const QString& path);

    Q_INVOKABLE void setPage(const QString& page);
    Q_INVOKABLE void goHome();
    Q_INVOKABLE void browse();
    Q_INVOKABLE void openFixture();
    Q_INVOKABLE void dropUrls(const QVariantList& urls);
    Q_INVOKABLE void noteChrome(const QVariantList& rects);
    Q_INVOKABLE void setPbr(int index);
    Q_INVOKABLE void setSideTab(int index);
    Q_INVOKABLE void clickId(const QString& id);
    Q_INVOKABLE void setChecked(const QString& key, bool on);
    Q_INVOKABLE void setCombo(const QString& key, int index);
    Q_INVOKABLE void setText(const QString& key, const QString& text);
    Q_INVOKABLE void setSpin(const QString& key, double value);
    Q_INVOKABLE void setSlider(const QString& key, int value);
    Q_INVOKABLE void setChannel(const QString& which, int index, double value);
    Q_INVOKABLE void pickList(const QString& list, int index);
    Q_INVOKABLE void pickMat(int index);
    Q_INVOKABLE void toggleMesh(int index, int column);
    Q_INVOKABLE void toggleSceneMesh(int index);
    Q_INVOKABLE void cancelBake();
    Q_INVOKABLE void placeSide(double x, double y, double w, double h);
    Q_INVOKABLE void placeEditor(double x, double y, double w, double h);
    Q_INVOKABLE void placeSettings(double x, double y, double w, double h);

signals:
    void changed();
    void homeRequested();

private:
    void publish();
    bool welcome_ = true;
    bool editor_open_ = false;
    int pbr_ = 0;
    int tab_ = 0;
    QString page_ = QStringLiteral("preview");
    QString path_;
    QString tip_;
    QString shortcut_;
    QString side_json_ = QStringLiteral(R"({"tab":0,"tabs":["Scene","Mat","Lamps","Motion","Lights"],"meshes":[]})");
    QString dock_json_ = QStringLiteral(R"({"title":"","mat":{"on":false,"name":"","types":[],"tex":[],"two":false,"spec":0},"att":{"name":"","parent":"","loc":[0,0,0],"rot":[0,0,0,1]}})");
    QStringList mesh_names_;
    MeshView* view_ = nullptr;
    QWidget* chrome_ = nullptr;
    int env_i_ = 0;
    bool sun_ = false;
    bool ground_ = false;
};

class MeshStudioPage : public QWidget {
    Q_OBJECT

public:
    explicit MeshStudioPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadFile(const QString& path);
    QString sideJson() const;

signals:
    void homeRequested();

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    MeshBridge* bridge_ = nullptr;
    MeshView* gl_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
