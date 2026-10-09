#include "assets_page.h"

#include "shell_window.h"

#include "io/tzarc.h"

#include <algorithm>

#include <QClipboard>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QListWidget>
#include <QPlainTextEdit>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QResizeEvent>
#include <QTableWidget>

namespace {

QString qml_dir() {
#ifdef QML_DIR
    return QStringLiteral(QML_DIR);
#else
    return {};
#endif
}

QString safe_kuid(const std::string& kuid) {
    QString text = QString::fromStdString(kuid);
    text.replace(QLatin1Char('<'), QString());
    text.replace(QLatin1Char('>'), QString());
    text.replace(QLatin1Char(':'), QLatin1Char('_'));
    return text;
}

}  // namespace

AssetsBridge::AssetsBridge(QObject* parent) : QObject(parent) {
    if (auto* host = qobject_cast<QWidget*>(parent)) {
        tex_ = new Texmesh(host);
        connect(tex_, &Texmesh::changed, this, &AssetsBridge::changed);
    }
}

QString AssetsBridge::footerJson() const {
    if (suite_ == QLatin1String("texmesh")) return QStringLiteral("[]");
    const QJsonArray rows{
        QJsonObject{{QStringLiteral("id"), QStringLiteral("open_cdp")}, {QStringLiteral("glyph"), material_glyph("file_open")}, {QStringLiteral("tip"), QStringLiteral("Open CDP")}, {QStringLiteral("accent"), true}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("extract_cdp")}, {QStringLiteral("glyph"), material_glyph("unarchive")}, {QStringLiteral("tip"), QStringLiteral("Extract CDP")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("open_tzarc")}, {QStringLiteral("glyph"), material_glyph("inventory_2")}, {QStringLiteral("tip"), QStringLiteral("Open TZarc")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("extract_tzarc")}, {QStringLiteral("glyph"), material_glyph("folder_zip")}, {QStringLiteral("tip"), QStringLiteral("Extract TZarc config")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("copy_pkg_kuids")}, {QStringLiteral("glyph"), material_glyph("content_copy")}, {QStringLiteral("tip"), QStringLiteral("Copy KUIDs")}, {QStringLiteral("accent"), false}},
    };
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::queueBtnJson() const {
    const QJsonArray rows{
        QJsonObject{{QStringLiteral("id"), QStringLiteral("remove")}, {QStringLiteral("glyph"), material_glyph("delete")}, {QStringLiteral("tip"), QStringLiteral("Remove")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("clear")}, {QStringLiteral("glyph"), material_glyph("clear")}, {QStringLiteral("tip"), QStringLiteral("Clear queue")}, {QStringLiteral("accent"), false}},
    };
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::leftNavJson() const {
    if (suite_ == QLatin1String("texmesh"))
        return QStringLiteral(R"([{"key":"meshops","label":"Mesh\nLods","w":100},{"key":"texture","label":"Texture\nParams","w":116}])");
    return QStringLiteral(R"([{"key":"packages","label":"Packages","w":108},{"key":"config","label":"Config","w":100}])");
}

QString AssetsBridge::rightNavJson() const {
    if (suite_ == QLatin1String("texmesh"))
        return QStringLiteral(R"([{"key":"parameter","label":"Texture\nEditor","w":116},{"key":"denoise","label":"Texture\nDenoiser","w":128}])");
    return QStringLiteral(R"([{"key":"kuid","label":"KUID","w":96},{"key":"export","label":"Export","w":96}])");
}

QString AssetsBridge::centerKind() const {
    if (page_ == QLatin1String("meshops") || page_ == QLatin1String("texture")) return QStringLiteral("split");
    if (page_ == QLatin1String("parameter") || page_ == QLatin1String("denoise")) return QStringLiteral("canvas");
    return QStringLiteral("page");
}

void AssetsBridge::set_suite(const QString& suite) {
    suite_ = suite == QLatin1String("texmesh") ? suite : QStringLiteral("assets");
    if (tex_) tex_->set_active(suite_ == QLatin1String("texmesh"));
    setPage(suite_ == QLatin1String("texmesh") ? QStringLiteral("meshops") : QStringLiteral("packages"));
}

void AssetsBridge::load_bytes(const QByteArray& bytes, const QString& path) {
    bytes_.assign(bytes.begin(), bytes.end());
    path_ = path;
    assets_.clear();
    asset_row_ = -1;
    try {
        if (path.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
            const auto config = read_tzarc_config(bytes_.data(), bytes_.size());
            CdpAssetEntry row;
            row.kuid = path.toStdString();
            row.files.push_back("config.txt");
            assets_.push_back(row);
            view_hint_ = QString::fromUtf8(reinterpret_cast<const char*>(config.data()), static_cast<int>(config.size()));
        } else {
            assets_ = list_cdp_assets(bytes_.data(), bytes_.size());
            view_hint_.clear();
        }
        center_tip_ = QString::number(assets_.size()) + QStringLiteral(" assets");
    } catch (const std::exception& error) {
        center_tip_ = QString::fromUtf8(error.what());
    }
    viewer_on_ = !assets_.empty();
    if (!assets_.empty()) show_asset(0);
    emit changed();
}

QString AssetsBridge::cell(int row, int column) const {
    if (row < 0 || row >= static_cast<int>(assets_.size())) return {};
    const CdpAssetEntry& asset = assets_[static_cast<size_t>(row)];
    if (column == 0) return QString::fromStdString(asset.kuid);
    if (column == 1) return QString::fromStdString(asset.username);
    if (column == 2) return QString::fromStdString(asset.kind);
    return {};
}

QStringList AssetsBridge::files_of(int asset) const {
    if (asset < 0 || asset >= static_cast<int>(assets_.size())) return {};
    QStringList rows;
    for (const std::string& file : assets_[static_cast<size_t>(asset)].files) rows << QString::fromStdString(file);
    return rows;
}

QString AssetsBridge::file_text(int asset, const QString& rel) const {
    if (asset < 0 || asset >= static_cast<int>(assets_.size()) || bytes_.empty()) return {};
    if (path_.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive) && rel == QLatin1String("config.txt")) return view_hint_;
    try {
        const auto data = read_cdp_file(bytes_.data(), bytes_.size(), assets_[static_cast<size_t>(asset)].kuid, rel.toStdString());
        return QString::fromUtf8(reinterpret_cast<const char*>(data.data()), static_cast<int>(data.size()));
    } catch (const std::exception&) {
        return {};
    }
}

int AssetsBridge::extract_to(const QString& directory) const {
    int written = 0;
    QDir root(directory);
    if (path_.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
        QFile file(root.filePath(QStringLiteral("config.txt")));
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            file.write(view_hint_.toUtf8());
            return 1;
        }
        return 0;
    }
    for (const CdpAssetEntry& asset : assets_) {
        const QString folder = root.filePath(safe_kuid(asset.kuid));
        QDir().mkpath(folder);
        for (const std::string& rel : asset.files) {
            if (rel.find("..") != std::string::npos) continue;
            const auto data = read_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, rel);
            const QString dest = QDir(folder).filePath(QString::fromStdString(rel));
            QDir().mkpath(QFileInfo(dest).path());
            QFile file(dest);
            if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) continue;
            file.write(reinterpret_cast<const char*>(data.data()), static_cast<qint64>(data.size()));
            ++written;
        }
    }
    return written;
}

void AssetsBridge::show_asset(int row) {
    asset_row_ = row;
    if (row < 0 || row >= static_cast<int>(assets_.size())) return;
    view_title_ = QString::fromStdString(assets_[static_cast<size_t>(row)].kuid);
    viewer_on_ = true;
}

void AssetsBridge::setPage(const QString& page) {
    page_ = page;
    const QString titles[][2] = {
        {QStringLiteral("packages"), QStringLiteral("Packages")},
        {QStringLiteral("config"), QStringLiteral("Config")},
        {QStringLiteral("kuid"), QStringLiteral("KUID")},
        {QStringLiteral("export"), QStringLiteral("Export")},
        {QStringLiteral("meshops"), QStringLiteral("Mesh Lods")},
        {QStringLiteral("texture"), QStringLiteral("Texture Params")},
        {QStringLiteral("parameter"), QStringLiteral("Texture Editor")},
        {QStringLiteral("denoise"), QStringLiteral("Texture Denoiser")},
    };
    page_title_ = page;
    center_title_ = page;
    for (const auto& row : titles) {
        if (row[0] != page) continue;
        page_title_ = row[1];
        center_title_ = row[1];
    }
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->set_page(page_);
        center_tip_ = tex_->center_tip();
        dock_w_ = tex_->dock_width();
        foot_note_ = tex_->foot_note();
    }
    emit changed();
}

void AssetsBridge::goHome() { emit homeRequested(); }
void AssetsBridge::setSideW(double width) {
    side_w_ = std::max(320, std::min(560, static_cast<int>(width)));
    emit changed();
}
void AssetsBridge::setDockW(double width) {
    dock_w_ = std::max(280, std::min(720, static_cast<int>(width)));
    emit changed();
}

void AssetsBridge::runAction(const QString& action) {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->run_action(action);
        center_tip_ = tex_->center_tip();
        foot_note_ = tex_->foot_note();
        emit changed();
        return;
    }
    if (action == QLatin1String("open_cdp") || action == QLatin1String("open_tzarc")) {
        const QString filter = action == QLatin1String("open_tzarc") ? QStringLiteral("TZarc (*.tzarc)") : QStringLiteral("CDP (*.cdp)");
        const QString path = QFileDialog::getOpenFileName(nullptr, action, {}, filter);
        if (path.isEmpty()) return;
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return;
        load_bytes(file.readAll(), path);
        return;
    }
    if (action == QLatin1String("extract_cdp") || action == QLatin1String("extract_tzarc")) {
        const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Extract"));
        if (dir.isEmpty()) return;
        center_tip_ = QString::number(extract_to(dir)) + QStringLiteral(" files");
        emit changed();
        return;
    }
    if (action == QLatin1String("copy_pkg_kuids")) {
        QStringList rows;
        for (const CdpAssetEntry& asset : assets_) rows << QString::fromStdString(asset.kuid);
        if (QGuiApplication::clipboard()) QGuiApplication::clipboard()->setText(rows.join(QLatin1Char('\n')));
    }
}

void AssetsBridge::queueClear() {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->queue_clear();
        return;
    }
    bytes_.clear();
    assets_.clear();
    path_.clear();
    viewer_on_ = false;
    center_tip_ = QStringLiteral("Queue cleared");
    emit changed();
}

void AssetsBridge::queueRemove() {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->queue_remove();
        return;
    }
    queueClear();
}

void AssetsBridge::placeQueue(double x, double y, double w, double h) {
    if (tex_) tex_->place_queue(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
}
void AssetsBridge::placeCenter(double x, double y, double w, double h) { emit placeCenterRequested(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)); }
void AssetsBridge::placePreview(double x, double y, double w, double h) { emit placePreviewRequested(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)); }
void AssetsBridge::placeDock(double, double, double, double) {}
void AssetsBridge::placeFormTool(double x, double y, double w, double h) {
    if (tex_) tex_->place_form_tool(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
}
void AssetsBridge::placeWell(const QString& key, double x, double y, double w, double h) {
    if (tex_) tex_->place_well(key, static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
}
void AssetsBridge::refreshCenter() { emit changed(); }
void AssetsBridge::setViewerPane(int) {}
void AssetsBridge::viewerFont(int) {}
void AssetsBridge::viewerBack() {}
void AssetsBridge::viewerExpand() {}
void AssetsBridge::viewerSave() {}
void AssetsBridge::viewerEngine() {}
void AssetsBridge::viewerFast() {}
void AssetsBridge::viewerMesh() {}
void AssetsBridge::viewerReplace() {}
void AssetsBridge::viewerDelete() {}
void AssetsBridge::viewerSaveCdp() {}
void AssetsBridge::viewerDeleteFbx() {}
void AssetsBridge::setFormTab(int tab) {
    if (tex_) tex_->set_form_tab(tab);
}
void AssetsBridge::setDockField(const QString& key, const QString& text) {
    if (tex_) tex_->set_field(key, text);
}
void AssetsBridge::runDock(const QString& id) {
    if (suite_ == QLatin1String("texmesh") && tex_) tex_->run_action(id);
}

QString AssetsBridge::brand() const { return suite_ == QLatin1String("texmesh") ? QStringLiteral("Texture & Mesh Lods") : QStringLiteral("Assets Tools"); }
QString AssetsBridge::blurb() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->blurb() : QString(); }
QString AssetsBridge::actionsJson() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->actions_json() : QStringLiteral("[]"); }
QString AssetsBridge::footerCap() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->footer_cap() : QStringLiteral("CDP / TZarc"); }
QString AssetsBridge::footNote() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->foot_note() : foot_note_; }
bool AssetsBridge::showQueue() const { return suite_ == QLatin1String("texmesh") ? page_ == QLatin1String("parameter") : page_ == QLatin1String("packages"); }
bool AssetsBridge::formOn() const { return suite_ == QLatin1String("texmesh") && tex_ && tex_->form_on(); }
QString AssetsBridge::formTitle() const { return formOn() ? tex_->form_title() : QString(); }
QString AssetsBridge::formTabs() const { return formOn() ? tex_->form_tabs() : QStringLiteral("[]"); }
int AssetsBridge::formTab() const { return formOn() ? tex_->form_tab() : 0; }
bool AssetsBridge::formTool() const { return formOn() && tex_->form_tool(); }
QString AssetsBridge::formBlocks() const { return formOn() ? tex_->form_blocks() : QStringLiteral("[]"); }
QString AssetsBridge::centerList() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->center_list() : QString(); }
QString AssetsBridge::centerPrev() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->center_prev() : QString(); }

AssetsPage::AssetsPage(QWidget* parent) : QWidget(parent) {
    bridge_ = new AssetsBridge(this);
    connect(bridge_, &AssetsBridge::homeRequested, this, &AssetsPage::homeRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setSource(QUrl::fromLocalFile(qml_dir() + QStringLiteral("/AssetsPage.qml")));
}

void AssetsPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (view_) view_->setGeometry(rect());
}

bool AssetsPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList AssetsPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void AssetsPage::loadBytes(const QByteArray& bytes, const QString& path) { bridge_->load_bytes(bytes, path); }
int AssetsPage::assetCount() const { return bridge_->asset_count(); }
QString AssetsPage::cell(int row, int column) const { return bridge_->cell(row, column); }
QString AssetsPage::fileText(int asset, const QString& rel) const { return bridge_->file_text(asset, rel); }
int AssetsPage::extractTo(const QString& directory) const { return bridge_->extract_to(directory); }
QString AssetsPage::pageName() const { return bridge_->page(); }
bool AssetsPage::formOn() const { return bridge_->formOn(); }
QString AssetsPage::centerList() const { return bridge_->centerList(); }
void AssetsPage::setPage(const QString& page) { bridge_->setPage(page); }
void AssetsPage::setSuite(const QString& suite) { bridge_->set_suite(suite); }
