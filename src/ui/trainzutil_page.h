#pragma once

#include "ui/status_hub.h"

#include <memory>

#include <QAbstractListModel>
#include <QHash>
#include <QSet>
#include <QStringList>
#include <QVariantList>
#include <QWidget>

#include "io/config_id.h"
#include "ui/install_queue.h"
#include "ui/trainz_meta.h"

class QQuickWidget;

struct TrainzScanGate;

QString find_trainzutil(const QString& saved);
QString trainzutil_under_common(const QString& common_dir);

struct LibraryAsset {
    QString name;
    QString kuid;
    QString author;
    QString build;
    QString category;
    QString flags;
    bool faulty = false;
    bool missing = false;
};

QList<LibraryAsset> parse_installed_library(const QString& text);
QString parse_installation_data_path(const QString& text);

struct AssetDates {
    QHash<QString, qint64> installed;
    QHash<QString, qint64> modified;
    QHash<QString, qint64> editing;
    QHash<QString, qint64> sizes;
};

AssetDates read_asset_dates(const ContentIndex& index);

class LibraryList : public QAbstractListModel {
    Q_OBJECT

public:
    explicit LibraryList(QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    void add(const LibraryAsset& asset);
    void replace(const QList<LibraryAsset>& assets);
    void set_dates(const AssetDates& dates);
    void merge_meta(const QHash<QString, AssetMeta>& meta);
    void set_owners(const QHash<qint64, QString>& owners);
    void set_scope(const QStringList& kuids, const QString& title);
    void pop_scope();
    bool scoped() const { return !scopes_.isEmpty(); }
    QString scope_title() const { return scopes_.isEmpty() ? QString() : scopes_.last().title; }
    void set_credits(const QString& kuid, const QString& text);
    void set_size(const QString& kuid, const QString& text);
    int count() const { return shown_.size(); }
    int total() const { return all_.size(); }
    int author_count() const { return authors_.size(); }
    QString cell(int row, int column) const;
    void filter(const QString& query);
    void sort_by(const QString& key);
    QString sort_mark() const;
    QString summary() const;
    int index_of(const QString& kuid) const;
    bool contains(const QString& kuid) const;
    void toggle_pick(const QString& kuid);
    void click_pick(const QString& kuid, bool shift, bool ctrl);
    void begin_drag_pick(const QString& kuid);
    void drag_pick(const QString& kuid);
    void end_drag_pick();
    void set_visible_picked(bool on);
    QStringList selected_kuids() const;
    QString name_for(const QString& kuid) const;
    QString flags_for(const QString& kuid) const;
    QString tuner_kuid() const;
    QVariantMap card(const QString& kuid, const QString& note) const;

signals:
    void picksChanged();

private:
    const LibraryAsset* find(const QString& kuid) const;
    QString author(const LibraryAsset& row) const;
    QString build(const LibraryAsset& row) const;
    QStringList bits(const LibraryAsset& row) const;
    qint64 modified_at(const QString& kuid) const;
    QString packed_label(const QString& kuid) const;
    QStringList credit_parts(const QString& kuid) const;
    bool matches(const LibraryAsset& row, const QStringList& words) const;
    void touch(const QString& kuid, const QList<int>& roles);
    void touch_all(const QList<int>& roles);
    void paint_drag(const QString& kuid);
    void rebuild();
    void add_ghosts();

    QList<LibraryAsset> all_;
    QList<int> shown_;
    QString query_;
    QString sort_key_ = QStringLiteral("modified");
    bool sort_desc_ = true;
    QHash<QString, qint64> installed_;
    QHash<QString, qint64> modified_;
    QHash<QString, qint64> editing_;
    QHash<QString, qint64> file_sizes_;
    QHash<QString, QString> measured_;
    QHash<QString, QString> credits_;
    QHash<QString, QString> authors_;
    QHash<qint64, QString> owners_;
    struct Scope {
        QSet<QString> kuids;
        QString title;
        QSet<QString> picks_before;
    };
    QList<Scope> scopes_;
    QHash<QString, QString> builds_;
    QHash<QString, QString> disk_names_;
    QSet<QString> picked_;
    QSet<QString> drag_snapshot_;
    QString click_anchor_;
    QString drag_anchor_;
    bool drag_on_ = true;
};

struct TuJob {
    QString id;
    QString label;
    QString kind;
    QString detail;
    bool can_install = false;
    QString source;
    QString member;
    QStringList chain;
    QString asset_kuid;
    bool checked = false;
};

QList<TuJob> scan_package(const QString& path, const QStringList& chain = {});

class TrainzUtilBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(bool launcherOk READ launcherOk NOTIFY changed)
    Q_PROPERTY(QString launcherText READ launcherText NOTIFY changed)
    Q_PROPERTY(QString utilPath READ utilPath NOTIFY changed)
    Q_PROPERTY(QString crumb READ crumb NOTIFY changed)
    Q_PROPERTY(QString statusText READ statusText NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString page READ page NOTIFY changed)
    Q_PROPERTY(bool libraryOn READ libraryOn NOTIFY changed)
    Q_PROPERTY(QString backupQuery READ backupQuery NOTIFY changed)
    Q_PROPERTY(QString backupSummary READ backupSummary NOTIFY changed)
    Q_PROPERTY(QString backupPick READ backupPick NOTIFY changed)
    Q_PROPERTY(QString librarySummary READ librarySummary NOTIFY changed)
    Q_PROPERTY(QString sortMark READ sortMark NOTIFY changed)
    Q_PROPERTY(bool scopeOn READ scopeOn NOTIFY changed)
    Q_PROPERTY(QObject* libraryModel READ libraryModel CONSTANT)
    Q_PROPERTY(QString glyphHome READ glyphHome NOTIFY changed)
    Q_PROPERTY(QString glyphFolder READ glyphFolder NOTIFY changed)
    Q_PROPERTY(QString glyphRefresh READ glyphRefresh NOTIFY changed)
    Q_PROPERTY(QString glyphAssets READ glyphAssets NOTIFY changed)
    Q_PROPERTY(QString glyphSearch READ glyphSearch NOTIFY changed)
    Q_PROPERTY(QString glyphHistory READ glyphHistory NOTIFY changed)
    Q_PROPERTY(QString glyphEdit READ glyphEdit NOTIFY changed)
    Q_PROPERTY(QString glyphPublish READ glyphPublish NOTIFY changed)
    Q_PROPERTY(QString glyphCheck READ glyphCheck NOTIFY changed)
    Q_PROPERTY(QString glyphChevronLeft READ glyphChevronLeft NOTIFY changed)
    Q_PROPERTY(QString glyphChevronRight READ glyphChevronRight NOTIFY changed)
    Q_PROPERTY(QString glyphClose READ glyphClose NOTIFY changed)
    Q_PROPERTY(QString glyphCopy READ glyphCopy NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString reportText READ reportText NOTIFY changed)
    Q_PROPERTY(bool reportOn READ reportOn NOTIFY changed)
    Q_PROPERTY(bool detailOn READ detailOn NOTIFY changed)
    Q_PROPERTY(QString detailKuid READ detailKuid NOTIFY changed)
    Q_PROPERTY(QString detailTitle READ detailTitle NOTIFY changed)
    Q_PROPERTY(QVariantList detailDeps READ detailDeps NOTIFY changed)
    Q_PROPERTY(QVariantList detailStatus READ detailStatus NOTIFY changed)
    Q_PROPERTY(QVariantList detailCards READ detailCards NOTIFY changed)
    Q_PROPERTY(QString coverUrl READ coverUrl NOTIFY changed)
    Q_PROPERTY(bool coverBusy READ coverBusy NOTIFY changed)
    Q_PROPERTY(QString taskSummary READ taskSummary NOTIFY changed)
    Q_PROPERTY(int taskPercent READ taskPercent NOTIFY changed)
    Q_PROPERTY(bool taskBusy READ taskBusy NOTIFY changed)
    Q_PROPERTY(bool loadOn READ loadOn NOTIFY changed)
    Q_PROPERTY(QString loadDetail READ loadDetail NOTIFY changed)
    Q_PROPERTY(QString loadLog READ loadLog NOTIFY changed)

public:
    explicit TrainzUtilBridge(LibraryList* library, InstallQueue* queue, QObject* parent = nullptr);

    bool dark() const { return ui_dark(); }
    bool launcherOk() const { return launcher_ok_; }
    QString launcherText() const { return launcher_text_; }
    QString utilPath() const { return util_path_; }
    QString crumb() const { return crumb_; }
    QString statusText() const { return status_text_; }
    QString iconFont() const;
    QString page() const { return page_; }
    bool libraryOn() const { return page_ == QLatin1String("library"); }
    QString backupQuery() const { return backup_query_; }
    QString backupSummary() const { return backup_summary_; }
    QString backupPick() const { return backup_pick_; }
    QString librarySummary() const { return library_summary_; }
    QString sortMark() const { return library_->sort_mark(); }
    bool scopeOn() const { return library_->scoped(); }
    QObject* libraryModel() const { return library_; }
    QString glyphHome() const;
    QString glyphFolder() const;
    QString glyphRefresh() const;
    QString glyphAssets() const;
    QString glyphSearch() const;
    QString glyphHistory() const;
    QString glyphEdit() const;
    QString glyphPublish() const;
    QString glyphCheck() const;
    QString glyphChevronLeft() const;
    QString glyphChevronRight() const;
    QString glyphClose() const;
    QString glyphCopy() const;
    bool busy() const { return fill_library_ || fill_dates_ || fill_meta_; }
    QString reportText() const { return report_text_; }
    bool reportOn() const { return !report_text_.trimmed().isEmpty(); }
    bool detailOn() const { return detail_on_; }
    QString detailKuid() const { return detail_kuid_; }
    QString detailTitle() const { return detail_title_; }
    QVariantList detailDeps() const { return detail_deps_; }
    QVariantList detailStatus() const { return detail_status_; }
    QVariantList detailCards() const { return detail_cards_; }
    QString coverUrl() const { return cover_url_; }
    bool coverBusy() const { return cover_busy_; }
    QString taskSummary() const { return task_summary_; }
    int taskPercent() const { return task_percent_; }
    bool taskBusy() const { return task_busy_; }
    bool loadOn() const { return load_on_; }
    QString loadDetail() const { return load_detail_; }
    QString loadLog() const { return load_log_; }

    void note_library();
    void commit_enginespec(const QString& kuid, const QString& text);
    ~TrainzUtilBridge() override;

    Q_INVOKABLE void showPage(const QString& page);
    Q_INVOKABLE void goHome();
    Q_INVOKABLE void browseUtil();
    Q_INVOKABLE void browseData();
    Q_INVOKABLE void refreshLauncher();
    Q_INVOKABLE void addFiles();
    Q_INVOKABLE void clearSources();
    Q_INVOKABLE void dropUrls(const QVariantList& urls);
    Q_INVOKABLE void scanLibrary();
    Q_INVOKABLE void filterLibrary(const QString& text);
    Q_INVOKABLE void sortLibrary(const QString& key);
    Q_INVOKABLE int rowIndex(const QString& kuid) const;
    Q_INVOKABLE bool libraryHas(const QString& kuid) const;
    Q_INVOKABLE void focusAsset(const QString& kuid);
    Q_INVOKABLE void openDependencyList(const QString& kuid, const QString& pick);
    Q_INVOKABLE void closeScope();
    Q_INVOKABLE void clickPick(const QString& kuid, int modifiers);
    Q_INVOKABLE void beginDragPick(const QString& kuid);
    Q_INVOKABLE void dragPick(const QString& kuid);
    Q_INVOKABLE void endDragPick();
    Q_INVOKABLE void installChecked();
    Q_INVOKABLE void stopQueue();
    Q_INVOKABLE void removeSource(const QString& source_id);
    Q_INVOKABLE void selectSource(const QString& source_id);
    Q_INVOKABLE void setSourcesChecked(bool on);
    Q_INVOKABLE QVariantList classifyLog(const QString& text) const;
    Q_INVOKABLE void closeReport();
    Q_INVOKABLE void copyText(const QString& text);
    Q_INVOKABLE void backContents();
    Q_INVOKABLE void addScripts();
    Q_INVOKABLE void clearScripts();
    Q_INVOKABLE void encryptScripts();
    Q_INVOKABLE void removeScript(const QString& script_id);
    Q_INVOKABLE void openForEditing();
    Q_INVOKABLE void submitEdit();
    Q_INVOKABLE void validateAssets();
    Q_INVOKABLE void openPackages();
    Q_INVOKABLE void inspectStatus();
    Q_INVOKABLE void inspectErrors();
    Q_INVOKABLE void inspectDepends();
    Q_INVOKABLE void measurePacked();
    Q_INVOKABLE void openEngine(const QString& kuid);
    Q_INVOKABLE void exportTogether();
    Q_INVOKABLE void exportEach();
    Q_INVOKABLE void pickVisible(bool on);
    Q_INVOKABLE void findBackups(const QString& query);
    Q_INVOKABLE void findSelectedBackups();
    Q_INVOKABLE void openBackup(const QString& path);
    Q_INVOKABLE void showBackup(const QString& path);
    Q_INVOKABLE void openEntry(const QString& job_id);

signals:
    void changed();
    void homeRequested();
    void engineRequested(const QString& kuid, const QString& text, const QString& name);
    void packagesRequested(const QString& folder);
    void contentsReady(const QVariantList& rows);
    void sourcesReady(const QVariantList& rows);
    void scriptsReady(const QVariantList& rows);
    void logLine(const QString& text);
    void jobState(const QString& id, const QString& state);
    void backupsReady(const QVariantList& rows);
    void tasksReady(const QVariantList& rows);

private:
    struct Source {
        QString id;
        QString path;
        QString name;
        QString kind;
        QString status;
        int percent = 0;
        bool checked = true;
    };
    struct DepNote {
        QString note;
        QVariantList deps;
    };

    void note(const QString& text);
    void report(const QString& text);
    void publish_sources();
    void publish_scripts();
    void publish_backups();
    void publish_tasks();
    void publish_load(const QString& text);
    void stop_scan();
    void on_data_folder(const QString& folder);
    void on_library_scan(bool ok, const QString& launcher_text, const QList<LibraryAsset>& rows);
    void open_data_folder();
    void scan_content();
    void sync_details();
    void publish_cards(const QStringList& kuids, const QString& focus, bool fetch);
    void fetch_deps(const QString& kuid);
    void load_cover(const QString& kuid);
    void clear_detail();
    void set_detail(const QVariantMap& card, const QStringList& status);
    bool ready();
    bool can_query() const;
    QStringList action_kuids();
    void run_action(const QString& command, const QString& label);
    void inspect(const QString& kind);
    void export_selected(bool separate);
    void add_package_paths(const QStringList& paths);
    void add_script_paths(const QStringList& paths);
    void show_source(const QString& source_id);
    void show_jobs(const QString& crumb, const QList<TuJob>& jobs);
    void note_install(const QString& job_id, const QString& state, int percent, const QString& line);
    void rollup(const QString& source_path);
    QList<TuJob> package_jobs(const QString& path) const;

    LibraryList* library_ = nullptr;
    InstallQueue* queue_ = nullptr;
    class QThread* scan_thread_ = nullptr;
    std::shared_ptr<TrainzScanGate> scan_state_;
    std::shared_ptr<const ContentIndex> index_;
    QString data_dir_;
    bool data_ready_ = false;
    bool want_data_ = false;
    bool scanning_ = false;
    bool fill_library_ = false;
    bool fill_dates_ = false;
    bool fill_meta_ = false;
    int fill_gen_ = 0;
    QList<Source> sources_;
    QHash<QString, TuJob> jobs_;
    QStringList job_order_;
    QHash<QString, int> job_pct_;
    QHash<QString, QString> job_status_;
    QString selected_source_;
    QList<QPair<QString, QStringList>> view_stack_;
    QVariantList scripts_;
    bool encrypting_ = false;
    QString page_ = QStringLiteral("library");
    QString util_path_ = QStringLiteral("TrainzUtil.exe not found");
    QString launcher_text_ = QStringLiteral("Launcher closed");
    QString crumb_ = QStringLiteral("Installed assets from Content Manager");
    QString status_text_;
    QString library_summary_ = QStringLiteral("Installed assets from Content Manager");
    QString report_text_;
    bool load_on_ = false;
    QString load_detail_;
    QString load_log_;
    QStringList load_lines_;
    QString detail_kuid_;
    QString detail_title_;
    QString focus_kuid_;
    QVariantList detail_cards_;
    QVariantList detail_deps_;
    QVariantList detail_status_;
    QHash<QString, DepNote> dep_cache_;
    bool detail_from_picks_ = false;
    bool detail_cap_noted_ = false;
    QString cover_url_;
    bool cover_busy_ = false;
    int cover_gen_ = 0;
    QString backup_query_;
    QString backup_summary_ = QStringLiteral("Find backups for an asset");
    QString backup_pick_;
    QVariantList batch_rows_;
    QHash<QString, QVariantMap> install_rows_;
    QStringList install_order_;
    QString task_summary_ = QStringLiteral("Open, submit, or validate an asset");
    int task_percent_ = 0;
    bool task_busy_ = false;
    int task_gen_ = 0;
    bool launcher_ok_ = false;
    bool detail_on_ = false;
};

class TrainzUtilPage : public QWidget {
    Q_OBJECT

public:
    explicit TrainzUtilPage(QWidget* parent = nullptr, bool start_probe = true);

    void open_archive(const QString& path);
    void commit_enginespec(const QString& kuid, const QString& text);
    int library_rows() const;
    QString cell(int row, int column) const;
    TrainzUtilBridge* bridge() const { return bridge_; }
    LibraryList* library() const { return library_; }
    bool qmlReady() const;
    QStringList qmlErrors() const;

signals:
    void homeRequested();
    void engineRequested(const QString& kuid, const QString& text, const QString& name);
    void packagesRequested(const QString& folder);

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    LibraryList* library_ = nullptr;
    InstallQueue* queue_ = nullptr;
    TrainzUtilBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
