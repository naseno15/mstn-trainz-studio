#pragma once

#include <QAbstractListModel>
#include <QStringList>
#include <QVariantList>
#include <QWidget>

#include "io/config_id.h"
#include "ui/install_queue.h"

class QQuickWidget;

QString find_trainzutil(const QString& saved);
QString trainzutil_under_common(const QString& common_dir);

struct LibraryAsset {
    QString name;
    QString kuid;
    QString author;
    QString build;
    bool picked = false;
};

class LibraryList : public QAbstractListModel {
    Q_OBJECT

public:
    explicit LibraryList(QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    void add(const LibraryAsset& asset);
    int count() const { return shown_.size(); }
    QString cell(int row, int column) const;
    void filter(const QString& query);
    void sort_by(const QString& key);
    QString sort_mark() const { return sort_mark_; }
    int index_of(const QString& kuid) const;
    bool contains(const QString& kuid) const;
    void toggle_pick(const QString& kuid);
    void drag_pick(const QString& kuid);

private:
    void rebuild();
    QList<LibraryAsset> all_;
    QList<int> shown_;
    QString query_;
    QString sort_key_ = QStringLiteral("name");
    bool sort_desc_ = false;
    QString sort_mark_;
};

class TrainzUtilBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(bool launcherOk READ launcherOk NOTIFY changed)
    Q_PROPERTY(QString launcherText READ launcherText NOTIFY changed)
    Q_PROPERTY(QString utilPath READ utilPath NOTIFY changed)
    Q_PROPERTY(QString crumb READ crumb NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString page READ page NOTIFY changed)
    Q_PROPERTY(bool libraryOn READ libraryOn NOTIFY changed)
    Q_PROPERTY(QString backupQuery READ backupQuery NOTIFY changed)
    Q_PROPERTY(QString backupSummary READ backupSummary NOTIFY changed)
    Q_PROPERTY(QString backupPick READ backupPick NOTIFY changed)
    Q_PROPERTY(QString librarySummary READ librarySummary NOTIFY changed)
    Q_PROPERTY(QString sortMark READ sortMark NOTIFY changed)
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

    bool dark() const { return true; }
    bool launcherOk() const { return launcher_ok_; }
    QString launcherText() const { return launcher_text_; }
    QString utilPath() const { return util_path_; }
    QString crumb() const { return crumb_; }
    QString iconFont() const;
    QString page() const { return page_; }
    bool libraryOn() const { return page_ == QLatin1String("library"); }
    QString backupQuery() const { return {}; }
    QString backupSummary() const { return QStringLiteral("Find backups for an asset"); }
    QString backupPick() const { return {}; }
    QString librarySummary() const { return library_summary_; }
    QString sortMark() const { return library_->sort_mark(); }
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
    bool busy() const { return false; }
    QString reportText() const { return {}; }
    bool reportOn() const { return false; }
    bool detailOn() const { return detail_on_; }
    QString detailKuid() const { return detail_kuid_; }
    QVariantList detailDeps() const { return {}; }
    QVariantList detailStatus() const { return {}; }
    QVariantList detailCards() const { return detail_cards_; }
    QString coverUrl() const { return {}; }
    bool coverBusy() const { return false; }
    QString taskSummary() const { return QStringLiteral("Open, submit, or validate an asset"); }
    int taskPercent() const { return 0; }
    bool taskBusy() const { return false; }
    bool loadOn() const { return false; }
    QString loadDetail() const { return {}; }
    QString loadLog() const { return {}; }

    void note_library();

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
    Q_INVOKABLE void openEntry(const QString& path);

signals:
    void changed();
    void homeRequested();
    void contentsReady(const QVariantList& rows);
    void sourcesReady(const QVariantList& rows);
    void scriptsReady(const QVariantList& rows);
    void logLine(const QString& text);
    void jobState(const QString& id, const QString& state);
    void backupsReady(const QVariantList& rows);
    void tasksReady(const QVariantList& rows);

private:
    void publish_sources();
    void later(const QString& text);
    struct Source {
        QString id;
        QString path;
        QString name;
        QString kind;
        QString status;
        int percent = 0;
        bool checked = true;
    };
    LibraryList* library_ = nullptr;
    InstallQueue* queue_ = nullptr;
    QList<Source> sources_;
    QString page_ = QStringLiteral("library");
    QString util_path_ = QStringLiteral("TrainzUtil.exe not found");
    QString launcher_text_ = QStringLiteral("Launcher closed");
    QString crumb_ = QStringLiteral("Installed assets from Content Manager");
    QString library_summary_ = QStringLiteral("Installed assets from Content Manager");
    QString detail_kuid_;
    QVariantList detail_cards_;
    bool launcher_ok_ = false;
    bool detail_on_ = false;
};

class TrainzUtilPage : public QWidget {
    Q_OBJECT

public:
    explicit TrainzUtilPage(QWidget* parent = nullptr);

    void open_archive(const QString& path);
    int library_rows() const;
    QString cell(int row, int column) const;
    bool qmlReady() const;
    QStringList qmlErrors() const;

signals:
    void homeRequested();

protected:
    void resizeEvent(QResizeEvent* event) override;

private:
    LibraryList* library_ = nullptr;
    InstallQueue* queue_ = nullptr;
    TrainzUtilBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
