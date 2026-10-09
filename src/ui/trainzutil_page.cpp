#include "trainzutil_page.h"

#include "icons.h"
#include "shell_window.h"

#include "io/tzarc.h"

#include <algorithm>
#include <cstdio>

#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QProcessEnvironment>
#include <QQmlContext>
#include <QSet>
#include <QSettings>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif
#include <QQmlError>
#include <QQuickWidget>
#include <QResizeEvent>
#include <QUrl>
#include <QVBoxLayout>

namespace {

QString qml_file() {
#ifdef QML_DIR
    return QStringLiteral(QML_DIR "/TrainzUtilPage.qml");
#else
    return {};
#endif
}

QString glyph(const char* name) { return material_glyph(name); }

LibraryAsset asset_from_tzarc(const QString& path) {
    QFile file(path);
    LibraryAsset asset;
    asset.name = QFileInfo(path).completeBaseName();
    if (!file.open(QIODevice::ReadOnly)) return asset;
    const QByteArray bytes = file.readAll();
    const std::vector<uint8_t> raw(bytes.begin(), bytes.end());
    const std::vector<uint8_t> config = read_tzarc_config(raw.data(), raw.size());
    const LibraryRow row = library_row_from_config(config.data(), config.size());
    if (!row.name.empty()) asset.name = QString::fromUtf8(row.name.c_str());
    asset.kuid = QString::fromUtf8(row.kuid.c_str());
    asset.author = QString::fromUtf8(row.author.c_str());
    asset.build = QString::fromUtf8(row.build.c_str());
    return asset;
}

QString field_of(const LibraryAsset& asset, const QString& key) {
    if (key == QLatin1String("kuid")) return asset.kuid;
    if (key == QLatin1String("author")) return asset.author;
    if (key == QLatin1String("build")) return asset.build;
    return asset.name;
}

QStringList drive_roots() {
#ifdef Q_OS_WIN
    QStringList roots;
    for (char letter = 'A'; letter <= 'Z'; ++letter) {
        const QString root = QString(QChar(letter)) + QStringLiteral(":\\");
        const UINT kind = GetDriveTypeW(reinterpret_cast<const wchar_t*>(root.utf16()));
        if (kind == DRIVE_REMOVABLE || kind == DRIVE_FIXED) roots << root;
    }
    return roots;
#else
    return {};
#endif
}

QString first_file(const QStringList& paths) {
    for (const QString& path : paths) {
        if (!path.isEmpty() && QFileInfo(path).isFile()) return QFileInfo(path).absoluteFilePath();
    }
    return {};
}

}  // namespace

QString trainzutil_under_common(const QString& common_dir) {
    const QDir common(common_dir);
    if (!common.exists()) return {};
    QStringList hits;
    const QFileInfoList children = common.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot);
    for (const QFileInfo& child : children) {
        if (!child.fileName().contains(QLatin1String("trainz"), Qt::CaseInsensitive)) continue;
        const QString exe = child.filePath() + QStringLiteral("/TrainzUtil.exe");
        if (QFileInfo(exe).isFile()) hits << QFileInfo(exe).absoluteFilePath();
    }
    std::sort(hits.begin(), hits.end(), [](const QString& left, const QString& right) {
        const QString left_name = QFileInfo(left).dir().dirName();
        const QString right_name = QFileInfo(right).dir().dirName();
        const bool left_2022 = left_name.contains(QLatin1String("2022"));
        const bool right_2022 = right_name.contains(QLatin1String("2022"));
        if (left_2022 != right_2022) return left_2022;
        return left_name.compare(right_name, Qt::CaseInsensitive) < 0;
    });
    return hits.isEmpty() ? QString() : hits.first();
}

QString find_trainzutil(const QString& saved) {
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString home = env.value(QStringLiteral("TRAINZ_HOME"), env.value(QStringLiteral("TRS22_HOME")));
    const QString explicit_hit = first_file({
        saved,
        env.value(QStringLiteral("TRAINZUTIL")),
        home.isEmpty() ? QString() : home + QStringLiteral("/TrainzUtil.exe"),
    });
    if (!explicit_hit.isEmpty()) return explicit_hit;
    // ponytail: one directory listing per drive root plus a few known Steam tails.
    // A library buried deeper than that needs Browse.
    QStringList commons;
    QSet<QString> seen;
    const QStringList tails = {
        QStringLiteral("steamapps/common"),
        QStringLiteral("Steam/steamapps/common"),
        QStringLiteral("SteamLibrary/steamapps/common"),
        QStringLiteral("Program Files (x86)/Steam/steamapps/common"),
        QStringLiteral("Program Files/Steam/steamapps/common"),
    };
    for (const QString& root : drive_roots()) {
        QStringList candidates;
        for (const QString& tail : tails) candidates << QDir(root).filePath(tail);
        const QFileInfoList children = QDir(root).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot);
        for (const QFileInfo& child : children) candidates << child.filePath() + QStringLiteral("/steamapps/common");
        for (const QString& common : candidates) {
            const QString key = QDir::cleanPath(common).toLower();
            if (seen.contains(key) || !QFileInfo(common).isDir()) continue;
            seen.insert(key);
            commons << common;
        }
    }
    for (const QString& common : commons) {
        const QString hit = trainzutil_under_common(common);
        if (!hit.isEmpty()) return hit;
    }
    return {};
}

LibraryList::LibraryList(QObject* parent) : QAbstractListModel(parent) {}

int LibraryList::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : shown_.size(); }

QVariant LibraryList::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= shown_.size()) return {};
    const LibraryAsset& asset = all_[shown_[index.row()]];
    switch (role) {
    case Qt::UserRole + 1: return asset.kuid;
    case Qt::UserRole + 2: return asset.name;
    case Qt::UserRole + 3: return false;
    case Qt::UserRole + 4: return QString();
    case Qt::UserRole + 5: return asset.author;
    case Qt::UserRole + 6: return asset.picked;
    case Qt::UserRole + 7: return QString();
    case Qt::UserRole + 8: return false;
    case Qt::UserRole + 9: return QStringLiteral("Installed");
    case Qt::UserRole + 10: return QString();
    case Qt::UserRole + 11: return QString();
    case Qt::UserRole + 12: return asset.author;
    case Qt::UserRole + 13: return asset.build;
    default: return {};
    }
}

QHash<int, QByteArray> LibraryList::roleNames() const {
    return {
        {Qt::UserRole + 1, "kuid"},
        {Qt::UserRole + 2, "assetName"},
        {Qt::UserRole + 3, "faulty"},
        {Qt::UserRole + 4, "category"},
        {Qt::UserRole + 5, "credits"},
        {Qt::UserRole + 6, "picked"},
        {Qt::UserRole + 7, "packed"},
        {Qt::UserRole + 8, "engineSpec"},
        {Qt::UserRole + 9, "statusText"},
        {Qt::UserRole + 10, "installed"},
        {Qt::UserRole + 11, "modified"},
        {Qt::UserRole + 12, "authorName"},
        {Qt::UserRole + 13, "buildVersion"},
    };
}

void LibraryList::add(const LibraryAsset& asset) {
    all_.push_back(asset);
    rebuild();
}

QString LibraryList::cell(int row, int column) const {
    if (row < 0 || row >= shown_.size()) return {};
    const LibraryAsset& asset = all_[shown_[row]];
    if (column == 0) return asset.name;
    if (column == 1) return asset.kuid;
    if (column == 2) return asset.author;
    return asset.build;
}

void LibraryList::filter(const QString& query) {
    query_ = query.trimmed();
    rebuild();
}

void LibraryList::sort_by(const QString& key) {
    if (sort_key_ == key) sort_desc_ = !sort_desc_;
    else {
        sort_key_ = key;
        sort_desc_ = false;
    }
    sort_mark_ = sort_desc_ ? key + QStringLiteral(":desc") : key;
    rebuild();
}

int LibraryList::index_of(const QString& kuid) const {
    for (int i = 0; i < shown_.size(); ++i) {
        if (all_[shown_[i]].kuid == kuid) return i;
    }
    return -1;
}

bool LibraryList::contains(const QString& kuid) const {
    return std::any_of(all_.begin(), all_.end(), [&](const LibraryAsset& asset) { return asset.kuid == kuid; });
}

void LibraryList::toggle_pick(const QString& kuid) {
    for (int row = 0; row < shown_.size(); ++row) {
        LibraryAsset& asset = all_[shown_[row]];
        if (asset.kuid != kuid) continue;
        asset.picked = !asset.picked;
        emit dataChanged(index(row), index(row));
        return;
    }
}

void LibraryList::drag_pick(const QString& kuid) { toggle_pick(kuid); }

void LibraryList::rebuild() {
    beginResetModel();
    shown_.clear();
    for (int i = 0; i < all_.size(); ++i) {
        const LibraryAsset& asset = all_[i];
        const QString blob = asset.name + asset.kuid + asset.author + asset.build;
        if (query_.isEmpty() || blob.contains(query_, Qt::CaseInsensitive)) shown_.push_back(i);
    }
    std::stable_sort(shown_.begin(), shown_.end(), [&](int left, int right) {
        const int order = field_of(all_[left], sort_key_).compare(field_of(all_[right], sort_key_), Qt::CaseInsensitive);
        return sort_desc_ ? order > 0 : order < 0;
    });
    endResetModel();
}

TrainzUtilBridge::TrainzUtilBridge(LibraryList* library, InstallQueue* queue, QObject* parent)
    : QObject(parent), library_(library), queue_(queue) {
    const QString saved = QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).value(QStringLiteral("trainzutil/exe")).toString();
    const QString found = find_trainzutil(saved);
    if (!found.isEmpty()) {
        util_path_ = found;
        queue_->set_exe(found);
    }
    refreshLauncher();
    connect(queue_, &InstallQueue::jobFinished, this, [this](const QString& id, bool ok) {
        for (Source& source : sources_) {
            if (source.id != id) continue;
            source.percent = 100;
            source.status = ok ? QStringLiteral("Installed") : QStringLiteral("Failed");
        }
        publish_sources();
    });
}

QString TrainzUtilBridge::iconFont() const { return material_icon_family(); }
QString TrainzUtilBridge::glyphHome() const { return glyph("home"); }
QString TrainzUtilBridge::glyphFolder() const { return glyph("folder_open"); }
QString TrainzUtilBridge::glyphRefresh() const { return glyph("refresh"); }
QString TrainzUtilBridge::glyphAssets() const { return glyph("inventory_2"); }
QString TrainzUtilBridge::glyphSearch() const { return glyph("search"); }
QString TrainzUtilBridge::glyphHistory() const { return glyph("history"); }
QString TrainzUtilBridge::glyphEdit() const { return glyph("edit"); }
QString TrainzUtilBridge::glyphPublish() const { return glyph("publish"); }
QString TrainzUtilBridge::glyphCheck() const { return glyph("fact_check"); }
QString TrainzUtilBridge::glyphChevronLeft() const { return glyph("chevron_left"); }
QString TrainzUtilBridge::glyphChevronRight() const { return glyph("chevron_right"); }
QString TrainzUtilBridge::glyphClose() const { return glyph("close"); }
QString TrainzUtilBridge::glyphCopy() const { return glyph("content_copy"); }

void TrainzUtilBridge::note_library() {
    const int count = library_->count();
    library_summary_ = count == 1 ? QStringLiteral("1 asset") : QStringLiteral("%1 assets").arg(count);
    if (page_ == QLatin1String("library")) crumb_ = library_summary_;
    emit changed();
}

void TrainzUtilBridge::showPage(const QString& page) {
    if (page != QLatin1String("library") && page != QLatin1String("files") && page != QLatin1String("install") && page != QLatin1String("backups") && page != QLatin1String("encrypt")) return;
    page_ = page;
    if (page_ == QLatin1String("library")) crumb_ = library_summary_;
    emit changed();
    if (page_ == QLatin1String("install")) publish_sources();
    if (page_ == QLatin1String("backups")) emit backupsReady({});
    if (page_ == QLatin1String("encrypt")) emit scriptsReady({});
    if (page_ == QLatin1String("files")) emit contentsReady({});
}

void TrainzUtilBridge::goHome() { emit homeRequested(); }

void TrainzUtilBridge::browseUtil() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("TrainzUtil.exe"), {}, QStringLiteral("TrainzUtil (TrainzUtil.exe)"));
    if (path.isEmpty()) return;
    util_path_ = path;
    QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).setValue(QStringLiteral("trainzutil/exe"), path);
    queue_->set_exe(path);
    refreshLauncher();
}

void TrainzUtilBridge::browseData() { later(QStringLiteral("The content library scan stays in the Python app")); }

void TrainzUtilBridge::refreshLauncher() {
    launcher_ok_ = QFileInfo::exists(util_path_);
    launcher_text_ = launcher_ok_ ? QStringLiteral("TrainzUtil ready") : QStringLiteral("Launcher closed");
    emit changed();
}

void TrainzUtilBridge::addFiles() {
    const QStringList paths = QFileDialog::getOpenFileNames(nullptr, QStringLiteral("Add packages"), {}, QStringLiteral("Packages (*.cdp *.zip *.tzarc)"));
    QVariantList urls;
    for (const QString& path : paths) urls << QUrl::fromLocalFile(path).toString();
    dropUrls(urls);
}

void TrainzUtilBridge::clearSources() {
    sources_.clear();
    publish_sources();
}

void TrainzUtilBridge::dropUrls(const QVariantList& urls) {
    for (const QVariant& url_value : urls) {
        const QUrl url(url_value.toString());
        const QString path = url.isLocalFile() ? url.toLocalFile() : url_value.toString();
        if (path.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
            library_->add(asset_from_tzarc(path));
            note_library();
            continue;
        }
        Source source;
        source.id = QString::number(sources_.size() + 1);
        source.path = path;
        source.name = QFileInfo(path).fileName();
        source.kind = QFileInfo(path).suffix().toUpper();
        source.status = QStringLiteral("Waiting");
        sources_.push_back(source);
    }
    publish_sources();
    if (!sources_.isEmpty()) showPage(QStringLiteral("install"));
}

void TrainzUtilBridge::scanLibrary() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open tzarc"), {}, QStringLiteral("tzarc (*.tzarc)"));
    if (path.isEmpty()) return;
    library_->add(asset_from_tzarc(path));
    note_library();
}

void TrainzUtilBridge::filterLibrary(const QString& text) {
    library_->filter(text);
    note_library();
}

void TrainzUtilBridge::sortLibrary(const QString& key) {
    library_->sort_by(key);
    emit changed();
}

int TrainzUtilBridge::rowIndex(const QString& kuid) const { return library_->index_of(kuid); }
bool TrainzUtilBridge::libraryHas(const QString& kuid) const { return library_->contains(kuid); }

void TrainzUtilBridge::focusAsset(const QString& kuid) {
    detail_kuid_ = kuid;
    detail_on_ = !kuid.isEmpty();
    detail_cards_.clear();
    if (detail_on_) {
        const int row = library_->index_of(kuid);
        detail_cards_.push_back(QVariantMap{
            {QStringLiteral("kuid"), kuid},
            {QStringLiteral("name"), row >= 0 ? library_->cell(row, 0) : kuid},
            {QStringLiteral("author"), row >= 0 ? library_->cell(row, 2) : QString()},
        });
    }
    emit changed();
}

void TrainzUtilBridge::clickPick(const QString& kuid, int) { library_->toggle_pick(kuid); }
void TrainzUtilBridge::beginDragPick(const QString& kuid) { library_->toggle_pick(kuid); }
void TrainzUtilBridge::dragPick(const QString& kuid) { library_->drag_pick(kuid); }
void TrainzUtilBridge::endDragPick() {}

void TrainzUtilBridge::installChecked() {
    if (util_path_.isEmpty() || !QFileInfo::exists(util_path_)) {
        crumb_ = QStringLiteral("Choose TrainzUtil.exe first");
        emit changed();
        return;
    }
    QList<InstallJob> jobs;
    for (Source& source : sources_) {
        if (!source.checked || source.percent >= 100) continue;
        source.status = QStringLiteral("Queued");
        jobs.push_back({source.id, source.path});
    }
    publish_sources();
    queue_->set_exe(util_path_);
    queue_->enqueue(jobs);
}

void TrainzUtilBridge::stopQueue() {
    queue_->stop();
    for (Source& source : sources_) {
        if (source.percent < 100) source.status = QStringLiteral("Waiting");
    }
    publish_sources();
}

void TrainzUtilBridge::removeSource(const QString& source_id) {
    sources_.removeIf([&](const Source& source) { return source.id == source_id; });
    publish_sources();
}

void TrainzUtilBridge::selectSource(const QString& source_id) {
    for (Source& source : sources_) source.checked = source.id == source_id;
    publish_sources();
}

void TrainzUtilBridge::setSourcesChecked(bool on) {
    for (Source& source : sources_) source.checked = on;
    publish_sources();
}

QVariantList TrainzUtilBridge::classifyLog(const QString&) const { return {}; }
void TrainzUtilBridge::closeReport() {}
void TrainzUtilBridge::copyText(const QString&) {}
void TrainzUtilBridge::backContents() { showPage(QStringLiteral("library")); }
void TrainzUtilBridge::addScripts() { later(QStringLiteral("Encrypt stays out of this build")); }
void TrainzUtilBridge::clearScripts() { emit scriptsReady({}); }
void TrainzUtilBridge::encryptScripts() { later(QStringLiteral("Encrypt stays out of this build")); }
void TrainzUtilBridge::removeScript(const QString&) {}
void TrainzUtilBridge::openForEditing() { later(QStringLiteral("Open for editing stays in the Python app")); }
void TrainzUtilBridge::submitEdit() { later(QStringLiteral("Submit stays in the Python app")); }
void TrainzUtilBridge::validateAssets() { later(QStringLiteral("Validate stays in the Python app")); }
void TrainzUtilBridge::openPackages() { showPage(QStringLiteral("install")); }
void TrainzUtilBridge::inspectStatus() {}
void TrainzUtilBridge::inspectErrors() {}
void TrainzUtilBridge::inspectDepends() {}
void TrainzUtilBridge::measurePacked() {}
void TrainzUtilBridge::openEngine(const QString&) { later(QStringLiteral("Engine Tuner opens from the home card")); }
void TrainzUtilBridge::exportTogether() { later(QStringLiteral("Export stays in the Python app")); }
void TrainzUtilBridge::exportEach() { later(QStringLiteral("Export stays in the Python app")); }
void TrainzUtilBridge::pickVisible(bool on) {
    for (int row = 0; row < library_->count(); ++row) {
        const QString kuid = library_->cell(row, 1);
        if (on != library_->data(library_->index(row), Qt::UserRole + 6).toBool()) library_->toggle_pick(kuid);
    }
}
void TrainzUtilBridge::findBackups(const QString&) { emit backupsReady({}); }
void TrainzUtilBridge::findSelectedBackups() { emit backupsReady({}); }
void TrainzUtilBridge::openBackup(const QString&) {}
void TrainzUtilBridge::showBackup(const QString&) {}
void TrainzUtilBridge::openEntry(const QString&) {}

void TrainzUtilBridge::publish_sources() {
    QVariantList rows;
    for (const Source& source : sources_) {
        const qint64 bytes = QFileInfo(source.path).size();
        rows.push_back(QVariantMap{
            {QStringLiteral("sourceId"), source.id},
            {QStringLiteral("name"), source.name},
            {QStringLiteral("kind"), source.kind},
            {QStringLiteral("size"), bytes > 0 ? QString::number(bytes) : QString()},
            {QStringLiteral("status"), source.status},
            {QStringLiteral("percent"), source.percent},
            {QStringLiteral("checked"), source.checked},
        });
    }
    emit sourcesReady(rows);
}

void TrainzUtilBridge::later(const QString& text) {
    crumb_ = text;
    emit changed();
}

TrainzUtilPage::TrainzUtilPage(QWidget* parent) : QWidget(parent) {
    load_material_icons();
    library_ = new LibraryList(this);
    queue_ = new InstallQueue(this);
    bridge_ = new TrainzUtilBridge(library_, queue_, this);
    connect(bridge_, &TrainzUtilBridge::homeRequested, this, &TrainzUtilPage::homeRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setSource(QUrl::fromLocalFile(qml_file()));
}

void TrainzUtilPage::open_archive(const QString& path) {
    library_->add(asset_from_tzarc(path));
    bridge_->note_library();
}

int TrainzUtilPage::library_rows() const { return library_->count(); }
QString TrainzUtilPage::cell(int row, int column) const { return library_->cell(row, column); }

bool TrainzUtilPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList TrainzUtilPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void TrainzUtilPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (view_) view_->setGeometry(rect());
}
