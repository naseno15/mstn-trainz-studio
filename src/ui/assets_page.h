#pragma once

#include "ui/status_hub.h"

#include <QByteArray>
#include <QDateTime>
#include <QList>
#include <QPointer>
#include <QString>
#include <QStringList>
#include <QWidget>

#include "ui/icons.h"

#include <vector>

#include "io/cdp.h"
#include "ui/texmesh.h"

class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QProcess;
class QPushButton;
class QQuickWidget;
class QStackedWidget;
class QTableWidget;
class QTextDocument;

struct AssetQueueItem {
    QString path;
    QString kind;
    QString size;
    QString info;
    QByteArray bytes;
    std::vector<CdpAssetEntry> assets;
};

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
    Q_PROPERTY(bool viewerExpanded READ viewerExpanded NOTIFY changed)
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
    Q_PROPERTY(QString queueJson READ queueJson NOTIFY changed)
    Q_PROPERTY(QString finderJson READ finderJson NOTIFY changed)
    Q_PROPERTY(QString finderMeta READ finderMeta NOTIFY changed)
    Q_PROPERTY(QString crumbsJson READ crumbsJson NOTIFY changed)
    Q_PROPERTY(bool finderFbx READ finderFbx NOTIFY changed)
    Q_PROPERTY(bool finderUpOn READ finderUpOn NOTIFY changed)
    Q_PROPERTY(QString previewBody READ previewBody NOTIFY changed)
    Q_PROPERTY(QString previewPlain READ previewPlain NOTIFY changed)
    Q_PROPERTY(QString previewImage READ previewImage NOTIFY changed)
    Q_PROPERTY(bool previewAudio READ previewAudio NOTIFY changed)
    Q_PROPERTY(bool previewOn READ previewOn NOTIFY changed)
    Q_PROPERTY(bool previewRich READ previewRich NOTIFY changed)
    Q_PROPERTY(int previewPt READ previewPt NOTIFY changed)
    Q_PROPERTY(QString configText READ configText WRITE setConfigText NOTIFY changed)
    Q_PROPERTY(QString kuidIn READ kuidIn WRITE setKuidIn NOTIFY changed)
    Q_PROPERTY(QString kuidOut READ kuidOut NOTIFY changed)
    Q_PROPERTY(QString exportIn READ exportIn WRITE setExportIn NOTIFY changed)
    Q_PROPERTY(QString exportJson READ exportJson NOTIFY changed)
    Q_PROPERTY(QString tableJson READ tableJson NOTIFY changed)
    Q_PROPERTY(QString paramQueueJson READ paramQueueJson NOTIFY changed)
    Q_PROPERTY(QString wellLeft READ wellLeft NOTIFY changed)
    Q_PROPERTY(QString wellRight READ wellRight NOTIFY changed)

public:
    explicit AssetsBridge(QObject* parent = nullptr);

    bool dark() const { return ui_dark(); }
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
    bool viewerExpanded() const { return viewer_expanded_; }
    QString viewTitle() const { return view_title_; }
    QString viewHint() const { return view_hint_; }
    int viewPane() const { return view_pane_; }
    bool viewEditor() const { return view_editor_; }
    QString viewFont() const { return QString::number(preview_pt_) + QStringLiteral(" pt"); }
    bool viewNested() const { return false; }
    bool viewSaveOn() const { return view_pane_ == 1 && view_editor_; }
    bool viewEngine() const;
    bool viewFast() const;
    bool viewMesh() const;
    QString viewEngineLabel() const { return QStringLiteral("Open in Engine Tuner"); }
    QString glyphBack() const { return material_glyph("arrow_back"); }
    QString glyphExpand() const { return material_glyph(viewer_expanded_ ? "fullscreen_exit" : "fullscreen"); }
    QString glyphSave() const { return material_glyph("save"); }
    QString glyphDelete() const { return material_glyph("delete"); }
    QString glyphFast() const { return material_glyph("swap_horiz"); }
    QString glyphMesh() const { return material_glyph("view_in_ar"); }
    QString glyphRepl() const { return material_glyph("swap_horiz"); }
    QString glyphFbx() const { return material_glyph("delete_sweep"); }
    QString viewTips() const {
        return QString::fromUtf8(
            "{\"smaller\":\"Smaller text (Ctrl+-)\",\"larger\":\"Larger text (Ctrl+=)\","
            "\"back\":\"Back to parent CDP\",\"expand\":\"Expand viewer - hide Finder (queue stays in sidebar)\","
            "\"saveText\":\"Save text...\",\"replace\":\"Replace this file...\",\"delete\":\"Delete\","
            "\"saveCdp\":\"Save CDP...\",\"fbx\":\"Delete all .fbx in this CDP...\","
            "\"fast\":\"Fast preview\",\"mesh\":\"Open in Mesh Studio\"}");
    }
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
    QString queueJson() const;
    QString finderJson() const { return finder_json_; }
    QString finderMeta() const { return finder_meta_; }
    QString crumbsJson() const { return crumbs_json_; }
    bool finderFbx() const { return finder_fbx_; }
    bool finderUpOn() const { return finder_asset_ >= 0 || finder_fbx_; }
    QString previewBody() const { return preview_body_; }
    QString previewPlain() const { return preview_plain_; }
    QString previewImage() const { return preview_image_url_; }
    bool previewAudio() const { return preview_audio_; }
    bool previewOn() const { return preview_on_; }
    bool previewRich() const { return preview_rich_; }
    int previewPt() const { return preview_pt_; }
    QString configText() const;
    void setConfigText(const QString& text);
    QString kuidIn() const;
    void setKuidIn(const QString& text);
    QString kuidOut() const;
    QString exportIn() const;
    void setExportIn(const QString& text);
    QString exportJson() const;
    QString tableJson() const;
    QString paramQueueJson() const;
    QString wellLeft() const;
    QString wellRight() const;

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
    Q_INVOKABLE void dropPaths(const QStringList& paths);
    Q_INVOKABLE void dropCenter(const QStringList& paths);
    Q_INVOKABLE void pickCenter(int row);
    Q_INVOKABLE void pickQueue(int row);
    Q_INVOKABLE void openFinder(int row);
    Q_INVOKABLE void pickFinder(int row);
    Q_INVOKABLE void finderUp();
    Q_INVOKABLE void jumpCrumb(int depth);
    Q_INVOKABLE void toggleFbx();
    Q_INVOKABLE void openFolder();
    Q_INVOKABLE void setFinderQuery(const QString& text);
    Q_INVOKABLE void setFinderSort(const QString& column);
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
    Q_INVOKABLE void setPreviewText(const QString& text);
    Q_INVOKABLE void attachEditor(QObject* quickDocument);
    Q_INVOKABLE void audioPlay();
    Q_INVOKABLE void audioStop();
    Q_INVOKABLE void viewerFont(int delta);
    Q_INVOKABLE void viewerBack();
    Q_INVOKABLE void viewerExpand();
    Q_INVOKABLE void viewerSave();
    Q_INVOKABLE void viewerEngine();
    void applyEngineText(const QString& text);
    Q_INVOKABLE void viewerFast();
    Q_INVOKABLE void viewerMesh();
    Q_INVOKABLE void viewerReplace();
    Q_INVOKABLE void viewerDelete();
    Q_INVOKABLE void viewerSaveCdp();
    Q_INVOKABLE void viewerDeleteFbx();
    Q_INVOKABLE void setFormTab(int tab);
    Q_INVOKABLE void setDockField(const QString& key, const QString& text);
    Q_INVOKABLE void runDock(const QString& id);
    Q_INVOKABLE QStringList veContextPaths() const;

signals:
    void changed();
    void homeRequested();
    void meshRequested(const QString& path);
    void engineRequested(const QString& text, const QString& label);
    void placeQueueRequested(int x, int y, int w, int h);
    void placeCenterRequested(int x, int y, int w, int h);
    void placePreviewRequested(int x, int y, int w, int h);

private:
    void build_tools(QWidget* host);
    void place_widget(QWidget* widget, int x, int y, int w, int h, bool show);
    void add_paths(const QStringList& paths);
    void refresh_queue();
    void select_queue(int row);
    void refresh_finder();
    void enter_finder(int row);
    void preview_file(int row);
    void apply_edited_bytes(std::vector<uint8_t> bytes);
    void clear_preview();
    QString stage_selected_asset();
    void sync_pages();
    void read_kuid_list();
    void start_export(bool one_file);
    void finish_export();
    void show_asset(int row);
    std::vector<uint8_t> bytes_;
    std::vector<CdpAssetEntry> assets_;
    std::vector<AssetQueueItem> queue_;
    int queue_row_ = -1;
    int finder_asset_ = -1;
    QStringList finder_parts_;
    int finder_sel_ = -1;
    bool finder_fbx_ = false;
    struct FinderShown {
        QString name;
        QString size_label;
        QString kind;
        QString detail;
        QString type_label;
        QString modified_label;
        QDateTime modified;
        QString badge;
        QString color;
        QString rel;
        int index = -1;
        qint64 bytes = -1;
    };
    std::vector<FinderShown> shown_;
    QString finder_sort_ = QStringLiteral("name");
    bool finder_sort_ascending_ = true;
    QString config_path_;
    QString tzarc_text_;
    QString export_exe_;
    QTableWidget* queue_table_ = nullptr;
    QWidget* finder_page_ = nullptr;
    QTableWidget* finder_table_ = nullptr;
    QLineEdit* finder_filter_ = nullptr;
    QPushButton* finder_up_ = nullptr;
    QStackedWidget* preview_ = nullptr;
    QLabel* preview_empty_ = nullptr;
    QLabel* preview_image_ = nullptr;
    QPlainTextEdit* preview_text_ = nullptr;
    QPlainTextEdit* config_edit_ = nullptr;
    QWidget* kuid_page_ = nullptr;
    QPlainTextEdit* kuid_in_ = nullptr;
    QPlainTextEdit* kuid_out_ = nullptr;
    QLabel* kuid_count_ = nullptr;
    QWidget* export_page_ = nullptr;
    QPlainTextEdit* export_in_ = nullptr;
    QTableWidget* export_table_ = nullptr;
    QLabel* export_count_ = nullptr;
    QProcess* export_proc_ = nullptr;
    QStringList export_dest_;
    QList<QStringList> export_kuids_;
    QList<int> export_rows_;
    int export_at_ = 0;
    int queue_at_[4] = {};
    int center_at_[4] = {};
    int preview_at_[4] = {};
    QString path_;
    QString suite_ = QStringLiteral("assets");
    QString page_ = QStringLiteral("packages");
    QString page_title_ = QStringLiteral("Packages");
    QString center_title_ = QStringLiteral("Packages");
    QString center_tip_ = QStringLiteral("Open a CDP. The table lists assets. The dock lists files.");
    QString foot_note_ = QStringLiteral("Packages reads a CDP and extracts its files.");
    QString view_title_ = QStringLiteral("Viewer");
    QString view_hint_;
    QString finder_json_ = QStringLiteral("[]");
    QString finder_meta_;
    QString crumbs_json_ = QStringLiteral("[]");
    QString preview_body_;
    bool preview_on_ = false;
    bool preview_rich_ = false;
    int preview_pt_ = 10;
    int view_pane_ = 0;
    bool view_editor_ = false;
    QString preview_plain_;
    QString preview_name_;
    QString preview_image_url_;
    QString preview_audio_path_;
    bool preview_audio_ = false;
    QPointer<QTextDocument> editor_document_;
    int side_w_ = 380;
    int dock_w_ = 560;
    int asset_row_ = -1;
    bool viewer_on_ = true;
    bool viewer_expanded_ = false;
    bool cdp_dirty_ = false;
    bool last_edit_committed_ = true;
    Texmesh* tex_ = nullptr;
};

class AssetsPage : public QWidget {
    Q_OBJECT

public:
    explicit AssetsPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadBytes(const QByteArray& bytes, const QString& path);
    void openPaths(const QStringList& paths);
    int assetCount() const;
    QString cell(int row, int column) const;
    QString fileText(int asset, const QString& rel) const;
    int extractTo(const QString& directory) const;
    QString pageName() const;
    bool formOn() const;
    QString centerList() const;
    void setPage(const QString& page);
    void setSuite(const QString& suite);
    void applyEngineText(const QString& text);

signals:
    void homeRequested();
    void meshRequested(const QString& path);
    void engineRequested(const QString& text, const QString& label);

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    AssetsBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
