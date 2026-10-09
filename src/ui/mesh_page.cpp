#include "mesh_page.h"

#include "icons.h"
#include "mesh_view.h"
#include "shell_window.h"

#include "io/im_geom.h"
#include "io/trainzmesh.h"

#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QRegion>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QTimer>
#include <QResizeEvent>
#include <QUrl>

#include <stdexcept>
#include <vector>

namespace {

QString qml_file() {
#ifdef QML_DIR
    return QStringLiteral(QML_DIR "/MeshPage.qml");
#else
    return {};
#endif
}

QString fixture_path() {
#ifdef QML_DIR
    return QFileInfo(QStringLiteral(QML_DIR)).dir().filePath(QStringLiteral("../../trainz_studio_cpp/checks/fixtures/tri.trainzmesh"));
#else
    return {};
#endif
}

}  // namespace

MeshBridge::MeshBridge(QObject* parent) : QObject(parent) {}

QString MeshBridge::iconFont() const { return material_icon_family(); }
QString MeshBridge::iconFontUrl() const { return material_icon_url(); }
QString MeshBridge::homeGlyph() const { return material_glyph("home"); }
QString MeshBridge::openGlyph() const { return material_glyph("file_open"); }
QString MeshBridge::folderGlyph() const { return material_glyph("folder_open"); }
QString MeshBridge::saveGlyph() const { return material_glyph("save"); }
QString MeshBridge::closeGlyph() const { return material_glyph("close"); }

QStringList MeshBridge::pbrLabels() const {
    return {QStringLiteral("Lit"), QStringLiteral("Albedo"), QStringLiteral("Normal"), QStringLiteral("Rough"), QStringLiteral("Metal"), QStringLiteral("AO")};
}

void MeshBridge::attach(MeshView* view, QWidget* chrome) {
    view_ = view;
    chrome_ = chrome;
}

void MeshBridge::load_file(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        tip_ = QStringLiteral("Could not open mesh");
        emit changed();
        return;
    }
    const QByteArray bytes = file.readAll();
    const auto* data = reinterpret_cast<const uint8_t*>(bytes.constData());
    mesh_names_.clear();
    std::vector<ViewPart> drawn;
    try {
        if (path.endsWith(QLatin1String(".im"), Qt::CaseInsensitive)) {
            for (const MeshPart& part : parse_im_parts(data, static_cast<size_t>(bytes.size()))) {
                mesh_names_ << QString::fromStdString(part.name);
                ViewPart row;
                row.name = QString::fromStdString(part.name);
                row.positions = part.positions;
                row.indices = part.indices;
                drawn.push_back(std::move(row));
            }
        } else {
            const TrainzMesh mesh = parse_trainzmesh(data, static_cast<size_t>(bytes.size()));
            for (const SubMesh& part : mesh.submeshes) {
                mesh_names_ << QString::fromStdString(part.name);
                ViewPart row;
                row.name = QString::fromStdString(part.name);
                row.positions = part.positions;
                row.uvs = part.uvs;
                row.indices = part.indices;
                drawn.push_back(std::move(row));
            }
        }
    } catch (const std::exception& error) {
        tip_ = QString::fromUtf8(error.what());
        emit changed();
        return;
    }
    if (view_) view_->setParts(std::move(drawn));
    path_ = path;
    welcome_ = false;
    editor_open_ = true;
    shortcut_ = QFileInfo(path).fileName();
    tip_.clear();
    publish();
    reveal_view();
}

void MeshBridge::reveal_view() {
    auto* quick = qobject_cast<QQuickWidget*>(chrome_);
    if (!quick || !quick->rootObject()) return;
    QTimer::singleShot(0, quick, [quick] {
        if (QQuickItem* root = quick->rootObject()) QMetaObject::invokeMethod(root, "publish");
    });
}

void MeshBridge::publish() {
    QJsonArray meshes;
    for (int i = 0; i < mesh_names_.size(); ++i) {
        meshes.append(QJsonObject{
            {QStringLiteral("name"), mesh_names_[i]},
            {QStringLiteral("show"), true},
            {QStringLiteral("atts"), true},
            {QStringLiteral("on"), i == 0},
        });
    }
    const QJsonObject side{
        {QStringLiteral("tab"), tab_},
        {QStringLiteral("tabs"), QJsonArray{QStringLiteral("Scene"), QStringLiteral("Mat"), QStringLiteral("Lamps"), QStringLiteral("Motion"), QStringLiteral("Lights")}},
        {QStringLiteral("meshes"), meshes},
        {QStringLiteral("infoOpen"), true},
        {QStringLiteral("stats"), QJsonArray{QJsonObject{{QStringLiteral("k"), QStringLiteral("File")}, {QStringLiteral("v"), QFileInfo(path_).fileName()}}}},
        {QStringLiteral("sun"), sun_},
        {QStringLiteral("ground"), ground_},
        {QStringLiteral("env"), QJsonObject{{QStringLiteral("i"), env_i_}, {QStringLiteral("items"), QJsonArray{QStringLiteral("None"), QStringLiteral("Studio"), QStringLiteral("Station"), QStringLiteral("Harbor"), QStringLiteral("Lake"), QStringLiteral("Mountains")}}}},
    };
    side_json_ = QString::fromUtf8(QJsonDocument(side).toJson(QJsonDocument::Compact));
    const QString name = mesh_names_.isEmpty() ? QString() : mesh_names_.first();
    const QJsonObject dock{
        {QStringLiteral("title"), name},
        {QStringLiteral("mat"),
         QJsonObject{
             {QStringLiteral("on"), !name.isEmpty()},
             {QStringLiteral("name"), name},
             {QStringLiteral("types"), QJsonArray{QStringLiteral("m.pbrmetal"), QStringLiteral("m.onetex")}},
             {QStringLiteral("tex"), QJsonArray{}},
             {QStringLiteral("two"), false},
             {QStringLiteral("spec"), 0},
         }},
        {QStringLiteral("att"),
         QJsonObject{
             {QStringLiteral("name"), QString()},
             {QStringLiteral("parent"), QString()},
             {QStringLiteral("loc"), QJsonArray{0, 0, 0}},
             {QStringLiteral("rot"), QJsonArray{0, 0, 0, 1}},
         }},
    };
    dock_json_ = QString::fromUtf8(QJsonDocument(dock).toJson(QJsonDocument::Compact));
    emit changed();
}

void MeshBridge::setPage(const QString& page) {
    page_ = page;
    emit changed();
}
void MeshBridge::goHome() { emit homeRequested(); }
void MeshBridge::browse() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open mesh"), {}, QStringLiteral("Mesh (*.trainzmesh *.im)"));
    if (!path.isEmpty()) load_file(path);
}
void MeshBridge::openFixture() {
    const QString path = QFileInfo(fixture_path()).absoluteFilePath();
    if (QFileInfo::exists(path)) load_file(path);
    else tip_ = QStringLiteral("Sample mesh was not found");
    emit changed();
}
void MeshBridge::dropUrls(const QVariantList& urls) {
    if (urls.isEmpty()) return;
    const QUrl url(urls.front().toString());
    const QString path = url.isLocalFile() ? url.toLocalFile() : urls.front().toString();
    load_file(path);
}
void MeshBridge::noteChrome(const QVariantList& packed) {
    if (!chrome_) return;
    QRegion region;
    for (int i = 0; i + 3 < packed.size(); i += 4) {
        const int w = static_cast<int>(packed[i + 2].toDouble());
        const int h = static_cast<int>(packed[i + 3].toDouble());
        if (w < 2 || h < 2) continue;
        if (!welcome_ && chrome_->width() > 0 && w > chrome_->width() * 9 / 10 && h > chrome_->height() * 9 / 10) continue;
        region = region.united(QRegion(static_cast<int>(packed[i].toDouble()), static_cast<int>(packed[i + 1].toDouble()), w, h));
    }
    if (region.isEmpty()) {
        chrome_->clearMask();
        chrome_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
        return;
    }
    chrome_->setAttribute(Qt::WA_TransparentForMouseEvents, false);
    chrome_->setMask(region);
}
void MeshBridge::setPbr(int index) {
    pbr_ = index;
    if (view_) view_->setDebugMode(index);
    emit changed();
}
void MeshBridge::setSideTab(int index) {
    tab_ = index;
    publish();
}
void MeshBridge::clickId(const QString& id) {
    if (id == QLatin1String("resetCam") && view_) view_->resetCamera();
    else if (id == QLatin1String("open") || id == QLatin1String("folder")) browse();
    else if (id == QLatin1String("save") || id == QLatin1String("saveAs")) {
        shortcut_ = QStringLiteral("Save stays with the mesh viewport");
        emit changed();
    }
}
void MeshBridge::setChecked(const QString& key, bool on) {
    if (key == QLatin1String("sun")) {
        sun_ = on;
        if (view_) view_->setSun(on);
    } else if (key == QLatin1String("ground")) {
        ground_ = on;
        if (view_) view_->setGround(on);
    }
    publish();
}
void MeshBridge::setCombo(const QString& key, int index) {
    if (key == QLatin1String("env")) {
        env_i_ = index;
        if (view_) view_->setEnvironment(index);
    }
    publish();
}
void MeshBridge::setText(const QString&, const QString&) {}
void MeshBridge::setSpin(const QString&, double) {}
void MeshBridge::setSlider(const QString&, int) {}
void MeshBridge::setChannel(const QString&, int, double) {}
void MeshBridge::pickList(const QString&, int) {}
void MeshBridge::pickMat(int) {}
void MeshBridge::toggleMesh(int, int) {}
void MeshBridge::toggleSceneMesh(int) {}
void MeshBridge::cancelBake() {}
void MeshBridge::placeSide(double, double, double, double) {}
void MeshBridge::placeEditor(double, double, double, double) {}
void MeshBridge::placeSettings(double, double, double, double) {}

MeshStudioPage::MeshStudioPage(QWidget* parent) : QWidget(parent) {
    load_material_icons();
    gl_ = new MeshView(this);
    bridge_ = new MeshBridge(this);
    connect(bridge_, &MeshBridge::homeRequested, this, &MeshStudioPage::homeRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->setClearColor(QColor(0, 0, 0, 0));
    view_->setAttribute(Qt::WA_TranslucentBackground, true);
    view_->setAttribute(Qt::WA_NoSystemBackground, true);
    view_->setAttribute(Qt::WA_OpaquePaintEvent, false);
    view_->setAttribute(Qt::WA_AlwaysStackOnTop, true);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setSource(QUrl::fromLocalFile(qml_file()));
    view_->raise();
    bridge_->attach(gl_, view_);
}

void MeshStudioPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (gl_) gl_->setGeometry(rect());
    if (view_) {
        view_->setGeometry(rect());
        view_->raise();
    }
}

bool MeshStudioPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList MeshStudioPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void MeshStudioPage::loadFile(const QString& path) { bridge_->load_file(path); }
QString MeshStudioPage::sideJson() const { return bridge_->sideJson(); }
