#pragma once

#include "ui/status_hub.h"

#include "io/trainzmesh.h"

#include <QElapsedTimer>
#include <QByteArray>
#include <QImage>
#include <QString>

#include "io/trainzmesh.h"
#include <vector>
#include <QStringList>
#include <QVariant>
#include <QVariantList>
#include <QWidget>
#include <QtGlobal>

class MeshView;
class QQuickWidget;

struct MatEdit {
    TzMaterial block;
    bool two = false;
    int gizmo = -1;
};

struct MeshRow {
    QString name;
    QString material;
    QString albedo;
    QString tex_file;
    QString format;
    int verts = 0;
    int tris = 0;
    size_t tail = 0;
    bool show = true;
    bool atts = true;
    bool open = false;
    bool two = false;
};

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
    Q_PROPERTY(bool faceOn MEMBER face_ NOTIFY changed)
    Q_PROPERTY(bool groundOn MEMBER ground_ NOTIFY changed)
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
    Q_PROPERTY(bool loadOpen READ loadOpen NOTIFY changed)
    Q_PROPERTY(int loadPct READ loadPct NOTIFY changed)
    Q_PROPERTY(QString loadStage READ loadStage NOTIFY changed)
    Q_PROPERTY(QString loadName READ loadName NOTIFY changed)
    Q_PROPERTY(QStringList pbrLabels READ pbrLabels NOTIFY changed)
    Q_PROPERTY(bool pieOpen READ pieOpen NOTIFY changed)
    Q_PROPERTY(QString pieTitle READ pieTitle NOTIFY changed)
    Q_PROPERTY(QStringList pieLabels READ pieLabels NOTIFY changed)
    Q_PROPERTY(int pieHover READ pieHover NOTIFY changed)
    Q_PROPERTY(qreal pieX READ pieX NOTIFY changed)
    Q_PROPERTY(qreal pieY READ pieY NOTIFY changed)

public:
    explicit MeshBridge(QObject* parent = nullptr);

    bool dark() const { return ui_dark(); }
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
    QString welcomeBody() const { return QStringLiteral("Open a .trainzmesh, .im, or .fbx file"); }
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
    bool loadOpen() const { return load_open_; }
    int loadPct() const { return load_pct_; }
    int loadSteps() const { return load_steps_; }
    QString loadStage() const { return load_stage_; }
    QString loadName() const { return load_name_; }
    QStringList pbrLabels() const;
    bool pieOpen() const { return pie_open_; }
    QString pieTitle() const;
    QStringList pieLabels() const;
    int pieHover() const { return pie_hover_; }
    qreal pieX() const { return pie_x_; }
    qreal pieY() const { return pie_y_; }

    void attach(MeshView* view, QWidget* chrome);
    void reveal_view();
    void load_file(const QString& path);
    // Preview Asset: every mesh of an asset tree in one scene, all at the origin.
    void load_scene(const QStringList& paths, const QStringList& labels, const QList<double>& yaws);

    Q_INVOKABLE void setPage(const QString& page);
    Q_INVOKABLE void goHome();
    Q_INVOKABLE void browse();
    Q_INVOKABLE void openFixture();
    Q_INVOKABLE QStringList veContextPaths() const;
    Q_INVOKABLE void dropUrls(const QVariantList& urls);
    Q_INVOKABLE void noteChrome(const QVariant& rects);
    Q_INVOKABLE void setPbr(int index);
    Q_INVOKABLE void pieHoverAt(qreal x, qreal y);
    Q_INVOKABLE void commitPie();
    Q_INVOKABLE void cancelPie();
    void armPie(qreal x, qreal y);
    void releasePie(qint64 held_ms);
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
    void sync_highlight();
    void focus_selection();
    void report_load(const QString& stage, int pct);
    bool welcome_ = true;
    bool editor_open_ = false;
    int pbr_ = 0;
    int tab_ = 0;
    QString page_ = QStringLiteral("preview");
    QString path_;
    QList<bool> file_shows_, file_attl_;  // per scene file (parallel to scene_paths_)
    QList<int> part_file_;                // file index of every row in rows_
    int sel_file_ = 0;
    QStringList scene_paths_;  // every file currently in the scene (drops append to this)
    QByteArray file_bytes_;
    bool dirty_ = false;
    QString tip_;
    QString shortcut_;
    QString side_json_ = QStringLiteral(R"({"tab":0,"tabs":["Scene","Mat","Lamps","Motion","Lights"],"meshes":[]})");
    QString dock_json_ = QStringLiteral(R"({"mode":"meshes","title":"","mat":{"on":false,"name":"","types":[],"tex":[],"two":false,"spec":0},"att":{"name":"","parent":"","loc":[0,0,0],"rot":[0,0,0,1]}})");
    std::vector<MeshRow> rows_;
    std::vector<MatEdit> mats_;
    std::vector<int> mat_owner_;
    int selected_ = 0;
    int mat_i_ = 0;
    bool file_show_ = true;
    bool file_atts_ = true;
    bool bounds_set_ = false;
    float bmin_[3] = {};
    float bmax_[3] = {};
    int anims_ = 0;
    int att_count_ = 0;
    bool info_open_ = true;
    bool two_sided_ = false;
    bool face_ = false;
    MeshView* view_ = nullptr;
    QRect blur_side_;
    QRect blur_editor_;
    QWidget* chrome_ = nullptr;
    int env_i_ = 0;
    bool sun_ = true;
    bool moon_ = false;
    int tod_ = 1;
    int sun_az_ = 135;
    int sun_el_ = 45;
    int sun_int_ = 140;
    int emis_ = 15;
    bool array_on_[5] = {true, true, true, true, true};
    bool ground_ = false;
    bool loading_ = false;
    bool scene_ = false;  // Preview Asset scene: many files, no single path
    bool load_open_ = false;
    int load_pct_ = 0;
    int load_steps_ = 0;
    QString load_stage_;
    QString load_name_;
    bool pie_open_ = false;
    bool pie_sticky_ = false;
    int pie_hover_ = 3;
    qreal pie_x_ = 0;
    qreal pie_y_ = 0;
    int shade_ = 3;
    int tool_ = 1;
    bool editor_pie() const;
    void cover_pie();
};

int pie_sector(float dx, float dy, int count, int keep);

class MeshStudioPage : public QWidget {
    Q_OBJECT

public:
    explicit MeshStudioPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadFile(const QString& path);
    void loadScene(const QStringList& paths, const QStringList& labels, const QList<double>& yaws);
    bool loadOpen() const;
    int loadSteps() const;
    QString sideJson() const;
    QImage grabView();
    bool pieOpen() const;

signals:
    void homeRequested();

protected:
    void resizeEvent(QResizeEvent* event) override;
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    bool filter_tab(QEvent* event);
    bool text_has_tab() const;

    MeshBridge* bridge_ = nullptr;
    MeshView* gl_ = nullptr;
    QQuickWidget* view_ = nullptr;
    QElapsedTimer tab_clock_;
};
