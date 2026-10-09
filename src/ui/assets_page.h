#pragma once

#include <QString>
#include <QStringList>
#include <QWidget>

#include "ui/icons.h"

#include <vector>

#include "io/cdp.h"
#include "ui/texmesh.h"

class QQuickWidget;

class AssetsBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(QString suite READ suite NOTIFY changed)
    Q_PROPERTY(QString page READ page NOTIFY changed)
    Q_PROPERTY(int sideW READ sideW NOTIFY changed)
    Q_PROPERTY(bool dockOn READ dockOn NOTIFY changed)
    Q_PROPERTY(int dockW READ dockW NOTIFY changed)
    Q_PROPERTY(bool navTall READ navTall NOTIFY changed)
    Q_PROPERTY(bool showQueue READ showQueue NOTIFY changed)
    Q_PROPERTY(QString brand READ brand NOTIFY changed)
    Q_PROPERTY(QString pageTitle READ pageTitle NOTIFY changed)
    Q_PROPERTY(QString blurb READ blurb NOTIFY changed)
    Q_PROPERTY(QString actionsJson READ actionsJson NOTIFY changed)
    Q_PROPERTY(QString footerJson READ footerJson NOTIFY changed)
    Q_PROPERTY(QString queueBtnJson READ queueBtnJson NOTIFY changed)
    Q_PROPERTY(QString leftNavJson READ leftNavJson NOTIFY changed)
    Q_PROPERTY(QString rightNavJson READ rightNavJson NOTIFY changed)
    Q_PROPERTY(QString footerCap READ footerCap NOTIFY changed)
    Q_PROPERTY(QString footNote READ footNote NOTIFY changed)
    Q_PROPERTY(QString homeLabel READ homeLabel NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString iconFontUrl READ iconFontUrl NOTIFY changed)
    Q_PROPERTY(bool viewerOn READ viewerOn NOTIFY changed)
    Q_PROPERTY(QString viewTitle READ viewTitle NOTIFY changed)
    Q_PROPERTY(QString viewHint READ viewHint NOTIFY changed)
    Q_PROPERTY(int viewPane READ viewPane NOTIFY changed)
    Q_PROPERTY(bool viewEditor READ viewEditor NOTIFY changed)
    Q_PROPERTY(QString viewFont READ viewFont NOTIFY changed)
    Q_PROPERTY(bool viewNested READ viewNested NOTIFY changed)
    Q_PROPERTY(bool viewSaveOn READ viewSaveOn NOTIFY changed)
    Q_PROPERTY(bool viewEngine READ viewEngine NOTIFY changed)
    Q_PROPERTY(bool viewFast READ viewFast NOTIFY changed)
    Q_PROPERTY(bool viewMesh READ viewMesh NOTIFY changed)
    Q_PROPERTY(QString viewEngineLabel READ viewEngineLabel NOTIFY changed)
    Q_PROPERTY(QString glyphBack READ glyphBack NOTIFY changed)
    Q_PROPERTY(QString glyphExpand READ glyphExpand NOTIFY changed)
    Q_PROPERTY(QString glyphSave READ glyphSave NOTIFY changed)
    Q_PROPERTY(QString glyphDelete READ glyphDelete NOTIFY changed)
    Q_PROPERTY(QString glyphFast READ glyphFast NOTIFY changed)
    Q_PROPERTY(QString glyphMesh READ glyphMesh NOTIFY changed)
    Q_PROPERTY(QString glyphRepl READ glyphRepl NOTIFY changed)
    Q_PROPERTY(QString glyphFbx READ glyphFbx NOTIFY changed)
    Q_PROPERTY(QString viewTips READ viewTips NOTIFY changed)
    Q_PROPERTY(bool formOn READ formOn NOTIFY changed)
    Q_PROPERTY(QString formTitle READ formTitle NOTIFY changed)
    Q_PROPERTY(QString formTabs READ formTabs NOTIFY changed)
    Q_PROPERTY(int formTab READ formTab NOTIFY changed)
    Q_PROPERTY(bool formTool READ formTool NOTIFY changed)
    Q_PROPERTY(QString formBlocks READ formBlocks NOTIFY changed)
    Q_PROPERTY(QString centerTitle READ centerTitle NOTIFY changed)
    Q_PROPERTY(QString centerTip READ centerTip NOTIFY changed)
    Q_PROPERTY(QString centerKind READ centerKind NOTIFY changed)
    Q_PROPERTY(QString centerList READ centerList NOTIFY changed)
    Q_PROPERTY(QString centerPrev READ centerPrev NOTIFY changed)
    Q_PROPERTY(QString glyphRefresh READ glyphRefresh NOTIFY changed)

public:
    explicit AssetsBridge(QObject* parent = nullptr);

    bool dark() const { return true; }
    QString suite() const { return suite_; }
    QString page() const { return page_; }
    int sideW() const { return side_w_; }
    bool dockOn() const { return suite_ == QLatin1String("texmesh") || viewer_on_; }
    int dockW() const { return dock_w_; }
    bool navTall() const { return suite_ == QLatin1String("texmesh"); }
    bool showQueue() const;
    QString brand() const;
    QString pageTitle() const { return page_title_; }
    QString blurb() const;
    QString actionsJson() const;
    QString footerJson() const;
    QString queueBtnJson() const;
    QString leftNavJson() const;
    QString rightNavJson() const;
    QString footerCap() const;
    QString footNote() const;
    QString homeLabel() const { return material_glyph("home"); }
    QString iconFont() const { return material_icon_family(); }
    QString iconFontUrl() const { return material_icon_url(); }
    bool viewerOn() const { return viewer_on_; }
    QString viewTitle() const { return view_title_; }
    QString viewHint() const { return view_hint_; }
    int viewPane() const { return 0; }
    bool viewEditor() const { return false; }
    QString viewFont() const { return QStringLiteral("10 pt"); }
    bool viewNested() const { return false; }
    bool viewSaveOn() const { return false; }
    bool viewEngine() const { return false; }
    bool viewFast() const { return false; }
    bool viewMesh() const { return false; }
    QString viewEngineLabel() const { return {}; }
    QString glyphBack() const { return material_glyph("arrow_back"); }
    QString glyphExpand() const { return material_glyph("fullscreen"); }
    QString glyphSave() const { return material_glyph("save"); }
    QString glyphDelete() const { return material_glyph("delete"); }
    QString glyphFast() const { return material_glyph("swap_horiz"); }
    QString glyphMesh() const { return material_glyph("view_in_ar"); }
    QString glyphRepl() const { return material_glyph("swap_horiz"); }
    QString glyphFbx() const { return material_glyph("delete_sweep"); }
    QString viewTips() const { return QStringLiteral("{}"); }
    bool formOn() const;
    QString formTitle() const;
    QString formTabs() const;
    int formTab() const;
    bool formTool() const;
    QString formBlocks() const;
    QString centerTitle() const { return center_title_; }
    QString centerTip() const { return center_tip_; }
    QString centerKind() const;
    QString centerList() const;
    QString centerPrev() const;
    QString glyphRefresh() const { return material_glyph("refresh"); }

    void set_suite(const QString& suite);
    void load_bytes(const QByteArray& bytes, const QString& path);
    int asset_count() const { return static_cast<int>(assets_.size()); }
    QString cell(int row, int column) const;
    QString file_text(int asset, const QString& rel) const;
    QStringList files_of(int asset) const;
    int extract_to(const QString& directory) const;

    Q_INVOKABLE void setPage(const QString& page);
    Q_INVOKABLE void goHome();
    Q_INVOKABLE void setSideW(double width);
    Q_INVOKABLE void setDockW(double width);
    Q_INVOKABLE void runAction(const QString& action);
    Q_INVOKABLE void queueClear();
    Q_INVOKABLE void queueRemove();
    Q_INVOKABLE void placeQueue(double x, double y, double w, double h);
    Q_INVOKABLE void placeCenter(double x, double y, double w, double h);
    Q_INVOKABLE void placeDock(double x, double y, double w, double h);
    Q_INVOKABLE void placePreview(double x, double y, double w, double h);
    Q_INVOKABLE void placeFormTool(double x, double y, double w, double h);
    Q_INVOKABLE void placeWell(const QString& key, double x, double y, double w, double h);
    Q_INVOKABLE void refreshCenter();
    Q_INVOKABLE void setViewerPane(int pane);
    Q_INVOKABLE void viewerFont(int delta);
    Q_INVOKABLE void viewerBack();
    Q_INVOKABLE void viewerExpand();
    Q_INVOKABLE void viewerSave();
    Q_INVOKABLE void viewerEngine();
    Q_INVOKABLE void viewerFast();
    Q_INVOKABLE void viewerMesh();
    Q_INVOKABLE void viewerReplace();
    Q_INVOKABLE void viewerDelete();
    Q_INVOKABLE void viewerSaveCdp();
    Q_INVOKABLE void viewerDeleteFbx();
    Q_INVOKABLE void setFormTab(int tab);
    Q_INVOKABLE void setDockField(const QString& key, const QString& text);
    Q_INVOKABLE void runDock(const QString& id);

signals:
    void changed();
    void homeRequested();
    void placeQueueRequested(int x, int y, int w, int h);
    void placeCenterRequested(int x, int y, int w, int h);
    void placePreviewRequested(int x, int y, int w, int h);

private:
    void show_asset(int row);
    std::vector<uint8_t> bytes_;
    std::vector<CdpAssetEntry> assets_;
    QString path_;
    QString suite_ = QStringLiteral("assets");
    QString page_ = QStringLiteral("packages");
    QString page_title_ = QStringLiteral("Packages");
    QString center_title_ = QStringLiteral("Packages");
    QString center_tip_ = QStringLiteral("Open a CDP. The table lists assets. The dock lists files.");
    QString foot_note_ = QStringLiteral("Packages reads a CDP and extracts its files.");
    QString view_title_ = QStringLiteral("Viewer");
    QString view_hint_;
    int side_w_ = 380;
    int dock_w_ = 420;
    int asset_row_ = -1;
    bool viewer_on_ = false;
    Texmesh* tex_ = nullptr;
};

class AssetsPage : public QWidget {
    Q_OBJECT

public:
    explicit AssetsPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadBytes(const QByteArray& bytes, const QString& path);
    int assetCount() const;
    QString cell(int row, int column) const;
    QString fileText(int asset, const QString& rel) const;
    int extractTo(const QString& directory) const;
    QString pageName() const;
    bool formOn() const;
    QString centerList() const;
    void setPage(const QString& page);
    void setSuite(const QString& suite);

signals:
    void homeRequested();

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    AssetsBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
