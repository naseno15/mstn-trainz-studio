#include "mesh_page.h"
#include "res_path.h"

#include "icons.h"
#include "mesh_view.h"
#include "shell_window.h"
#include "status_hub.h"

#include "io/fbx.h"
#include "io/im_geom.h"
#include "io/kin.h"
#include "io/texture_txt.h"
#include "io/trainzmesh.h"

#include <cstring>

#include <QApplication>
#include <QCoreApplication>
#include <QCursor>
#include <QDir>
#include <QEventLoop>
#include <QQuaternion>
#include <QSaveFile>
#include <QScopeGuard>
#include <QTimer>
#include <QtEndian>
#include <QFile>
#include <QImage>
#include <QImageReader>
#include <QThreadPool>
#include <QColorDialog>
#include <QFileDialog>
#include <QFileInfo>
#include <QHash>
#include <QKeyEvent>
#include <QLabel>
#include <QRegion>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQuickItem>
#include <QQuickWindow>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QTimer>
#include <QResizeEvent>
#include <QUrl>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {

QString qml_file() {
return res_qml_dir() + QStringLiteral("/MeshPage.qml");
}

QString fixture_path() {
#ifdef QML_DIR
    return QDir(QStringLiteral(QML_DIR)).filePath(QStringLiteral("../../checks/fixtures/tri.trainzmesh"));
#else
    return {};
#endif
}

QString file_if(const QString& path) { return QFileInfo::exists(path) ? path : QString(); }

QString primary_image(const QDir& dir, const QString& stem) {
    const QString txt = dir.filePath(stem + QStringLiteral(".texture.txt"));
    if (!QFileInfo::exists(txt)) return {};
    QFile file(txt);
    if (!file.open(QIODevice::ReadOnly)) return {};
    const auto keys = parse_texture_txt(QString::fromUtf8(file.readAll()).toStdString());
    for (const auto& row : keys) {
        if (row.first != "Primary") continue;
        const QString img = dir.filePath(QString::fromStdString(row.second));
        if (QFileInfo::exists(img)) return img;
    }
    return {};
}

QString resolve_texture(const QString& mesh_path, const QString& named) {
    if (named.isEmpty() || named.startsWith(QLatin1Char('$'))) return {};
    const QString ref = QString(named).replace('\\', '/');
    const QFileInfo mesh(mesh_path);
    const QString direct = file_if(mesh.dir().filePath(ref));
    if (!direct.isEmpty() && !direct.endsWith(QLatin1String(".texture"), Qt::CaseInsensitive)) return direct;
    QString stem = QFileInfo(ref).fileName();
    if (stem.endsWith(QLatin1String(".texture.txt"), Qt::CaseInsensitive)) stem.chop(12);
    else if (stem.endsWith(QLatin1String(".texture"), Qt::CaseInsensitive)) stem.chop(8);
    else stem = QFileInfo(stem).completeBaseName();
    const QStringList exts{QStringLiteral(".png"), QStringLiteral(".tga"), QStringLiteral(".jpg"), QStringLiteral(".jpeg"), QStringLiteral(".bmp"), QStringLiteral(".tif"), QStringLiteral(".tiff")};
    const QStringList folders{mesh.dir().absolutePath(), mesh.dir().absoluteFilePath(QStringLiteral(".."))};
    for (const QString& folder : folders) {
        const QDir dir(folder);
        const QString from_txt = primary_image(dir, stem);
        if (!from_txt.isEmpty()) return from_txt;
        for (const QString& ext : exts) {
            const QString hit = file_if(dir.filePath(stem + ext));
            if (!hit.isEmpty()) return hit;
        }
    }
    return {};
}

struct TexPixels {
    QString path;
    int w = 0;
    int h = 0;
    std::vector<unsigned char> rgba;
};

// max_side > 0 shrinks bigger images (Preview Asset: hundreds of parts, one copy of the pixels each).
TexPixels decode_file(const QString& path, int max_side = 0) {
    TexPixels out;
    out.path = path;
    if (out.path.isEmpty()) return out;
    QImage picture(out.path);
    if (picture.isNull()) return out;
    if (max_side > 0 && std::max(picture.width(), picture.height()) > max_side)
        picture = picture.scaled(max_side, max_side, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    picture = picture.convertToFormat(QImage::Format_RGBA8888).mirrored(false, true);
    if (picture.isNull()) return out;
    out.w = picture.width();
    out.h = picture.height();
    out.rgba.resize(static_cast<size_t>(out.w) * out.h * 4);
    for (int y = 0; y < out.h; ++y) std::memcpy(out.rgba.data() + static_cast<size_t>(y) * out.w * 4, picture.constScanLine(y), static_cast<size_t>(out.w) * 4);
    return out;
}

TexPixels decode_named(const QString& mesh_path, const QString& named) { return decode_file(resolve_texture(mesh_path, named)); }

// Runs fn(i) for i in [0, count) on all cores; the caller's thread keeps pumping events and reports progress.
void run_parallel(int count, const std::function<void(int)>& fn, const std::function<void(int)>& tick) {
    if (count <= 0) return;
    std::atomic<int> next{0};
    std::atomic<int> done{0};
    QThreadPool pool;
    pool.setMaxThreadCount(std::min(count, std::max(1, static_cast<int>(std::thread::hardware_concurrency()))));
    for (int t = 0; t < pool.maxThreadCount(); ++t) {
        pool.start([&] {
            for (int i = next.fetch_add(1); i < count; i = next.fetch_add(1)) {
                fn(i);
                done.fetch_add(1);
            }
        });
    }
    while (!pool.waitForDone(32)) tick(done.load());
}
std::vector<TexPixels> load_named_parallel(const QString& mesh_path, const QStringList& names, const std::function<void(int, int, const QString&)>& tick) {
    const int total = names.size();
    std::vector<TexPixels> out(static_cast<size_t>(total));
    if (total == 0) return out;
    QImageReader::supportedImageFormats();
    std::atomic<int> next{0};
    std::atomic<int> done{0};
    std::mutex note_mu;
    QString note;
    const int workers = std::min(total, std::max(1, static_cast<int>(std::thread::hardware_concurrency())));
    QThreadPool pool;
    pool.setMaxThreadCount(workers);
    for (int t = 0; t < workers; ++t) {
        pool.start([&, mesh_path] {
            for (;;) {
                const int i = next.fetch_add(1);
                if (i >= total) return;
                TexPixels pix = decode_named(mesh_path, names.at(i));
                const QString shown = pix.path.isEmpty() ? names.at(i) : QFileInfo(pix.path).fileName();
                out[static_cast<size_t>(i)] = std::move(pix);
                {
                    std::lock_guard<std::mutex> lock(note_mu);
                    note = shown;
                }
                done.fetch_add(1);
            }
        });
    }
    while (!pool.waitForDone(32)) {
        QString shown;
        int finished = 0;
        {
            std::lock_guard<std::mutex> lock(note_mu);
            shown = note;
            finished = done.load();
        }
        tick(finished, total, shown);
    }
    return out;
}

QHash<QString, bool> read_two_map(const QString& path);
bool two_for(const QHash<QString, bool>& flags, const QString& name);
QString meta_path_for(const QString& mesh);
QByteArray replace_le_string(QByteArray data, int off, const QByteArray& text);
void write_be_f32(QByteArray& data, int off, float value);
void write_le_f32(QByteArray& data, int off, float value);
void quat_from_orient(ViewAtt& gizmo);

}  // namespace

MeshBridge::MeshBridge(QObject* parent) : QObject(parent) { publish(); }

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

int pie_sector(float dx, float dy, int count, int keep) {
    if (count <= 1) return 0;
    if (dx * dx + dy * dy < 36.f * 36.f) {
        const int wrapped = keep % count;
        return wrapped < 0 ? wrapped + count : wrapped;
    }
    // Slice i is drawn centred on i·step from the top (MeshPage.qml), so shift by half a slice.
    const float step = 6.28318530718f / static_cast<float>(count);
    float ang = std::atan2(dx, -dy) + step * 0.5f;
    while (ang < 0.f) ang += 6.28318530718f;
    while (ang >= 6.28318530718f) ang -= 6.28318530718f;
    int index = static_cast<int>(ang / step);
    if (index < 0) index = 0;
    if (index >= count) index = count - 1;
    return index;
}

bool MeshBridge::editor_pie() const {
    return page_ == QLatin1String("meshes") || page_ == QLatin1String("attachs");
}

QString MeshBridge::pieTitle() const {
    return editor_pie() ? QStringLiteral("Edit") : QStringLiteral("Shading");
}

QStringList MeshBridge::pieLabels() const {
    if (editor_pie()) return {QStringLiteral("Move"), QStringLiteral("Edit")};
    return {QStringLiteral("Wireframe"), QStringLiteral("Solid"), QStringLiteral("Material"), QStringLiteral("Render")};
}

void MeshBridge::cover_pie() {
    if (!chrome_ || !pie_open_) return;
    chrome_->setAttribute(Qt::WA_TransparentForMouseEvents, false);
    chrome_->setMask(QRegion(0, 0, std::max(1, chrome_->width()), std::max(1, chrome_->height())));
}

void MeshBridge::armPie(qreal x, qreal y) {
    pie_open_ = true;
    pie_sticky_ = false;
    pie_x_ = x;
    pie_y_ = y;
    const int current = editor_pie() ? tool_ : shade_;
    const int count = pieLabels().size();
    pie_hover_ = count > 0 ? ((current % count) + count) % count : 0;
    cover_pie();
    emit changed();
}

void MeshBridge::releasePie(qint64 held_ms) {
    if (!pie_open_) return;
    if (!pie_sticky_ && held_ms < 200) {
        pie_sticky_ = true;
        emit changed();
        return;
    }
    commitPie();
}

void MeshBridge::pieHoverAt(qreal x, qreal y) {
    if (!pie_open_) return;
    const int next = pie_sector(static_cast<float>(x - pie_x_), static_cast<float>(y - pie_y_), pieLabels().size(), pie_hover_);
    if (next == pie_hover_) return;
    pie_hover_ = next;
    emit changed();
}

void MeshBridge::commitPie() {
    if (!pie_open_) return;
    const int count = pieLabels().size();
    const int pick = pie_hover_;
    pie_open_ = false;
    pie_sticky_ = false;
    if (pick >= 0 && pick < count) {
        if (editor_pie()) {
            tool_ = pick;
            const bool move = page_ == QLatin1String("attachs") && tool_ == 0;
            if (view_) view_->setMoveTool(move);
            if (move) post_status(QStringLiteral("Move: drag an attachment's centre to move it freely, or an axis to slide along it. Hold Shift to lock to the main axis. Esc cancels."));
        } else {
            shade_ = pick;
            if (view_) view_->setShade(shade_);
        }
    }
    emit changed();
}

void MeshBridge::cancelPie() {
    if (!pie_open_) return;
    pie_open_ = false;
    pie_sticky_ = false;
    emit changed();
}

void MeshBridge::attach(MeshView* view, QWidget* chrome) {
    view_ = view;
    chrome_ = chrome;
    if (!view_) return;
    view_->setAttNames(att_names_);
    view_->setFaceOrient(face_);
    view_->setSun(sun_);
    view_->setMoon(moon_);
    view_->setSunPose(static_cast<float>(sun_az_), static_cast<float>(sun_el_), sun_int_ / 100.f);
    view_->setEmissiveScale(emis_ / 100.f);
    for (int i = 0; i < 5; ++i) view_->setArrayLight(i, array_on_[i]);
    // Shift+click in the viewport: select that part's material, open the Mat tab.
    connect(view_, &MeshView::attPicked, this, [this](int gizmo) {
        if (gizmo < 0 || gizmo >= static_cast<int>(att_rows_.size())) return;
        pick_att(gizmo);
        publish();
    });
    connect(view_, &MeshView::attMoved, this, [this](int index, float x, float y, float z) {
        if (index < 0 || index >= static_cast<int>(att_rows_.size())) return;
        if (drag_before_.empty()) drag_before_.push_back(snap());
        ViewAtt& row = att_rows_[static_cast<size_t>(index)];
        row.pos[0] = x;
        row.pos[1] = y;
        row.pos[2] = z;
        if (index == att_i_) std::memcpy(att_edit_.pos, row.pos, sizeof(row.pos));
        dirty_ = true;
        publish();
    });
    connect(view_, &MeshView::attDragDone, this, [this] {
        if (drag_before_.empty()) return;
        record(drag_before_.front());
        drag_before_.clear();
    });
    connect(view_, &MeshView::pickCleared, this, [this] {
        att_i_ = -1;
        att_edit_ = ViewAtt{};
        mat_i_ = -1;
        if (view_) view_->setHighlight({});
        publish();
    });
    connect(view_, &MeshView::cameraMoved, this, [this] { refresh_nav(); });
    refresh_nav();
    connect(view_, &MeshView::partPicked, this, [this](int part) {
        if (part < 0 || part >= static_cast<int>(rows_.size())) return;
        const MeshRow& row = rows_[static_cast<size_t>(part)];
        for (int i = 0; i < static_cast<int>(mats_.size()); ++i) {
            if (mats_[static_cast<size_t>(i)].file != part_file_.value(part)) continue;
            const QString name = QString::fromStdString(mats_[static_cast<size_t>(i)].block.name);
            if (name.compare(row.material, Qt::CaseInsensitive) != 0 && name.compare(row.name, Qt::CaseInsensitive) != 0) continue;
            mat_i_ = i;
            tab_ = 1;
            sync_highlight();
            focus_selection();
            publish();
            return;
        }
    });
}

void MeshBridge::report_load(const QString& stage, int pct) {
    load_open_ = true;
    load_stage_ = stage;
    load_pct_ = std::clamp(pct, 0, 100);
    ++load_steps_;
    emit changed();
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
}

void MeshBridge::load_file(const QString& path) {
    if (loading_) return;
    loading_ = true;
    load_steps_ = 0;
    load_name_ = QFileInfo(path).fileName();
    scene_ = false;
    scene_paths_ = {path};
    scene_yaws_.clear();
    auto stop = [this] {
        loading_ = false;
        load_open_ = false;
        emit changed();
    };
    report_load(QStringLiteral("Opening mesh…"), 4);
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        tip_ = QStringLiteral("Could not open mesh");
        post_status(tip_ + QStringLiteral(" ") + load_name_);
        stop();
        return;
    }
    report_load(QStringLiteral("Reading file…"), 12);
    const QByteArray bytes = file.readAll();
    const auto* data = reinterpret_cast<const uint8_t*>(bytes.constData());
    rows_.clear();
    mats_.clear();
    selected_ = 0;
    mat_i_ = 0;
    file_show_ = true;
    file_atts_ = true;
    file_shows_ = {true};
    file_attl_ = {true};
    sel_file_ = 0;
    bounds_set_ = false;
    anims_ = 0;
    att_count_ = 0;
    att_rows_.clear();
    att_i_ = -1;
    clear_history();
    std::vector<ViewPart> drawn;
    std::vector<ViewAtt> gizmos;
    auto grow = [&](const float* p) {
        if (!bounds_set_) {
            for (int k = 0; k < 3; ++k) bmin_[k] = bmax_[k] = p[k];
            bounds_set_ = true;
            return;
        }
        for (int k = 0; k < 3; ++k) {
            bmin_[k] = std::min(bmin_[k], p[k]);
            bmax_[k] = std::max(bmax_[k], p[k]);
        }
    };
    struct TexSlot {
        QString albedo;
        QString normal;
        QString parameter;
    };
    std::vector<TexSlot> tex_slots;
    auto push = [&](const QString& name, const QString& material, const QString& albedo, const QString& normal, const QString& parameter, const QString& format, const std::vector<float>& positions, const std::vector<float>& normals, const std::vector<float>& uvs, const std::vector<uint32_t>& indices) {
        MeshRow meta;
        meta.name = name;
        meta.material = material;
        meta.albedo = albedo;
        meta.format = format;
        meta.verts = static_cast<int>(positions.size() / 3);
        meta.tris = static_cast<int>(indices.size() / 3);
        rows_.push_back(meta);
        for (size_t v = 0; v + 2 < positions.size(); v += 3) {
            const float x = positions[v];
            const float y = positions[v + 1];
            const float z = positions[v + 2];
            if (!bounds_set_) {
                bmin_[0] = bmax_[0] = x;
                bmin_[1] = bmax_[1] = y;
                bmin_[2] = bmax_[2] = z;
                bounds_set_ = true;
            } else {
                bmin_[0] = std::min(bmin_[0], x);
                bmin_[1] = std::min(bmin_[1], y);
                bmin_[2] = std::min(bmin_[2], z);
                bmax_[0] = std::max(bmax_[0], x);
                bmax_[1] = std::max(bmax_[1], y);
                bmax_[2] = std::max(bmax_[2], z);
            }
        }
        ViewPart row;
        row.name = name;
        row.material = material;
        row.positions = positions;
        row.normals = normals;
        row.uvs = uvs;
        row.indices = indices;
        tex_slots.push_back({albedo, normal, parameter});
        drawn.push_back(std::move(row));
    };
    report_load(QStringLiteral("Parsing mesh…"), 22);
    try {
        const bool is_fbx = path.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive);
        if (is_fbx || path.endsWith(QLatin1String(".im"), Qt::CaseInsensitive)) {
            const ImView view = is_fbx ? parse_fbx_view(data, static_cast<size_t>(bytes.size())) : parse_im_view(data, static_cast<size_t>(bytes.size()));
            att_count_ = static_cast<int>(view.atts.size());
            for (const MeshPart& part : view.parts) {
                push(QString::fromStdString(part.name), {}, QString::fromStdString(part.albedo), QString::fromStdString(part.normal_map), {}, {}, part.positions, part.normals, part.uvs, part.indices);
                MatEdit edit;
                edit.block.name = part.name;
                mats_.push_back(std::move(edit));
            }
            for (const ImAttachment& att : view.atts) {
                MatEdit edit;
                edit.block.name = att.name;
                edit.gizmo = static_cast<int>(gizmos.size());
                mats_.push_back(std::move(edit));
                grow(att.pos);
                ViewAtt gizmo;
                std::memcpy(gizmo.pos, att.pos, sizeof(gizmo.pos));
                std::memcpy(gizmo.orient, att.orient, sizeof(gizmo.orient));
                gizmo.name = QString::fromStdString(att.name);
                gizmos.push_back(gizmo);
            }
        } else {
            const TrainzMesh mesh = parse_trainzmesh(data, static_cast<size_t>(bytes.size()));
            for (const SubMesh& part : mesh.submeshes) {
                push(QString::fromStdString(part.name), QString::fromStdString(part.material_type), QString::fromStdString(part.albedo), QString::fromStdString(part.normal_map), QString::fromStdString(part.parameter_map), QString::fromStdString(part.format), part.positions, part.normals, part.uvs, part.indices);
                if (!rows_.empty()) rows_.back().tail = part.tail_off;
            }
            for (const TzMaterial& block : parse_tzmf_materials(data, static_cast<size_t>(bytes.size()))) {
                MatEdit edit;
                edit.block = block;
                mats_.push_back(std::move(edit));
            }
            for (const TzAttachment& att : parse_trainzmesh_attachments(data, static_cast<size_t>(bytes.size()))) {
                ++att_count_;
                grow(att.pos);
                ViewAtt gizmo;
                std::memcpy(gizmo.pos, att.pos, sizeof(gizmo.pos));
                std::memcpy(gizmo.orient, att.orient, sizeof(gizmo.orient));
                std::memcpy(gizmo.quat, att.quat, sizeof(gizmo.quat));
                gizmo.off = static_cast<int>(att.off);
                gizmo.name = QString::fromStdString(att.name);
                gizmos.push_back(gizmo);
            }
        }
        // No material blocks (lights, markers): list the parts' own material names (else albedo name, else part name), one per part.
        if (mats_.empty()) {
            for (const MeshRow& row : rows_) {
                QString name = row.material;
                if (name.isEmpty()) name = QFileInfo(row.albedo).completeBaseName();
                if (name.isEmpty()) name = row.name;
                MatEdit edit;
                edit.block.name = name.toStdString();
                mats_.push_back(std::move(edit));
            }
        }
    } catch (const std::exception& error) {
        att_count_ = 0;
        att_rows_.clear();
        att_i_ = -1;
        if (view_) view_->setAttachments({});
        tip_ = QString::fromUtf8(error.what());
        stop();
        return;
    }
    QStringList names;
    QHash<QString, int> order;
    auto keep = [&](const QString& named) {
        if (named.isEmpty() || named.startsWith(QLatin1Char('$'))) return;
        if (order.contains(named)) return;
        order.insert(named, names.size());
        names.push_back(named);
    };
    for (const TexSlot& slot : tex_slots) {
        keep(slot.albedo);
        keep(slot.normal);
        keep(slot.parameter);
    }
    const std::vector<TexPixels> loaded = load_named_parallel(path, names, [this](int finished, int total, const QString& file) {
        const int pct = total > 0 ? 28 + (60 * finished) / total : 28;
        const QString stage = file.isEmpty() ? QStringLiteral("Loading textures · %1 / %2").arg(finished).arg(total) : QStringLiteral("Loading textures · %1 / %2 · %3").arg(finished).arg(total).arg(file);
        report_load(stage, pct);
    });
    auto paint = [&](const QString& named, std::vector<unsigned char>& rgba, int& tw, int& th) -> QString {
        if (!order.contains(named)) return {};
        const TexPixels& pix = loaded[static_cast<size_t>(order.value(named))];
        if (!pix.rgba.empty()) {
            tw = pix.w;
            th = pix.h;
            rgba = pix.rgba;
        }
        return pix.path;
    };
    for (int i = 0; i < static_cast<int>(drawn.size()) && i < static_cast<int>(tex_slots.size()); ++i) {
        rows_[static_cast<size_t>(i)].tex_file = paint(tex_slots[static_cast<size_t>(i)].albedo, drawn[static_cast<size_t>(i)].rgba, drawn[static_cast<size_t>(i)].tex_w, drawn[static_cast<size_t>(i)].tex_h);
        paint(tex_slots[static_cast<size_t>(i)].normal, drawn[static_cast<size_t>(i)].nrgba, drawn[static_cast<size_t>(i)].nrm_w, drawn[static_cast<size_t>(i)].nrm_h);
        paint(tex_slots[static_cast<size_t>(i)].parameter, drawn[static_cast<size_t>(i)].prgba, drawn[static_cast<size_t>(i)].prm_w, drawn[static_cast<size_t>(i)].prm_h);
    }
    report_load(QStringLiteral("Preparing scene…"), 92);
    const QHash<QString, bool> faces = read_two_map(meta_path_for(path));
    for (MatEdit& edit : mats_) edit.two = two_for(faces, QString::fromStdString(edit.block.name));
    for (int i = 0; i < static_cast<int>(drawn.size()) && i < static_cast<int>(rows_.size()); ++i) {
        const bool on = two_for(faces, drawn[static_cast<size_t>(i)].name);
        drawn[static_cast<size_t>(i)].two_sided = on;
        rows_[static_cast<size_t>(i)].two = on;
    }
    report_load(QStringLiteral("Uploading mesh…"), 98);
    part_file_.assign(rows_.size(), 0);
    paint_drawn_colors(drawn);
    note_atts(gizmos);
    if (view_) {
        view_->setParts(std::move(drawn));
        view_->setAttachments(std::move(gizmos));
    }
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    file_bytes_ = {bytes};
    dirty_ = false;
    path_ = path;
    bind_anims();
    welcome_ = false;
    editor_open_ = true;
    shortcut_ = QFileInfo(path).fileName();
    tip_.clear();
    QString note = QStringLiteral("Loaded ") + shortcut_;
    if (!clips_.empty()) {
        const KinClip& clip = clips_[static_cast<size_t>(anim_i_)].clip;
        const QString bone = clip.bones.empty() ? QString() : QString::fromStdString(clip.bones.front());
        note += QStringLiteral(" · ") + QFileInfo(clips_[static_cast<size_t>(anim_i_)].path).fileName() + QStringLiteral(" · %1 frames").arg(static_cast<int>(clip.frames.size()));
        if (!bone.isEmpty()) note += QStringLiteral(" · ") + bone;
    }
    post_status(note);
    publish();
    reveal_view();
    stop();
}

void MeshBridge::load_scene(const QStringList& paths, const QStringList& labels, const QList<double>& yaws) {
    if (loading_ || paths.isEmpty()) return;
    loading_ = true;
    scene_ = true;
    scene_paths_ = paths;
    scene_yaws_ = yaws;
    file_shows_ = QList<bool>(paths.size(), true);
    file_attl_ = QList<bool>(paths.size(), true);
    part_file_.clear();
    sel_file_ = 0;
    load_steps_ = 0;
    load_name_ = QStringLiteral("asset preview");
    rows_.clear();
    mats_.clear();
    selected_ = 0;
    mat_i_ = 0;
    bounds_set_ = false;
    anims_ = 0;
    att_count_ = 0;
    att_rows_.clear();
    att_i_ = -1;
    clear_history();
    stop_anim();
    clips_.clear();
    file_clip_.clear();
    if (view_) view_->setFileAnims({});
    const int total = static_cast<int>(paths.size());

    // 1. Read + parse every mesh on all cores; resolve each part's albedo image path.
    struct Parsed {
        std::vector<ViewPart> parts;
        QStringList albedo_path;
        std::vector<ImAttachment> atts;
        std::vector<TzAttachment> tz_atts;  // .trainzmesh only, parallel to atts: offsets + file quats
        std::vector<TzMaterial> blocks;
        QByteArray bytes;
        bool ok = false;
    };
    std::vector<Parsed> parsed(static_cast<size_t>(total));
    QImageReader::supportedImageFormats();
    run_parallel(
        total,
        [&](int f) {
            Parsed& out = parsed[static_cast<size_t>(f)];
            const QString& path = paths[f];
            QFile file(path);
            if (!file.open(QIODevice::ReadOnly)) return;
            const QByteArray bytes = file.readAll();
            const auto* data = reinterpret_cast<const uint8_t*>(bytes.constData());
            QStringList albedo;
            try {
                const bool is_fbx = path.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive);
                if (is_fbx || path.endsWith(QLatin1String(".im"), Qt::CaseInsensitive)) {
                    const ImView view = is_fbx ? parse_fbx_view(data, static_cast<size_t>(bytes.size())) : parse_im_view(data, static_cast<size_t>(bytes.size()));
                    out.atts = view.atts;
                    for (const MeshPart& part : view.parts) {
                        ViewPart row;
                        row.name = QString::fromStdString(part.name);
                        row.positions = part.positions;
                        row.normals = part.normals;
                        row.uvs = part.uvs;
                        row.indices = part.indices;
                        out.parts.push_back(std::move(row));
                        albedo << QString::fromStdString(part.albedo);
                    }
                } else {
                    const TrainzMesh mesh = parse_trainzmesh(data, static_cast<size_t>(bytes.size()));
                    out.tz_atts = parse_trainzmesh_attachments(data, static_cast<size_t>(bytes.size()));
                    out.blocks = parse_tzmf_materials(data, static_cast<size_t>(bytes.size()));
                    for (const TzAttachment& att : out.tz_atts) {
                        ImAttachment row;
                        row.name = att.name;
                        std::memcpy(row.pos, att.pos, sizeof(row.pos));
                        std::memcpy(row.orient, att.orient, sizeof(row.orient));
                        out.atts.push_back(std::move(row));
                    }
                    for (const SubMesh& part : mesh.submeshes) {
                        ViewPart row;
                        row.name = QString::fromStdString(part.name);
                        row.material = QString::fromStdString(part.material_type);
                        row.positions = part.positions;
                        row.normals = part.normals;
                        row.uvs = part.uvs;
                        row.indices = part.indices;
                        out.parts.push_back(std::move(row));
                        albedo << QString::fromStdString(part.albedo);
                    }
                }
            } catch (const std::exception&) {
                out.parts.clear();
                return;
            }
            const double yaw = f < yaws.size() ? yaws[f] : 0.0;
            if (yaw != 0.0) {
                const float c = static_cast<float>(std::cos(yaw)), s = static_cast<float>(std::sin(yaw));
                auto spin = [&](float& x, float& y) {
                const float nx = x * c - y * s;
                const float ny = x * s + y * c;
                x = nx;
                y = ny;
            };
            for (ViewPart& part : out.parts)
                    for (std::vector<float>* v : {&part.positions, &part.normals})
                        for (size_t k = 0; k + 2 < v->size(); k += 3) spin((*v)[k], (*v)[k + 1]);
            for (ImAttachment& att : out.atts) {
                spin(att.pos[0], att.pos[1]);
                for (int axis = 0; axis < 3; ++axis) spin(att.orient[axis * 3], att.orient[axis * 3 + 1]);
            }
            }
            for (const QString& a : albedo) out.albedo_path << resolve_texture(path, a);
            out.bytes = bytes;
            out.ok = true;
        },
        [&](int done) { report_load(QStringLiteral("Reading meshes %1 / %2").arg(done).arg(total), 4 + (40 * done) / total); });

    // 2. Decode each distinct image once, shrunk by how many parts will carry a copy.
    QStringList unique;
    QHash<QString, int> uses;  // parts carrying each image: every part holds its own copy
    for (const Parsed& p : parsed)
        for (const QString& img : p.albedo_path) {
            if (img.isEmpty()) continue;
            if (++uses[img] == 1) unique << img;
        }
    // Biggest side whose total (RAM copy + mips, same again on the GPU) fits the budget. Sizes come from headers.
    constexpr double kBudget = 1.5e9;
    std::vector<QSize> native;
    for (const QString& img : unique) native.push_back(QImageReader(img).size());
    int max_side = 512;
    for (int side : {4096, 2048, 1024}) {
        double bytes = 0;
        for (size_t i = 0; i < native.size(); ++i) {
            const double w = std::max(1, native[i].width()), h = std::max(1, native[i].height());
            const double k = std::min(1.0, side / std::max(w, h));
            bytes += uses.value(unique[static_cast<int>(i)]) * (w * k) * (h * k) * 4.0 * 1.33;
        }
        if (bytes <= kBudget) {
            max_side = side;
            break;
        }
    }
    std::vector<TexPixels> pixels(static_cast<size_t>(unique.size()));
    run_parallel(
        static_cast<int>(unique.size()),
        [&](int i) { pixels[static_cast<size_t>(i)] = decode_file(unique[i], max_side); },
        [&](int done) { report_load(QStringLiteral("Decoding textures %1 / %2").arg(done).arg(unique.size()), 45 + (45 * done) / std::max<int>(1, static_cast<int>(unique.size()))); });

    // 3. Put it together in file order.
    std::vector<ViewPart> drawn;
    std::vector<ViewAtt> gizmos;
    int failed = 0;
    for (int f = 0; f < total; ++f) {
        Parsed& p = parsed[static_cast<size_t>(f)];
        if (!p.ok) {
            ++failed;
            continue;
        }
        att_count_ += static_cast<int>(p.atts.size());
        const QString label = f < labels.size() ? labels[f] : QFileInfo(paths[f]).fileName();
        const QHash<QString, bool> faces = read_two_map(meta_path_for(paths[f]));
        for (const TzMaterial& block : p.blocks) {
            MatEdit edit;
            edit.block = block;
            edit.file = f;
            edit.label = label;
            edit.two = two_for(faces, QString::fromStdString(block.name));
            mats_.push_back(std::move(edit));
        }
        for (size_t a = 0; a < p.atts.size(); ++a) {
            const ImAttachment& att = p.atts[a];
            MatEdit edit;
            edit.block.name = att.name;
            edit.gizmo = static_cast<int>(gizmos.size());
            edit.file = f;
            mats_.push_back(std::move(edit));
            if (!bounds_set_) {
                for (int k = 0; k < 3; ++k) bmin_[k] = bmax_[k] = att.pos[k];
                bounds_set_ = true;
            } else {
                for (int k = 0; k < 3; ++k) {
                    bmin_[k] = std::min(bmin_[k], att.pos[k]);
                    bmax_[k] = std::max(bmax_[k], att.pos[k]);
                }
            }
            ViewAtt gizmo;
            gizmo.file = f;
            std::memcpy(gizmo.pos, att.pos, sizeof(gizmo.pos));
            std::memcpy(gizmo.orient, att.orient, sizeof(gizmo.orient));
            gizmo.name = QString::fromStdString(att.name);
            if (a < p.tz_atts.size()) {
                gizmo.off = static_cast<int>(p.tz_atts[a].off);
                if (yaws.value(f, 0.0) == 0.0) std::memcpy(gizmo.quat, p.tz_atts[a].quat, sizeof(gizmo.quat));
                else quat_from_orient(gizmo);
            }
            gizmos.push_back(gizmo);
        }
        for (size_t i = 0; i < p.parts.size(); ++i) {
            ViewPart& row = p.parts[i];
            const int at = unique.indexOf(p.albedo_path[static_cast<int>(i)]);
            if (at >= 0 && !pixels[static_cast<size_t>(at)].rgba.empty()) {
                row.rgba = pixels[static_cast<size_t>(at)].rgba;
                row.tex_w = pixels[static_cast<size_t>(at)].w;
                row.tex_h = pixels[static_cast<size_t>(at)].h;
            }
            MeshRow meta;
            meta.name = label + QStringLiteral(": ") + row.name;
            meta.material = row.material;
            meta.albedo = p.albedo_path[static_cast<int>(i)];
            meta.verts = static_cast<int>(row.positions.size() / 3);
            meta.tris = static_cast<int>(row.indices.size() / 3);
            meta.tex_file = at >= 0 ? pixels[static_cast<size_t>(at)].path : QString();
            rows_.push_back(meta);
            part_file_.push_back(f);
            if (p.blocks.empty()) {
                MatEdit edit;
                edit.block.name = meta.name.toStdString();
                edit.file = f;
                mats_.push_back(std::move(edit));
            }
            for (size_t v = 0; v + 2 < row.positions.size(); v += 3) {
                for (int k = 0; k < 3; ++k) {
                    const float x = row.positions[v + static_cast<size_t>(k)];
                    if (!bounds_set_) {
                        bmin_[k] = bmax_[k] = x;
                        if (k == 2) bounds_set_ = true;
                    } else {
                        bmin_[k] = std::min(bmin_[k], x);
                        bmax_[k] = std::max(bmax_[k], x);
                    }
                }
            }
            row.name = meta.name;
            row.file = f;
            drawn.push_back(std::move(row));
        }
    }
    report_load(QStringLiteral("Uploading %1 parts to the GPU").arg(drawn.size()), 96);
    paint_drawn_colors(drawn);
    note_atts(gizmos);
    if (view_) {
        view_->setParts(std::move(drawn));
        view_->setAttachments(std::move(gizmos));
    }
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    file_bytes_.assign(static_cast<size_t>(total), {});
    for (int f = 0; f < total; ++f) file_bytes_[static_cast<size_t>(f)] = std::move(parsed[static_cast<size_t>(f)].bytes);
    dirty_ = false;
    path_.clear();
    bind_anims();
    welcome_ = false;
    editor_open_ = true;
    shortcut_ = QStringLiteral("%1 meshes").arg(total - failed);
    tip_.clear();
    post_status(QStringLiteral("Preview: ") + shortcut_ + (failed ? QStringLiteral(", %1 unreadable").arg(failed) : QString()) + (clips_.empty() ? QString() : QStringLiteral(" · %1 .kin").arg(clips_.size())));
    publish();
    reveal_view();
    loading_ = false;
    load_open_ = false;
    emit changed();
}
void MeshBridge::reveal_view() {
    auto* quick = qobject_cast<QQuickWidget*>(chrome_);
    if (!quick || !quick->rootObject()) return;
    QTimer::singleShot(0, quick, [quick] {
        if (QQuickItem* root = quick->rootObject()) QMetaObject::invokeMethod(root, "publish");
    });
}

namespace {

QString grouped(int value) {
    QString text = QString::number(value);
    for (int i = text.size() - 3; i > 0; i -= 3) text.insert(i, QLatin1Char(','));
    return text;
}

int byte_of(float value) {
    return std::clamp(static_cast<int>(std::lround(value * 255.f)), 0, 255);
}

QJsonArray rgba_bytes(const float* ch) {
    return QJsonArray{byte_of(ch[0]), byte_of(ch[1]), byte_of(ch[2]), byte_of(ch[3])};
}

int tex_rank(const QString& key) {
    const QString low = key.toLower();
    if (low == QLatin1String("txalbedo") || low == QLatin1String("texture0") || low == QLatin1String("texdiffuse") || low == QLatin1String("diffuse") || low == QLatin1String("albedo")) return 0;
    if (low.contains(QLatin1String("envbrdf"))) return 1;
    if (low.contains(QLatin1String("envirradiance"))) return 2;
    if (low.contains(QLatin1String("envradiance"))) return 3;
    if (low == QLatin1String("txnormal") || low == QLatin1String("normal")) return 4;
    if (low == QLatin1String("txparameters") || low == QLatin1String("parameters") || low == QLatin1String("param")) return 5;
    return 10;
}


QHash<QString, bool> read_two_map(const QString& path) {
    QHash<QString, bool> out;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return out;
    const QString text = QString::fromUtf8(file.readAll());
    int pos = 0;
    while ((pos = text.indexOf(QLatin1String("two-sided"), pos, Qt::CaseInsensitive)) >= 0) {
        int value = pos + 9;
        while (value < text.size() && text[value].isSpace()) ++value;
        const QString token = text.mid(value, 5).toLower();
        const bool on = token.startsWith(QLatin1Char('1')) || token.startsWith(QLatin1String("true")) || token.startsWith(QLatin1String("yes"));
        const int brace = text.lastIndexOf(QLatin1Char('{'), pos);
        int end = brace;
        while (end > 0 && text[end - 1].isSpace()) --end;
        int start = end;
        while (start > 0 && !text[start - 1].isSpace() && text[start - 1] != QLatin1Char('{') && text[start - 1] != QLatin1Char('}')) --start;
        const QString name = text.mid(start, end - start).trimmed();
        if (!name.isEmpty() && name.compare(QLatin1String("materials"), Qt::CaseInsensitive) != 0) out.insert(name.toLower(), on);
        pos += 9;
    }
    return out;
}

bool two_for(const QHash<QString, bool>& flags, const QString& name) {
    const QString key = name.toLower();
    if (flags.contains(key)) return flags.value(key);
    const QString base = key.section(QLatin1String(".m."), 0, 0);
    for (auto it = flags.cbegin(); it != flags.cend(); ++it) {
        if (it.key() == base || it.key().startsWith(base + QLatin1Char('.'))) return it.value();
    }
    return false;
}

QString meta_path_for(const QString& mesh) {
    const QFileInfo info(mesh);
    return info.dir().filePath(info.completeBaseName() + QStringLiteral(".txt"));
}

QByteArray replace_le_string(QByteArray data, int off, const QByteArray& text) {
    if (off < 0 || off + 4 > data.size()) return data;
    quint32 old_n = 0;
    std::memcpy(&old_n, data.constData() + off, 4);
    if (off + 4 + static_cast<int>(old_n) > data.size()) return data;
    QByteArray raw = text;
    raw.append('\0');
    QByteArray packed(4, 0);
    const quint32 n = static_cast<quint32>(raw.size());
    std::memcpy(packed.data(), &n, 4);
    packed.append(raw);
    data.replace(off, 4 + static_cast<int>(old_n), packed);
    return data;
}

void write_be_f32(QByteArray& data, int off, float value) {
    uint32_t bits = 0;
    std::memcpy(&bits, &value, 4);
    bits = qToBigEndian(bits);
    if (off >= 0 && off + 4 <= data.size()) std::memcpy(data.data() + off, &bits, 4);
}

void write_le_f32(QByteArray& data, int off, float value) {
    if (off >= 0 && off + 4 <= data.size()) std::memcpy(data.data() + off, &value, 4);
}

void quat_from_orient(ViewAtt& gizmo) {
    QMatrix3x3 rot;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) rot(r, c) = gizmo.orient[r * 3 + c];
    const QQuaternion q = QQuaternion::fromRotationMatrix(rot);
    gizmo.quat[0] = q.x();
    gizmo.quat[1] = q.y();
    gizmo.quat[2] = q.z();
    gizmo.quat[3] = q.scalar();
}

bool tex_locked(const QString& key, const QString& value) {
    const QString low = key.toLower();
    return value.startsWith(QLatin1Char('$')) || low.contains(QLatin1String("env"));
}

}  // namespace

QString mesh_tex_map_label(const QString& key) {
    const QString low = key.toLower();
    if (low == QLatin1String("txalbedo") || low == QLatin1String("texture0") || low == QLatin1String("texdiffuse") || low == QLatin1String("diffuse") || low == QLatin1String("albedo"))
        return QStringLiteral("Albedo");
    if (low == QLatin1String("txnormal") || low == QLatin1String("normal")) return QStringLiteral("Normal");
    if (low == QLatin1String("txparameters") || low == QLatin1String("parameters") || low == QLatin1String("param")) return QStringLiteral("Parameters");
    if (low.contains(QLatin1String("envbrdf"))) return QStringLiteral("Env BRDF");
    if (low.contains(QLatin1String("envirradiance"))) return QStringLiteral("Env Irradiance");
    if (low.contains(QLatin1String("envradiance"))) return QStringLiteral("Env Radiance");
    if (low.contains(QLatin1String("emissive"))) return QStringLiteral("Emissive Map");
    if (low.contains(QLatin1String("specular")) || low.contains(QLatin1String("specmap"))) return QStringLiteral("Specular Map");
    return key;
}

QString mesh_texture_slot_ref(const QString& path) {
    QString name = QFileInfo(path).fileName();
    if (name.endsWith(QLatin1String(".texture.txt"), Qt::CaseInsensitive)) name.chop(4);
    return name;
}

void MeshBridge::note_atts(std::vector<ViewAtt>& gizmos) {
    for (ViewAtt& gizmo : gizmos)
        if (gizmo.off < 0) quat_from_orient(gizmo);
    att_rows_ = gizmos;
    att_base_ = gizmos;
    att_count_ = static_cast<int>(gizmos.size());
    att_i_ = -1;
    att_edit_ = ViewAtt{};
}

void MeshBridge::pick_att(int index) {
    att_i_ = index;
    att_edit_ = att_rows_[static_cast<size_t>(index)];
}

namespace {

bool same_att(const ViewAtt& a, const ViewAtt& b) {
    return a.name == b.name && std::memcmp(a.pos, b.pos, sizeof(a.pos)) == 0 && std::memcmp(a.quat, b.quat, sizeof(a.quat)) == 0 && std::memcmp(a.orient, b.orient, sizeof(a.orient)) == 0;
}

bool same_mat(const MatEdit& a, const MatEdit& b) {
    const TzMaterial& x = a.block;
    const TzMaterial& y = b.block;
    if (a.two != b.two || x.name != y.name || x.type_name != y.type_name || x.spec_power != y.spec_power) return false;
    if (std::memcmp(x.color, y.color, sizeof(x.color)) != 0 || std::memcmp(x.emissive, y.emissive, sizeof(x.emissive)) != 0 || std::memcmp(x.specular, y.specular, sizeof(x.specular)) != 0) return false;
    if (x.textures.size() != y.textures.size()) return false;
    for (size_t i = 0; i < x.textures.size(); ++i)
        if (x.textures[i].key != y.textures[i].key || x.textures[i].value != y.textures[i].value) return false;
    return true;
}

}  // namespace

void MeshBridge::record(const EditSnap& before) {
    if (before.atts.size() == att_rows_.size() && before.mats.size() == mats_.size()) {
        bool same = true;
        for (size_t i = 0; same && i < att_rows_.size(); ++i) same = same_att(before.atts[i], att_rows_[i]);
        for (size_t i = 0; same && i < mats_.size(); ++i) same = same_mat(before.mats[i], mats_[i]);
        if (same) return;
    }
    undo_.push_back(before);
    // ponytail: 100 whole-state snapshots (attachments + material blocks, no geometry). Diff entries if meshes grow huge.
    if (undo_.size() > 100) undo_.erase(undo_.begin());
    redo_.clear();
}

void MeshBridge::restore(const EditSnap& state) {
    att_rows_ = state.atts;
    mats_ = state.mats;
    if (att_i_ >= static_cast<int>(att_rows_.size())) att_i_ = -1;
    att_edit_ = att_i_ >= 0 ? att_rows_[static_cast<size_t>(att_i_)] : ViewAtt{};
    if (mat_i_ >= static_cast<int>(mats_.size())) mat_i_ = mats_.empty() ? -1 : 0;
    if (view_)
        for (int i = 0; i < static_cast<int>(att_rows_.size()); ++i) view_->updateAttachment(i, att_rows_[static_cast<size_t>(i)]);
    for (const MatEdit& edit : mats_) {
        const QString name = QString::fromStdString(edit.block.name);
        for (int i = 0; i < static_cast<int>(rows_.size()); ++i) {
            MeshRow& row = rows_[static_cast<size_t>(i)];
            if (row.name.compare(name, Qt::CaseInsensitive) != 0 && row.material.compare(name, Qt::CaseInsensitive) != 0) continue;
            if (row.two == edit.two) continue;
            row.two = edit.two;
            if (view_) view_->setPartTwo(i, edit.two);
        }
    }
    dirty_ = true;
    if (mat_i_ >= 0) refresh_mat_tex_previews(mat_i_);
    for (int m = 0; m < static_cast<int>(mats_.size()); ++m) apply_mat_color_preview(m);
    sync_highlight();
    publish();
}

void MeshBridge::clear_history() {
    undo_.clear();
    redo_.clear();
    drag_before_.clear();
}

void MeshBridge::undoEdit() {
    if (undo_.empty()) {
        post_status(QStringLiteral("Nothing to undo"));
        return;
    }
    redo_.push_back(snap());
    const EditSnap state = std::move(undo_.back());
    undo_.pop_back();
    restore(state);
    post_status(QStringLiteral("Undo"));
}

void MeshBridge::redoEdit() {
    if (redo_.empty()) {
        post_status(QStringLiteral("Nothing to redo"));
        return;
    }
    undo_.push_back(snap());
    const EditSnap state = std::move(redo_.back());
    redo_.pop_back();
    restore(state);
    post_status(QStringLiteral("Redo"));
}

void MeshBridge::apply_att() {
    if (att_i_ < 0 || att_i_ >= static_cast<int>(att_rows_.size())) return;
    QQuaternion q(att_edit_.quat[3], att_edit_.quat[0], att_edit_.quat[1], att_edit_.quat[2]);
    if (q.lengthSquared() < 1e-8f) {
        post_status(QStringLiteral("Rotation quaternion is zero"));
        return;
    }
    q.normalize();
    att_edit_.quat[0] = q.x();
    att_edit_.quat[1] = q.y();
    att_edit_.quat[2] = q.z();
    att_edit_.quat[3] = q.scalar();
    const QMatrix3x3 rot = q.toRotationMatrix();
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) att_edit_.orient[r * 3 + c] = rot(r, c);
    att_rows_[static_cast<size_t>(att_i_)] = att_edit_;
    if (view_) view_->updateAttachment(att_i_, att_edit_);
    dirty_ = true;
    post_status(att_edit_.off >= 0 ? QStringLiteral("Applied ") + att_edit_.name + QStringLiteral(" · Save to write the file") : QStringLiteral("Applied ") + att_edit_.name + QStringLiteral(" · preview only, this file type is not written"));
}

// Blender XYZ Euler (R = Rz·Ry·Rx), degrees.
void att_euler(const float q[4], double out[3]) {
    const QMatrix3x3 m = QQuaternion(q[3], q[0], q[1], q[2]).normalized().toRotationMatrix();
    const double s = std::clamp(-double(m(2, 0)), -1.0, 1.0);
    out[1] = std::asin(s);
    if (std::abs(s) < 0.999999) {
        out[0] = std::atan2(m(2, 1), m(2, 2));
        out[2] = std::atan2(m(1, 0), m(0, 0));
    } else {
        out[0] = 0.0;
        out[2] = std::atan2(-m(0, 1), m(1, 1));
    }
    for (int k = 0; k < 3; ++k) out[k] = qRadiansToDegrees(out[k]);
}

void att_quat(const double deg[3], float q[4]) {
    const QQuaternion r = QQuaternion::fromAxisAndAngle(0, 0, 1, float(deg[2])) * QQuaternion::fromAxisAndAngle(0, 1, 0, float(deg[1])) * QQuaternion::fromAxisAndAngle(1, 0, 0, float(deg[0]));
    q[0] = r.x();
    q[1] = r.y();
    q[2] = r.z();
    q[3] = r.scalar();
}

static QString att_num(double v, int decimals) {
    QString s = QString::number(v, 'f', decimals);
    if (s.contains(QLatin1Char('.'))) {
        while (s.endsWith(QLatin1Char('0'))) s.chop(1);
        if (s.endsWith(QLatin1Char('.'))) s.chop(1);
    }
    return s == QLatin1String("-0") ? QStringLiteral("0") : s;
}

void MeshBridge::publish() {
    if (selected_ < 0 || selected_ >= static_cast<int>(rows_.size())) selected_ = 0;
    if (mats_.empty()) mat_i_ = -1;
    else if (mat_i_ >= static_cast<int>(mats_.size())) mat_i_ = 0;
    QJsonArray materials;
    QJsonArray mats;
    mat_owner_.clear();
    int vert_sum = 0;
    int tri_sum = 0;
    int albedo_n = 0;
    int normal_n = 0;
    int param_n = 0;
    for (const MeshRow& row : rows_) {
        vert_sum += row.verts;
        tri_sum += row.tris;
    }
    for (int i = 0; i < static_cast<int>(mats_.size()); ++i) {
        const MatEdit& edit = mats_[static_cast<size_t>(i)];
        const bool on = i == mat_i_;
        const QString shown = edit.label.isEmpty() ? QString::fromStdString(edit.block.name) : edit.label + QStringLiteral(": ") + QString::fromStdString(edit.block.name);
        materials.append(QJsonObject{{QStringLiteral("name"), shown}, {QStringLiteral("on"), on}});
        mats.append(QJsonObject{{QStringLiteral("t"), shown}, {QStringLiteral("a"), QString()}, {QStringLiteral("on"), on}, {QStringLiteral("d"), 0}});
        mat_owner_.push_back(i);
        for (const TzTex& slot : edit.block.textures) {
            const QString key = QString::fromStdString(slot.key).toLower();
            if (key.contains(QLatin1String("albedo")) || key == QLatin1String("texture0")) ++albedo_n;
            else if (key.contains(QLatin1String("normal"))) ++normal_n;
            else if (key.contains(QLatin1String("param"))) ++param_n;
        }
    }
    const bool loaded = !path_.isEmpty() || scene_;
    const QString file_label = scene_ ? shortcut_ : QFileInfo(path_).fileName();
    const QString kind = path_.endsWith(QLatin1String(".im"), Qt::CaseInsensitive) ? QStringLiteral("im") : path_.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive) ? QStringLiteral("fbx") : QStringLiteral("trainzmesh");
    QString bounds = QStringLiteral("—");
    if (bounds_set_) {
        bounds = QStringLiteral("%1 × %2 × %3")
                     .arg(bmax_[0] - bmin_[0], 0, 'f', 2)
                     .arg(bmax_[1] - bmin_[1], 0, 'f', 2)
                     .arg(bmax_[2] - bmin_[2], 0, 'f', 2);
    }
    const QJsonArray detail{
        QJsonObject{{QStringLiteral("k"), QStringLiteral("File")}, {QStringLiteral("v"), loaded ? file_label : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Kind")}, {QStringLiteral("v"), loaded ? kind : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Verts / Faces")}, {QStringLiteral("v"), loaded ? grouped(vert_sum) + QStringLiteral(" / ") + grouped(tri_sum) : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Parts")}, {QStringLiteral("v"), loaded ? QString::number(rows_.size()) : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Attachments")}, {QStringLiteral("v"), loaded ? QString::number(att_count_) : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Anims")}, {QStringLiteral("v"), loaded ? QString::number(anims_) : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Albedo / Normal / Param")}, {QStringLiteral("v"), loaded ? QStringLiteral("%1 / %2 / %3").arg(albedo_n).arg(normal_n).arg(param_n) : QStringLiteral("—")}},
        QJsonObject{{QStringLiteral("k"), QStringLiteral("Bounds (m)")}, {QStringLiteral("v"), bounds}},
    };
    const HeldKin* clip_on = anim_i_ >= 0 && anim_i_ < static_cast<int>(clips_.size()) ? &clips_[static_cast<size_t>(anim_i_)] : nullptr;
    const QJsonObject side{
        {QStringLiteral("tab"), tab_},
        {QStringLiteral("tabs"), QJsonArray{QStringLiteral("Scene"), QStringLiteral("Mat"), QStringLiteral("Lamps"), QStringLiteral("Motion"), QStringLiteral("Lights")}},
        {QStringLiteral("materials"), materials},
        {QStringLiteral("mats"), mats},
        {QStringLiteral("file"), loaded ? QJsonObject{{QStringLiteral("name"), file_label}, {QStringLiteral("show"), file_show_}, {QStringLiteral("atts"), file_atts_}} : QJsonValue()},
        {QStringLiteral("files"), [&] {
            QJsonArray a;
            if (loaded)
                for (int i = 0; i < scene_paths_.size(); ++i)
                    a.append(QJsonObject{{QStringLiteral("name"), QFileInfo(scene_paths_[i]).fileName()}, {QStringLiteral("show"), file_shows_.value(i, true)}, {QStringLiteral("atts"), file_attl_.value(i, true)}, {QStringLiteral("sel"), i == sel_file_}});
            return a;
        }()},
        {QStringLiteral("infoOpen"), info_open_},
        {QStringLiteral("face"), face_},
        {QStringLiteral("attNames"), att_names_},
        {QStringLiteral("atts"), [&] {
            QJsonArray a;
            for (const ViewAtt& row : att_rows_) a.append(row.name);
            return a;
        }()},
        {QStringLiteral("att"), att_i_},
        {QStringLiteral("anims"), [&] {
            QJsonArray a;
            for (const HeldKin& held : clips_) {
                const QString bone = held.clip.bones.empty() ? QString() : QString::fromStdString(held.clip.bones.front());
                QString label = QFileInfo(held.path).fileName();
                if (scene_paths_.size() > 1) label = QFileInfo(scene_paths_.value(held.file)).completeBaseName() + QStringLiteral(" ▸ ") + label;
                if (!bone.isEmpty()) label += QStringLiteral(" · ") + bone;
                label += QStringLiteral(" · %1f").arg(held.clip.frames.size());
                if (held.playing) label += QStringLiteral(" ▶");
                a.append(label);
            }
            return a;
        }()},
        {QStringLiteral("anim"), anim_i_},
        {QStringLiteral("animEmpty"), clips_.empty()},
        {QStringLiteral("frame"), clip_on ? clip_on->frame : 0},
        {QStringLiteral("frameMax"), clip_on ? std::max(1, static_cast<int>(clip_on->clip.frames.size()) - 1) : 1},
        {QStringLiteral("playing"), clip_on && clip_on->playing},
        {QStringLiteral("cap"), QStringLiteral("a.* → edit on right")},
        {QStringLiteral("detail"), detail},
        {QStringLiteral("sun"), sun_},
        {QStringLiteral("moon"), moon_},
        {QStringLiteral("tod"), tod_},
        {QStringLiteral("az"), sun_az_},
        {QStringLiteral("el"), sun_el_},
        {QStringLiteral("sunInt"), sun_int_},
        {QStringLiteral("emis"), emis_},
        {QStringLiteral("azLab"), QStringLiteral("Azimuth %1°").arg(sun_az_)},
        {QStringLiteral("elLab"), QStringLiteral("Elevation %1°").arg(sun_el_)},
        {QStringLiteral("intLab"), QStringLiteral("Intensity %1").arg(sun_int_ / 100.0, 0, 'f', 2)},
        {QStringLiteral("emisLab"), QStringLiteral("Emissive boost %1 (preview only)").arg(emis_ / 100.0, 0, 'f', 2)},
        {QStringLiteral("lights"), QJsonArray{
            QJsonObject{{QStringLiteral("t"), QStringLiteral("Left")}, {QStringLiteral("on"), array_on_[0]}},
            QJsonObject{{QStringLiteral("t"), QStringLiteral("Right")}, {QStringLiteral("on"), array_on_[1]}},
            QJsonObject{{QStringLiteral("t"), QStringLiteral("Front")}, {QStringLiteral("on"), array_on_[2]}},
            QJsonObject{{QStringLiteral("t"), QStringLiteral("Back")}, {QStringLiteral("on"), array_on_[3]}},
            QJsonObject{{QStringLiteral("t"), QStringLiteral("Top fill")}, {QStringLiteral("on"), array_on_[4]}},
        }},
        {QStringLiteral("ground"), ground_},
        {QStringLiteral("env"), QJsonObject{{QStringLiteral("i"), env_i_}, {QStringLiteral("items"), QJsonArray{QStringLiteral("None"), QStringLiteral("Studio"), QStringLiteral("Station"), QStringLiteral("Harbor"), QStringLiteral("Lake"), QStringLiteral("Mountains")}}}},
    };
    side_json_ = QString::fromUtf8(QJsonDocument(side).toJson(QJsonDocument::Compact));
    const bool has = mat_i_ >= 0 && mat_i_ < static_cast<int>(mats_.size());
    const MatEdit blank;
    const MatEdit& cur = has ? mats_[static_cast<size_t>(mat_i_)] : blank;
    // Trainz casing as written in .trainzmesh (StdOneTex, not stdonetex).
    const char* type_names[] = {"pbrmetal", "pbrmetalmasked", "pbrmetaldetail", "pbrmetalspec", "StdOneTex", "glass", "clutter", "foliage"};
    QJsonArray types;
    int type_i = 0;
    bool type_found = false;
    const QString cur_type = QString::fromStdString(cur.block.type_name);
    for (int i = 0; i < 8; ++i) {
        types.append(QString::fromLatin1(type_names[i]));
        if (cur_type.compare(QLatin1String(type_names[i]), Qt::CaseInsensitive) == 0) {
            type_i = i;
            type_found = true;
        }
    }
    if (has && !type_found && !cur.block.type_name.empty()) {
        types.prepend(QString::fromStdString(cur.block.type_name));
        type_i = 0;
    }
    struct TexLine {
        QString key;
        QString value;
        int rank;
    };
    std::vector<TexLine> ordered;
    for (const TzTex& tex : cur.block.textures) ordered.push_back({QString::fromStdString(tex.key), QString::fromStdString(tex.value), tex_rank(QString::fromStdString(tex.key))});
    std::stable_sort(ordered.begin(), ordered.end(), [](const TexLine& a, const TexLine& b) { return a.rank < b.rank; });
    QJsonArray tex;
    for (const TexLine& slot : ordered) {
        tex.append(QJsonObject{
            {QStringLiteral("k"), slot.key},
            {QStringLiteral("lab"), mesh_tex_map_label(slot.key)},
            {QStringLiteral("v"), slot.value},
            {QStringLiteral("lock"), tex_locked(slot.key, slot.value)},
        });
    }
    const QString mode = page_ == QLatin1String("attachs") ? QStringLiteral("attachs") : page_ == QLatin1String("meshes") ? QStringLiteral("meshes") : QString();
    double euler[3] = {};
    att_euler(att_edit_.quat, euler);
    const QJsonObject dock{
        {QStringLiteral("mode"), mode},
        {QStringLiteral("title"), page_ == QLatin1String("attachs") ? QStringLiteral("Attachs Editor") : QStringLiteral("Meshes Editor")},
        {QStringLiteral("tip"), page_ == QLatin1String("attachs") ? QStringLiteral("Pick on the left · edit here · Save") : QStringLiteral("Pick on the left · edit here · Save")},
        {QStringLiteral("saveOn"), !scene_paths_.isEmpty()},
        {QStringLiteral("mat"),
         QJsonObject{
             {QStringLiteral("on"), has},
             {QStringLiteral("name"), QString::fromStdString(cur.block.name)},
             {QStringLiteral("types"), types},
             {QStringLiteral("type"), type_i},
             {QStringLiteral("tex"), tex},
             {QStringLiteral("two"), cur.two},
             {QStringLiteral("vfmt"), cur.block.vertex_format.empty() ? QStringLiteral("—") : QString::fromStdString(cur.block.vertex_format)},
             {QStringLiteral("spec"), QString::number(cur.block.spec_power, 'f', 6)},
             {QStringLiteral("color"), rgba_bytes(cur.block.color)},
             {QStringLiteral("emis"), rgba_bytes(cur.block.emissive)},
             {QStringLiteral("specC"), rgba_bytes(cur.block.specular)},
         }},
        {QStringLiteral("att"),
         QJsonObject{
             {QStringLiteral("name"), att_edit_.name},
             {QStringLiteral("parent"), QString()},
             {QStringLiteral("loc"), QJsonArray{att_num(att_edit_.pos[0], 6), att_num(att_edit_.pos[1], 6), att_num(att_edit_.pos[2], 6)}},
             {QStringLiteral("rot"), QJsonArray{att_num(euler[0], 4), att_num(euler[1], 4), att_num(euler[2], 4)}},
             {QStringLiteral("quat"), QStringLiteral("%1, %2, %3, %4").arg(att_num(att_edit_.quat[0], 6), att_num(att_edit_.quat[1], 6), att_num(att_edit_.quat[2], 6), att_num(att_edit_.quat[3], 6))},
         }},
        {QStringLiteral("applyOn"), att_i_ >= 0},
        {QStringLiteral("addOn"), false},
        {QStringLiteral("delOn"), false},
    };
    dock_json_ = QString::fromUtf8(QJsonDocument(dock).toJson(QJsonDocument::Compact));
    emit changed();
}

void MeshBridge::setPage(const QString& page) {
    if (pie_open_) cancelPie();
    page_ = page;
    if (view_) view_->setMoveTool(page_ == QLatin1String("attachs") && tool_ == 0);
    publish();
}
void MeshBridge::goHome() { emit homeRequested(); }
void MeshBridge::browse() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open mesh"), {}, QStringLiteral("Mesh (*.trainzmesh *.im *.fbx)"));
    if (!path.isEmpty()) load_file(path);
}
QStringList MeshBridge::veContextPaths() const {
    return path_.isEmpty() ? QStringList() : QStringList{path_, QFileInfo(path_).absolutePath()};
}

void MeshBridge::openFixture() {
    const QString path = QFileInfo(fixture_path()).absoluteFilePath();
    if (QFileInfo::exists(path)) load_file(path);
    else tip_ = QStringLiteral("Sample mesh was not found");
    emit changed();
}
void MeshBridge::stop_anim() {
    for (HeldKin& held : clips_) held.playing = false;
    if (anim_timer_) anim_timer_->stop();
}

void MeshBridge::apply_frame() {
    if (!view_) return;
    auto pose = [](const KinXform& x) {
        QMatrix4x4 m;
        m.translate(x.pos[0], x.pos[1], x.pos[2]);
        m.rotate(QQuaternion(x.quat[3], x.quat[0], x.quat[1], x.quat[2]));
        m.scale(x.scale[0], x.scale[1], x.scale[2]);
        return m;
    };
    std::vector<QMatrix4x4> per_file(static_cast<size_t>(scene_paths_.size()));
    for (int f = 0; f < scene_paths_.size(); ++f) {
        const int c = file_clip_.value(f, -1);
        if (c < 0 || c >= static_cast<int>(clips_.size())) continue;
        const HeldKin& held = clips_[static_cast<size_t>(c)];
        if (held.clip.bones.size() != 1 || held.clip.frames.empty()) continue;
        const int frame = std::clamp(held.frame, 0, static_cast<int>(held.clip.frames.size()) - 1);
        QMatrix4x4 m = pose(held.clip.frames[static_cast<size_t>(frame)].front()) * pose(held.clip.frames.front().front()).inverted();
        // load_scene spun this file's vertices about Z; spin the motion the same way.
        const double yaw = scene_yaws_.value(f, 0.0);
        if (yaw != 0.0) {
            QMatrix4x4 spin;
            spin.rotate(static_cast<float>(qRadiansToDegrees(yaw)), 0.f, 0.f, 1.f);
            m = spin * m * spin.inverted();
        }
        per_file[static_cast<size_t>(f)] = m;
    }
    view_->setFileAnims(std::move(per_file));
}

namespace {

// 0 = <mesh>_scene.kin, 1 = <mesh>.kin, 2 = <mesh>*.kin, 3 = anything else.
int kin_rank(const QString& kin_path, const QString& mesh_path) {
    const QString stem = QFileInfo(mesh_path).completeBaseName();
    const QString base = QFileInfo(kin_path).completeBaseName();
    if (base.compare(stem + QStringLiteral("_scene"), Qt::CaseInsensitive) == 0) return 0;
    if (base.compare(stem, Qt::CaseInsensitive) == 0) return 1;
    if (base.startsWith(stem, Qt::CaseInsensitive)) return 2;
    return 3;
}

}  // namespace

int MeshBridge::kin_owner(const QString& kin_path, const KinClip& clip, std::vector<QByteArray>& bytes, const QString& same_dir, std::string* missing) {
    int best = -1;
    int best_rank = 4;
    bytes.resize(static_cast<size_t>(scene_paths_.size()));
    for (int f = 0; f < scene_paths_.size(); ++f) {
        if (!same_dir.isEmpty() && QFileInfo(scene_paths_[f]).absolutePath().compare(same_dir, Qt::CaseInsensitive) != 0) continue;
        QByteArray& data = bytes[static_cast<size_t>(f)];
        if (data.isEmpty() && static_cast<size_t>(f) < file_bytes_.size()) data = file_bytes_[static_cast<size_t>(f)];
        if (data.isEmpty())
            if (QFile file(scene_paths_[f]); file.open(QIODevice::ReadOnly)) data = file.readAll();
        if (!kin_bones_in_mesh(clip, reinterpret_cast<const uint8_t*>(data.constData()), static_cast<size_t>(data.size()), missing)) continue;
        const int rank = kin_rank(kin_path, scene_paths_[f]);
        if (rank < best_rank) {
            best = f;
            best_rank = rank;
        }
    }
    return best;
}

void MeshBridge::own_file(int clip) {
    if (clip < 0 || clip >= static_cast<int>(clips_.size())) return;
    const int f = clips_[static_cast<size_t>(clip)].file;
    if (f < 0) return;
    while (file_clip_.size() <= f) file_clip_ << -1;
    file_clip_[f] = clip;
    // One pose per mesh: another clip on the same mesh stops.
    for (int i = 0; i < static_cast<int>(clips_.size()); ++i)
        if (i != clip && clips_[static_cast<size_t>(i)].file == f) clips_[static_cast<size_t>(i)].playing = false;
}

void MeshBridge::bind_anims() {
    stop_anim();
    clips_.clear();
    anim_i_ = 0;
    anims_ = 0;
    file_clip_ = QList<int>(scene_paths_.size(), -1);
    if (view_) view_->setFileAnims({});
    // ponytail: bones are matched by name in the raw mesh bytes, only against meshes in the .kin's own folder.
    std::vector<QByteArray> bytes;
    QStringList dirs;
    for (const QString& p : scene_paths_) {
        const QString dir = QFileInfo(p).absolutePath();
        if (!dirs.contains(dir, Qt::CaseInsensitive)) dirs << dir;
    }
    int skipped = 0;
    for (const QString& dir : dirs) {
        for (const QString& name : QDir(dir).entryList({QStringLiteral("*.kin")}, QDir::Files, QDir::Name)) {
            const QString path = QDir(dir).filePath(name);
            QFile file(path);
            if (!file.open(QIODevice::ReadOnly)) continue;
            const QByteArray raw = file.readAll();
            KinClip clip = parse_kin(reinterpret_cast<const uint8_t*>(raw.constData()), static_cast<size_t>(raw.size()));
            const int owner = clip.ok ? kin_owner(path, clip, bytes, dir, nullptr) : -1;
            if (owner < 0) {
                ++skipped;
                continue;
            }
            HeldKin held;
            held.path = path;
            held.clip = std::move(clip);
            held.file = owner;
            clips_.push_back(std::move(held));
        }
    }
    std::stable_sort(clips_.begin(), clips_.end(), [&](const HeldKin& a, const HeldKin& b) {
        if (a.file != b.file) return a.file < b.file;
        return kin_rank(a.path, scene_paths_[a.file]) < kin_rank(b.path, scene_paths_[b.file]);
    });
    for (int i = 0; i < static_cast<int>(clips_.size()); ++i)
        if (file_clip_.value(clips_[static_cast<size_t>(i)].file, 0) < 0) file_clip_[clips_[static_cast<size_t>(i)].file] = i;
    anims_ = static_cast<int>(clips_.size());
    apply_frame();
    if (skipped > 0 && clips_.empty()) post_status(QStringLiteral("No .kin in this folder matches the mesh"));
}

void MeshBridge::add_kin(const QString& path) {
    if (scene_paths_.isEmpty() || file_bytes_.empty()) {
        post_status(QStringLiteral("Open a mesh first — %1 was not kept").arg(QFileInfo(path).fileName()));
        return;
    }
    for (int i = 0; i < static_cast<int>(clips_.size()); ++i) {
        if (QFileInfo(clips_[static_cast<size_t>(i)].path).absoluteFilePath().compare(QFileInfo(path).absoluteFilePath(), Qt::CaseInsensitive) == 0) {
            anim_i_ = i;
            own_file(i);
            apply_frame();
            publish();
            return;
        }
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        post_status(QStringLiteral("Could not read ") + QFileInfo(path).fileName());
        return;
    }
    const QByteArray bytes = file.readAll();
    KinClip clip = parse_kin(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
    const QString shown = QFileInfo(path).fileName();
    if (!clip.ok) {
        post_status(shown + QStringLiteral(" — ") + QString::fromStdString(clip.error) + QStringLiteral(" — removed"));
        return;
    }
    std::string missing;
    std::vector<QByteArray> bytes_cache;
    const int owner = kin_owner(path, clip, bytes_cache, {}, &missing);
    if (owner < 0) {
        post_status(shown + QStringLiteral(" does not match %1 (bone ").arg(scene_ ? QStringLiteral("any mesh in the view") : QStringLiteral("this mesh")) + QString::fromStdString(missing) + QStringLiteral(") — removed"));
        return;
    }
    HeldKin held;
    held.path = path;
    held.clip = std::move(clip);
    held.file = owner;
    clips_.push_back(std::move(held));
    anims_ = static_cast<int>(clips_.size());
    anim_i_ = static_cast<int>(clips_.size()) - 1;
    own_file(anim_i_);
    apply_frame();
    const KinClip& kept = clips_.back().clip;
    post_status(shown + QStringLiteral(" → ") + QFileInfo(scene_paths_.value(owner)).fileName() + QStringLiteral(" · %1 frames · %2").arg(kept.frames.size()).arg(QString::fromStdString(kept.bones.front())));
    publish();
}

void MeshBridge::dropUrls(const QVariantList& urls) {
    if (urls.isEmpty()) return;
    if (loading_) {
        post_status(QStringLiteral("Still loading — drop again when it finishes"));
        return;
    }
    // Drops append to the scene. ponytail: 2+ files load through the read-only scene preview
    // (no per-mesh editing, whole scene reloads each drop); upgrade = incremental part append.
    QStringList ok;
    QStringList kins;
    int skipped = 0;
    for (const QVariant& value : urls) {
        const QUrl url(value.toString());
        const QString path = url.isLocalFile() ? url.toLocalFile() : value.toString();
        if (path.endsWith(QLatin1String(".trainzmesh"), Qt::CaseInsensitive) || path.endsWith(QLatin1String(".im"), Qt::CaseInsensitive) || path.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) ok << path;
        else if (path.endsWith(QLatin1String(".kin"), Qt::CaseInsensitive)) kins << path;
        else ++skipped;
    }
    if (ok.isEmpty() && kins.isEmpty()) {
        post_status(QStringLiteral("Unsupported file — Mesh Studio opens .trainzmesh, .im, .fbx, and .kin"));
        return;
    }
    if (!ok.isEmpty()) {
        QStringList all = scene_paths_;
        for (const QString& p : ok) if (!all.contains(p)) all << p;
        if (all.size() == 1) load_file(all.first());
        else {
            QStringList labels;
            for (const QString& p : all) labels << QFileInfo(p).fileName();
            load_scene(all, labels, {});
        }
    }
    for (const QString& kin : kins) add_kin(kin);
    if (skipped > 0) post_status(QStringLiteral("%1 unsupported file(s) skipped").arg(skipped));
}
void MeshBridge::noteChrome(const QVariant& rects) {
    const QVariantList packed = rects.toList();
    if (!chrome_) return;
    if (load_open_ || pie_open_) {
        chrome_->setAttribute(Qt::WA_TransparentForMouseEvents, false);
        chrome_->setMask(QRegion(0, 0, std::max(1, chrome_->width()), std::max(1, chrome_->height())));
        return;
    }
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
    } else {
        chrome_->setAttribute(Qt::WA_TransparentForMouseEvents, false);
        chrome_->setMask(region);
    }
    if (view_) view_->update();
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
    if (id == QLatin1String("apply")) {
        if (att_i_ < 0) post_status(QStringLiteral("Pick an attachment first"));
        const EditSnap before = snap();
        apply_att();
        record(before);
        publish();
        return;
    }
    if (id == QLatin1String("add") || id == QLatin1String("del")) {
        post_status(QStringLiteral("Add and Delete are not written yet. They change the .trainzmesh layout."));
        return;
    }
    if (id == QLatin1String("play")) {
        if (clips_.empty()) {
            post_status(QStringLiteral("No matching .kin — drop one onto the view"));
            return;
        }
        anim_i_ = std::clamp(anim_i_, 0, static_cast<int>(clips_.size()) - 1);
        HeldKin& held = clips_[static_cast<size_t>(anim_i_)];
        if (held.clip.bones.size() != 1) {
            post_status(QStringLiteral("This .kin moves %1 bones. Playback is for a one-bone part.").arg(held.clip.bones.size()));
            return;
        }
        if (held.playing) {
            held.playing = false;
            if (std::none_of(clips_.begin(), clips_.end(), [](const HeldKin& h) { return h.playing; })) stop_anim();
            publish();
            return;
        }
        if (!anim_timer_) {
            anim_timer_ = new QTimer(this);
            connect(anim_timer_, &QTimer::timeout, this, [this] {
                const double dt = anim_clock_.restart() / 1000.0;
                bool any = false;
                for (HeldKin& h : clips_) {
                    if (!h.playing) continue;
                    any = true;
                    h.time += dt;
                    const int n = static_cast<int>(h.clip.frames.size());
                    h.frame = n > 0 ? static_cast<int>(h.time * std::max(1, h.clip.tick)) % n : 0;
                }
                if (!any) {
                    stop_anim();
                    return;
                }
                apply_frame();
                publish();
            });
        }
        own_file(anim_i_);
        held.playing = true;
        held.time = held.frame / static_cast<double>(std::max(1, held.clip.tick));
        if (!anim_timer_->isActive()) {
            anim_clock_.start();
            anim_timer_->start(16);
        }
        apply_frame();
        publish();
        return;
    }
    if (id == QLatin1String("resetCam") && view_) view_->resetCamera();
    else if (id == QLatin1String("info")) {
        info_open_ = !info_open_;
        publish();
    } else if (id.startsWith(QLatin1String("texBrowse:"))) {
        // Trainz mesh slots reference name.texture (from sibling .texture.txt + Primary image).
        const QString dir = path_.isEmpty() ? QString() : QFileInfo(path_).absolutePath();
        const QString file = QFileDialog::getOpenFileName(
            nullptr, QStringLiteral("Pick Trainz texture"), dir,
            QStringLiteral("Trainz texture (*.texture.txt *.texture);;Images (*.tga *.png *.dds *.jpg);;All (*)"));
        if (!file.isEmpty()) setText(QStringLiteral("tex:") + id.mid(10), mesh_texture_slot_ref(file));
        return;
    } else if (id == QLatin1String("open") || id == QLatin1String("folder")) browse();
    else if (id.startsWith(QLatin1String("file:"))) {
        sel_file_ = std::clamp(id.mid(5).toInt(), 0, std::max(0, int(scene_paths_.size()) - 1));
        publish();
        return;
    } else if (id == QLatin1String("removeMesh") && scene_paths_.size() > 1 && !loading_) {
        QStringList paths = scene_paths_;
        QList<bool> shows = file_shows_, atts = file_attl_;
        const int at = sel_file_;
        paths.removeAt(at);
        shows.removeAt(at);
        atts.removeAt(at);
        QStringList labels;
        for (const QString& p : paths) labels << QFileInfo(p).fileName();
        if (paths.size() == 1) load_file(paths.first());
        else load_scene(paths, labels, {});
        file_shows_ = shows;  // keep each remaining file's Show / Atts choice
        file_attl_ = atts;
        if (view_)
            for (int i = 0; i < int(part_file_.size()); ++i) view_->setShown(i, file_shows_.value(part_file_[i], true));
        publish();
        return;
    } else if (id == QLatin1String("clearMesh") || id == QLatin1String("removeMesh")) {
        scene_ = false;
        scene_paths_.clear();
        file_shows_.clear();
        file_attl_.clear();
        part_file_.clear();
        sel_file_ = 0;
        shortcut_.clear();
        rows_.clear();
        mats_.clear();
        file_bytes_.clear();
        path_.clear();
        welcome_ = true;
        editor_open_ = false;
        bounds_set_ = false;
        anims_ = 0;
        stop_anim();
        clips_.clear();
        file_clip_.clear();
        if (view_) view_->setFileAnims({});
        att_count_ = 0;
        att_rows_.clear();
        att_i_ = -1;
        clear_history();
        if (view_) {
            view_->setParts({});
            view_->setAttachments({});
        }
        publish();
        return;
    } else if (id == QLatin1String("save") || id == QLatin1String("saveAs")) {
        save_files(id == QLatin1String("saveAs"));
    } else if (id == QLatin1String("color") || id == QLatin1String("emisPick") || id == QLatin1String("specPick")) {
        if (mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size())) return;
        const auto undo = qScopeGuard([this, before = snap()] { record(before); });
        TzMaterial& block = mats_[static_cast<size_t>(mat_i_)].block;
        float* dest = id == QLatin1String("color") ? block.color : id == QLatin1String("emisPick") ? block.emissive : block.specular;
        const QString title = id == QLatin1String("color") ? QStringLiteral("Material Color") : id == QLatin1String("emisPick") ? QStringLiteral("Emissive") : QStringLiteral("Specular");
        const QColor start(byte_of(dest[0]), byte_of(dest[1]), byte_of(dest[2]), byte_of(dest[3]));
        const QColor picked = QColorDialog::getColor(start, nullptr, title, QColorDialog::ShowAlphaChannel);
        if (!picked.isValid()) return;
        dest[0] = picked.red() / 255.f;
        dest[1] = picked.green() / 255.f;
        dest[2] = picked.blue() / 255.f;
        dest[3] = picked.alpha() / 255.f;
        dirty_ = true;
        if (id == QLatin1String("color")) apply_mat_color_preview(mat_i_);
        post_status(title + QStringLiteral(" set · Save to write the file"));
        publish();
    }
}

// Save writes every scene .trainzmesh (Save As: the selected one) and always reports the outcome.
void MeshBridge::save_files(bool ask) {
    auto tell = [](const QString& title, const QString& detail) {
        post_status(title + QStringLiteral(" — ") + detail);
        StatusHub::instance()->notify(QStringLiteral("info"), title, detail);
    };
    if (scene_paths_.isEmpty() || loading_) {
        tell(QStringLiteral("Nothing to save"), QStringLiteral("open a mesh first"));
        return;
    }
    file_bytes_.resize(static_cast<size_t>(scene_paths_.size()));
    QList<int> files;
    if (ask) files << std::clamp(scene_ ? sel_file_ : 0, 0, static_cast<int>(scene_paths_.size()) - 1);
    else
        for (int f = 0; f < scene_paths_.size(); ++f) files << f;
    QStringList saved, preview, failed;
    for (const int f : files) {
        const QString src = scene_paths_[f];
        const bool tz = src.endsWith(QLatin1String(".trainzmesh"), Qt::CaseInsensitive);
        QString dest = src;
        if (ask) {
            dest = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Save %1 as").arg(QFileInfo(src).fileName()), src, tz ? QStringLiteral("Trainz mesh (*.trainzmesh)") : QStringLiteral("Mesh (*.im *.fbx)"));
            if (dest.isEmpty()) {
                post_status(QStringLiteral("Save As cancelled"));
                return;
            }
        }
        const QString name = QFileInfo(dest).fileName();
        const QByteArray& before = file_bytes_[static_cast<size_t>(f)];
        bool wrote = false;
        if (tz && !before.isEmpty()) {
            QByteArray data = before;
            // Offsets come from the bytes as they are now: an earlier save may have resized a string.
            const auto* raw = reinterpret_cast<const uint8_t*>(before.constData());
            std::vector<TzMaterial> now_blocks;
            std::vector<TzAttachment> now_atts;
            try {
                now_blocks = parse_tzmf_materials(raw, static_cast<size_t>(before.size()));
                now_atts = parse_trainzmesh_attachments(raw, static_cast<size_t>(before.size()));
            } catch (const std::exception&) {
                failed << name;
                continue;
            }
            std::vector<TzMaterial> blocks;
            for (const MatEdit& edit : mats_) {
                if (edit.file != f || edit.gizmo >= 0 || edit.block.name_off == 0 || blocks.size() >= now_blocks.size()) continue;
                const TzMaterial& at = now_blocks[blocks.size()];
                TzMaterial block = edit.block;
                block.name_off = at.name_off;
                block.type_off = at.type_off;
                block.color_off = at.color_off;
                block.emissive_off = at.emissive_off;
                block.specular_off = at.specular_off;
                block.spec_power_off = at.spec_power_off;
                if (block.textures.size() > at.textures.size()) block.textures.resize(at.textures.size());
                for (size_t t = 0; t < block.textures.size(); ++t) block.textures[t].value_off = at.textures[t].value_off;
                blocks.push_back(std::move(block));
            }
            for (const TzMaterial& block : blocks) {
                if (block.color_off) {
                    for (int c = 0; c < 4; ++c) write_be_f32(data, static_cast<int>(block.color_off) + c * 4, block.color[c]);
                }
                if (block.emissive_off >= 0)
                    for (int c = 0; c < 4; ++c) write_le_f32(data, block.emissive_off + c * 4, block.emissive[c]);
                if (block.specular_off >= 0)
                    for (int c = 0; c < 4; ++c) write_le_f32(data, block.specular_off + c * 4, block.specular[c]);
                if (block.spec_power_off >= 0) write_le_f32(data, block.spec_power_off, block.spec_power);
            }
            // load_scene spun a yawed file about Z; spin back, and leave untouched attachments as read.
            const double yaw = scene_yaws_.value(f, 0.0);
            const float yc = static_cast<float>(std::cos(-yaw)), ys = static_cast<float>(std::sin(-yaw));
            auto unspin = [&](float& x, float& y) {
                const float nx = x * yc - y * ys;
                y = x * ys + y * yc;
                x = nx;
            };
            size_t att_k = 0;
            for (size_t i = 0; i < att_rows_.size(); ++i) {
                ViewAtt att = att_rows_[i];
                if (att.file != f || att.off < 0 || att_k >= now_atts.size()) continue;
                att.off = static_cast<int>(now_atts[att_k++].off);
                const ViewAtt* base = i < att_base_.size() ? &att_base_[i] : nullptr;
                const bool moved = !base || std::memcmp(base->pos, att.pos, sizeof(att.pos)) != 0;
                const bool turned = !base || std::memcmp(base->quat, att.quat, sizeof(att.quat)) != 0;
                if (yaw != 0.0) {
                    unspin(att.pos[0], att.pos[1]);
                    for (int axis = 0; axis < 3; ++axis) unspin(att.orient[axis * 3], att.orient[axis * 3 + 1]);
                    quat_from_orient(att);
                }
                if (moved)
                    for (int c = 0; c < 3; ++c) write_be_f32(data, att.off + c * 4, att.pos[c]);
                if (turned)
                    for (int c = 0; c < 4; ++c) write_be_f32(data, att.off + 12 + c * 4, att.quat[c]);
            }
            struct Patch {
                int off;
                QByteArray text;
            };
            std::vector<Patch> patches;
            auto queue = [&](size_t off, const std::string& now) {
                if (off + 4 > static_cast<size_t>(before.size())) return;
                quint32 n = 0;
                std::memcpy(&n, before.constData() + off, 4);
                if (off + 4 + n > static_cast<size_t>(before.size()) || n < 1) return;
                const QByteArray old(before.constData() + off + 4, static_cast<int>(n - 1));
                const QByteArray next = QByteArray::fromStdString(now);
                if (old == next) return;
                patches.push_back({static_cast<int>(off), next});
            };
            for (const TzMaterial& block : blocks) {
                queue(block.name_off, block.name);
                queue(block.type_off, block.type_name);
                for (const TzTex& tex : block.textures) queue(tex.value_off, tex.value);
            }
            std::sort(patches.begin(), patches.end(), [](const Patch& a, const Patch& b) { return a.off > b.off; });
            for (const Patch& patch : patches) data = replace_le_string(data, patch.off, patch.text);
            if (ask || !scene_ || data != before) {
                const QString bak = dest + QStringLiteral(".bak");
                if (!QFileInfo::exists(bak)) QFile::copy(dest, bak);
                QSaveFile out(dest);
                if (!out.open(QIODevice::WriteOnly) || out.write(data) != data.size() || !out.commit()) {
                    failed << name;
                    continue;
                }
                file_bytes_[static_cast<size_t>(f)] = data;
                for (size_t i = 0; i < att_rows_.size() && i < att_base_.size(); ++i)
                    if (att_rows_[i].file == f) att_base_[i] = att_rows_[i];
                wrote = true;
            }
        }
        // Two-sided flags live in the .meta beside the mesh (any format). Save As starts from the source's flags.
        const QString meta_path = meta_path_for(dest);
        QString meta_text;
        QFile meta_in(QFileInfo::exists(meta_path) ? meta_path : meta_path_for(src));
        if (meta_in.open(QIODevice::ReadOnly)) meta_text = QString::fromUtf8(meta_in.readAll());
        const QString meta_was = QFileInfo::exists(meta_path) ? meta_text : QString();
        for (const MatEdit& edit : mats_) {
            if (edit.file != f || edit.gizmo >= 0 || (scene_ && edit.block.name_off == 0)) continue;
            const QString name = QString::fromStdString(edit.block.name);
            if (name.isEmpty()) continue;
            const QString flag = edit.two ? QStringLiteral("1") : QStringLiteral("0");
            int at = meta_text.indexOf(name);
            if (at < 0) {
                if (!edit.two) continue;
                if (!meta_text.contains(QLatin1String("materials"))) meta_text += QStringLiteral("\nmaterials\n{\n}\n");
                const int close = meta_text.lastIndexOf(QLatin1Char('}'));
                meta_text.insert(std::max(0, close), QStringLiteral("  %1\n  {\n    two-sided %2\n  }\n").arg(name, flag));
                continue;
            }
            const int brace = meta_text.indexOf(QLatin1Char('{'), at);
            const int end = meta_text.indexOf(QLatin1Char('}'), brace);
            const int tag = meta_text.indexOf(QLatin1String("two-sided"), brace);
            if (brace < 0 || end < 0 || tag < 0 || tag > end) {
                if (end > 0) meta_text.insert(end, QStringLiteral("\n    two-sided %1\n  ").arg(flag));
                continue;
            }
            int value = tag + 9;
            while (value < meta_text.size() && meta_text[value].isSpace()) ++value;
            int value_end = value;
            while (value_end < meta_text.size() && !meta_text[value_end].isSpace() && meta_text[value_end] != QLatin1Char('}')) ++value_end;
            meta_text.replace(value, value_end - value, flag);
        }
        if (meta_text != meta_was) {
            QSaveFile meta_out(meta_path);
            const QByteArray meta_bytes = meta_text.toUtf8();
            if (!meta_out.open(QIODevice::WriteOnly) || meta_out.write(meta_bytes) != meta_bytes.size() || !meta_out.commit()) {
                failed << QFileInfo(meta_path).fileName();
                continue;
            }
            wrote = true;
        }
        if (!tz) preview << name;
        if (!wrote) continue;
        saved << name;
        if (ask) {
            scene_paths_[f] = dest;
            if (!scene_) path_ = dest;
        }
    }
    if (failed.isEmpty()) dirty_ = false;
    if (!saved.isEmpty()) {
        shortcut_ = saved.join(QStringLiteral(", ")) + QStringLiteral(" saved");
        post_status(QStringLiteral("Saved ") + saved.join(QStringLiteral(", ")) + (preview.isEmpty() ? QString() : QStringLiteral(" · %1: two-sided flags only").arg(preview.join(QStringLiteral(", ")))));
    }
    if (!failed.isEmpty()) post_status(QStringLiteral("Save failed — cannot write ") + failed.join(QStringLiteral(", ")));
    else if (saved.isEmpty() && !preview.isEmpty())
        tell(QStringLiteral("Not saved"), preview.join(QStringLiteral(", ")) + QStringLiteral(" is preview only — Save writes .trainzmesh files (and two-sided flags)"));
    else if (saved.isEmpty())
        tell(QStringLiteral("No changes to save"), QStringLiteral("every mesh already matches its file"));
    publish();
}
void MeshBridge::setChecked(const QString& key, bool on) {
    const auto undo = qScopeGuard([this, before = snap()] { record(before); });
    if (key == QLatin1String("sun")) {
        sun_ = on;
        if (on) moon_ = false;
        if (view_) {
            view_->setSun(on);
            view_->setMoon(moon_);
        }
    } else if (key.startsWith(QLatin1String("light")) && key.size() == 6 && key[5].isDigit()) {
        const int index = key[5].digitValue();
        if (index >= 0 && index < 5) {
            array_on_[index] = on;
            if (view_) view_->setArrayLight(index, on);
        }
    } else if (key == QLatin1String("ground")) {
        ground_ = on;
        if (view_) view_->setGround(on);
    } else if (key == QLatin1String("two")) {
        if (mat_i_ >= 0 && mat_i_ < static_cast<int>(mats_.size())) {
            MatEdit& edit = mats_[static_cast<size_t>(mat_i_)];
            edit.two = on;
            dirty_ = true;
            const QString name = QString::fromStdString(edit.block.name);
            for (int i = 0; i < static_cast<int>(rows_.size()); ++i) {
                if (rows_[static_cast<size_t>(i)].name.compare(name, Qt::CaseInsensitive) != 0 && rows_[static_cast<size_t>(i)].material.compare(name, Qt::CaseInsensitive) != 0) continue;
                rows_[static_cast<size_t>(i)].two = on;
                if (view_) view_->setPartTwo(i, on);
            }
        }
    } else if (key.startsWith(QLatin1String("fileShow:")) || key.startsWith(QLatin1String("fileAtts:"))) {
        const int f = key.mid(9).toInt();
        if (f >= 0 && f < scene_paths_.size()) {
            if (key.startsWith(QLatin1String("fileShow:"))) {
                file_shows_[f] = on;
                if (view_)
                    for (int i = 0; i < int(part_file_.size()); ++i)
                        if (part_file_[i] == f) view_->setShown(i, on);
            } else {
                file_attl_[f] = on;
                if (view_) view_->setAttFileShown(f, on);
            }
        }
    } else if (key == QLatin1String("fileShow")) {
        file_show_ = on;
        if (view_) {
            for (int i = 0; i < static_cast<int>(rows_.size()); ++i) view_->setShown(i, on);
        }
    } else if (key == QLatin1String("fileAtts")) {
        file_atts_ = on;
        if (view_) view_->setAttFileShown(0, on);
    } else if (key == QLatin1String("face")) {
        face_ = on;
        if (view_) view_->setFaceOrient(on);
    } else if (key == QLatin1String("attNames")) {
        att_names_ = on;
        if (view_) view_->setAttNames(on);
    }
    publish();
}
void MeshBridge::setCombo(const QString& key, int index) {
    const auto undo = qScopeGuard([this, before = snap()] { record(before); });
    if (key == QLatin1String("tod") && index >= 0 && index < 4) {
        const int az[4] = {92, 135, 255, 210};
        const int el[4] = {8, 48, 6, -8};
        const int inten[4] = {110, 140, 85, 20};
        tod_ = index;
        sun_az_ = az[index];
        sun_el_ = el[index];
        sun_int_ = inten[index];
        sun_ = index != 3;
        moon_ = index == 3;
        const float warm[4] = {0.35f, 0.f, 0.9f, 0.f};
        if (moon_) {
            for (int i = 0; i < 5; ++i) array_on_[i] = false;
        } else {
            for (int i = 0; i < 5; ++i) array_on_[i] = true;
        }
        if (view_) {
            view_->setSun(sun_);
            view_->setMoon(moon_);
            view_->setSunPose(static_cast<float>(sun_az_), static_cast<float>(sun_el_), sun_int_ / 100.f);
            view_->setSunWarm(warm[index]);
            for (int i = 0; i < 5; ++i) view_->setArrayLight(i, array_on_[i]);
        }
    } else if (key == QLatin1String("env")) {
        env_i_ = index;
        if (view_) view_->setEnvironment(index);
    } else if (key == QLatin1String("type") && mat_i_ >= 0 && mat_i_ < static_cast<int>(mats_.size())) {
        const char* type_names[] = {"pbrmetal", "pbrmetalmasked", "pbrmetaldetail", "pbrmetalspec", "StdOneTex", "glass", "clutter", "foliage"};
        MatEdit& edit = mats_[static_cast<size_t>(mat_i_)];
        const QString cur_type = QString::fromStdString(edit.block.type_name);
        bool known = false;
        for (const char* name : type_names) {
            if (cur_type.compare(QLatin1String(name), Qt::CaseInsensitive) == 0) known = true;
        }
        int at = index;
        if (!known && !edit.block.type_name.empty()) {
            if (index == 0) {
                publish();
                return;
            }
            at = index - 1;
        }
        if (at >= 0 && at < 8) {
            edit.block.type_name = type_names[at];
            dirty_ = true;
            post_status(QStringLiteral("Type → %1 · Save to write the file").arg(QString::fromLatin1(type_names[at])));
        }
    }
    publish();
}
void MeshBridge::setText(const QString& key, const QString& text) {
    const auto undo = qScopeGuard([this, before = snap()] { record(before); });
    if (mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size())) return;
    MatEdit& edit = mats_[static_cast<size_t>(mat_i_)];
    if (key == QLatin1String("matName")) {
        edit.block.name = text.toStdString();
        dirty_ = true;
    }
    else if (key.startsWith(QLatin1String("tex:"))) {
        const QString slot = key.mid(4);
        // Resolve parts before the slot value changes (stem match still uses the old albedo).
        const std::vector<int> parts = parts_for_mat(mat_i_);
        bool changed = false;
        for (TzTex& tex : edit.block.textures) {
            if (QString::fromStdString(tex.key) == slot) {
                tex.value = text.toStdString();
                dirty_ = true;
                changed = true;
            }
        }
        if (changed) {
            if (parts.empty() && edit.gizmo < 0) {
                QString shown = QString::fromStdString(edit.block.name).trimmed();
                if (shown.isEmpty()) shown = QStringLiteral("(unnamed)");
                post_status(QStringLiteral("Texture set for Save, but “%1” is not on any geometry — preview unchanged").arg(shown));
            } else {
                apply_mat_tex_preview(mat_i_, slot, text, parts);
            }
            sync_highlight();
        }
    } else return;
    publish();
}
void MeshBridge::setSpin(const QString& key, double value) {
    const auto undo = qScopeGuard([this, before = snap()] { record(before); });
    const int k = key.size() == 4 ? key[3].digitValue() : -1;
    if (key.startsWith(QLatin1String("loc")) && k >= 0 && k < 3 && att_i_ >= 0 && std::isfinite(value)) {
        att_edit_.pos[k] = static_cast<float>(value);
        apply_att();
    } else if (key.startsWith(QLatin1String("rot")) && k >= 0 && k < 3 && att_i_ >= 0 && std::isfinite(value)) {
        double deg[3] = {};
        att_euler(att_edit_.quat, deg);
        deg[k] = value;
        att_quat(deg, att_edit_.quat);
        apply_att();
    } else if (key == QLatin1String("spec") && mat_i_ >= 0 && mat_i_ < static_cast<int>(mats_.size())) {
        mats_[static_cast<size_t>(mat_i_)].block.spec_power = static_cast<float>(value);
        dirty_ = true;
    }
    publish();
}
void MeshBridge::setSlider(const QString& key, int value) {
    if (key == QLatin1String("frame")) {
        if (anim_i_ >= 0 && anim_i_ < static_cast<int>(clips_.size())) {
            HeldKin& held = clips_[static_cast<size_t>(anim_i_)];
            held.playing = false;
            held.frame = std::clamp(value, 0, std::max(0, static_cast<int>(held.clip.frames.size()) - 1));
            own_file(anim_i_);
            apply_frame();
        }
        publish();
        return;
    }
    if (key == QLatin1String("az")) {
        sun_az_ = std::clamp(value, 0, 360);
        tod_ = -1;
        if (view_) view_->setSunWarm(0.f);
    }
    else if (key == QLatin1String("el")) sun_el_ = std::clamp(value, -10, 89);
    else if (key == QLatin1String("sunInt")) sun_int_ = std::clamp(value, 20, 500);
    else if (key == QLatin1String("emis")) emis_ = std::clamp(value, 0, 200);
    else return;
    if (view_) {
        view_->setSunPose(static_cast<float>(sun_az_), static_cast<float>(sun_el_), sun_int_ / 100.f);
        view_->setEmissiveScale(emis_ / 100.f);
    }
    publish();
}
void MeshBridge::setChannel(const QString& which, int index, double value) {
    const auto undo = qScopeGuard([this, before = snap()] { record(before); });
    if (mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size()) || index < 0 || index > 3) return;
    float* dest = nullptr;
    TzMaterial& block = mats_[static_cast<size_t>(mat_i_)].block;
    if (which == QLatin1String("color")) dest = block.color;
    else if (which == QLatin1String("emis")) dest = block.emissive;
    else if (which == QLatin1String("spec")) dest = block.specular;
    if (!dest) return;
    dest[index] = static_cast<float>(value) / 255.f;
    dirty_ = true;
    if (which == QLatin1String("color")) apply_mat_color_preview(mat_i_);
    publish();
}
void MeshBridge::pickList(const QString& list, int index) {
    if (list == QLatin1String("anim") && index >= 0 && index < static_cast<int>(clips_.size())) {
        anim_i_ = index;
        own_file(index);
        apply_frame();
    } else if (list == QLatin1String("mesh") && index >= 0 && index < static_cast<int>(mats_.size())) {
        mat_i_ = index;
        sync_highlight();
        focus_selection();
        note_mat_geo();
    } else if (list == QLatin1String("atts") && index >= 0 && index < static_cast<int>(att_rows_.size())) {
        pick_att(index);
        if (view_) view_->setAttSelected(index);
    } else if (list == QLatin1String("scene") && index >= 0 && index < static_cast<int>(rows_.size())) selected_ = index;
    else return;
    publish();
}
void MeshBridge::pickMat(int index) {
    if (index < 0 || index >= static_cast<int>(mat_owner_.size())) return;
    mat_i_ = mat_owner_[static_cast<size_t>(index)];
    sync_highlight();
    focus_selection();
    note_mat_geo();
    publish();
}
void MeshBridge::focus_selection() {
    if (!view_ || mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size())) return;
    const int gizmo = mats_[static_cast<size_t>(mat_i_)].gizmo;
    if (gizmo >= 0) {
        view_->setAttSelected(gizmo);
        return;
    }
    view_->setAttSelected(-1);
    view_->flyToHighlight();
}
QString MeshBridge::mesh_path_for(int file) const {
    if (scene_ && file >= 0 && file < scene_paths_.size()) return scene_paths_[file];
    return path_;
}

std::vector<int> MeshBridge::parts_for_mat(int mat_i) const {
    std::vector<int> out;
    if (mat_i < 0 || mat_i >= static_cast<int>(mats_.size())) return out;
    const MatEdit& edit = mats_[static_cast<size_t>(mat_i)];
    if (edit.gizmo >= 0) return out;
    const QString name = QString::fromStdString(edit.block.name);
    auto stem = [](QString s) {
        s = QFileInfo(s.trimmed()).fileName().toLower();
        return s.section(QLatin1Char('.'), 0, 0);
    };
    QSet<QString> stems;
    for (const TzTex& tex : edit.block.textures) {
        const QString s = stem(QString::fromStdString(tex.value));
        if (!s.isEmpty() && !s.startsWith(QLatin1Char('$'))) stems.insert(s);
    }
    for (int i = 0; i < static_cast<int>(rows_.size()); ++i) {
        if (part_file_.value(i) != edit.file) continue;
        const MeshRow& row = rows_[static_cast<size_t>(i)];
        const bool named = !name.isEmpty() && (row.name.compare(name, Qt::CaseInsensitive) == 0 || row.material.compare(name, Qt::CaseInsensitive) == 0);
        if (named || (!row.albedo.isEmpty() && stems.contains(stem(row.albedo)))) out.push_back(i);
    }
    return out;
}

void MeshBridge::paint_drawn_colors(std::vector<ViewPart>& drawn) const {
    for (int m = 0; m < static_cast<int>(mats_.size()); ++m) {
        const float* c = mats_[static_cast<size_t>(m)].block.color;
        for (int i : parts_for_mat(m)) {
            if (i < 0 || i >= static_cast<int>(drawn.size())) continue;
            drawn[static_cast<size_t>(i)].color[0] = c[0];
            drawn[static_cast<size_t>(i)].color[1] = c[1];
            drawn[static_cast<size_t>(i)].color[2] = c[2];
        }
    }
}

void MeshBridge::apply_mat_color_preview(int mat_i) {
    if (!view_ || mat_i < 0 || mat_i >= static_cast<int>(mats_.size())) return;
    const float* c = mats_[static_cast<size_t>(mat_i)].block.color;
    for (int i : parts_for_mat(mat_i)) view_->setPartColor(i, c[0], c[1], c[2]);
}

void MeshBridge::note_mat_geo() {
    if (mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size())) return;
    const MatEdit& edit = mats_[static_cast<size_t>(mat_i_)];
    if (edit.gizmo >= 0) return;  // attachment row, not a mesh material
    if (rows_.empty()) {
        post_status(QStringLiteral("No geometry loaded"));
        return;
    }
    if (!parts_for_mat(mat_i_).empty()) return;
    QString name = QString::fromStdString(edit.block.name).trimmed();
    if (name.isEmpty()) name = QStringLiteral("(unnamed)");
    post_status(QStringLiteral("“%1” is not on any geometry").arg(name));
}

void MeshBridge::apply_mat_tex_preview(int mat_i, const QString& slot, const QString& value, const std::vector<int>& parts) {
    if (!view_ || parts.empty() || mat_i < 0 || mat_i >= static_cast<int>(mats_.size())) return;
    const QString low = slot.toLower();
    if (value.startsWith(QLatin1Char('$')) || low.contains(QLatin1String("env"))) return;
    int map = 0;
    if (low == QLatin1String("txnormal") || low == QLatin1String("normal"))
        map = 1;
    else if (low == QLatin1String("txparameters") || low == QLatin1String("parameters") || low == QLatin1String("param"))
        map = 2;
    else if (!(low == QLatin1String("txalbedo") || low == QLatin1String("texture0") || low == QLatin1String("texdiffuse") || low == QLatin1String("diffuse") || low == QLatin1String("albedo")))
        map = 0;  // unknown editable slot → albedo for Live preview
    const QString mesh = mesh_path_for(mats_[static_cast<size_t>(mat_i)].file);
    const TexPixels pix = decode_named(mesh, value);
    if (pix.rgba.empty()) {
        post_status(QStringLiteral("Texture set for Save, but no image found beside the mesh for “") + value + QStringLiteral("”"));
        return;
    }
    for (int i : parts) {
        if (i < 0 || i >= static_cast<int>(rows_.size())) continue;
        if (map == 0) {
            rows_[static_cast<size_t>(i)].albedo = value;
            rows_[static_cast<size_t>(i)].tex_file = pix.path;
        }
        view_->setPartPixels(i, map, pix.rgba, pix.w, pix.h);
    }
    post_status(QStringLiteral("Preview · ") + QFileInfo(pix.path).fileName());
}

void MeshBridge::refresh_mat_tex_previews(int mat_i) {
    if (!view_ || mat_i < 0 || mat_i >= static_cast<int>(mats_.size())) return;
    const std::vector<int> parts = parts_for_mat(mat_i);
    if (parts.empty()) return;
    const QString mesh = mesh_path_for(mats_[static_cast<size_t>(mat_i)].file);
    for (const TzTex& tex : mats_[static_cast<size_t>(mat_i)].block.textures) {
        const QString key = QString::fromStdString(tex.key);
        const QString value = QString::fromStdString(tex.value);
        const QString low = key.toLower();
        if (value.startsWith(QLatin1Char('$')) || low.contains(QLatin1String("env"))) continue;
        int map = 0;
        if (low == QLatin1String("txnormal") || low == QLatin1String("normal")) map = 1;
        else if (low == QLatin1String("txparameters") || low == QLatin1String("parameters") || low == QLatin1String("param")) map = 2;
        const TexPixels pix = decode_named(mesh, value);
        if (pix.rgba.empty()) continue;
        for (int i : parts) {
            if (i < 0 || i >= static_cast<int>(rows_.size())) continue;
            if (map == 0) {
                rows_[static_cast<size_t>(i)].albedo = value;
                rows_[static_cast<size_t>(i)].tex_file = pix.path;
            }
            view_->setPartPixels(i, map, pix.rgba, pix.w, pix.h);
        }
    }
}

void MeshBridge::sync_highlight() {
    if (!view_ || mat_i_ < 0 || mat_i_ >= static_cast<int>(mats_.size())) return;
    const std::vector<int> parts = parts_for_mat(mat_i_);
    std::vector<uint8_t> on(rows_.size(), 0);
    for (int i : parts)
        if (i >= 0 && i < static_cast<int>(on.size())) on[static_cast<size_t>(i)] = 1;
    view_->setHighlight(std::move(on));
}
void MeshBridge::toggleMesh(int index, int column) {
    if (index < 0 || index >= static_cast<int>(rows_.size())) return;
    MeshRow& row = rows_[static_cast<size_t>(index)];
    if (column == 0) {
        row.show = !row.show;
        if (view_) view_->setShown(index, row.show);
    } else if (column == 1) {
        row.atts = !row.atts;
    } else {
        row.open = !row.open;
    }
    publish();
}
void MeshBridge::toggleSceneMesh(int index) { toggleMesh(index, 0); }
void MeshBridge::cancelBake() {}
void MeshBridge::placeSide(double x, double y, double w, double h) {
    blur_side_ = QRect(qRound(x), qRound(y), qRound(w), qRound(h));
    if (view_) view_->setBlurRects(blur_side_, blur_editor_);
}
void MeshBridge::placeEditor(double x, double y, double w, double h) {
    blur_editor_ = QRect(qRound(x), qRound(y), qRound(w), qRound(h));
    if (view_) view_->setBlurRects(blur_side_, blur_editor_);
}
void MeshBridge::placeSettings(double, double, double, double) {}

void MeshBridge::navDrag(double dx, double dy) {
    if (view_) view_->orbitDrag(static_cast<float>(dx), static_cast<float>(dy));
}

void MeshBridge::navAxis(int axis) {
    if (view_) view_->lookAxis(axis);
}

void MeshBridge::refresh_nav() {
    if (!view_) return;
    float tip[9] = {};
    view_->navTips(tip);
    const QString next = QStringLiteral("{\"x\":[%1,%2,%3],\"y\":[%4,%5,%6],\"z\":[%7,%8,%9]}")
                             .arg(tip[0], 0, 'f', 4)
                             .arg(tip[1], 0, 'f', 4)
                             .arg(tip[2], 0, 'f', 4)
                             .arg(tip[3], 0, 'f', 4)
                             .arg(tip[4], 0, 'f', 4)
                             .arg(tip[5], 0, 'f', 4)
                             .arg(tip[6], 0, 'f', 4)
                             .arg(tip[7], 0, 'f', 4)
                             .arg(tip[8], 0, 'f', 4);
    if (next == nav_json_) return;
    nav_json_ = next;
    emit navChanged();
}

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
    view_->setSource(res_url(qml_file()));
    view_->raise();
    view_->installEventFilter(this);
    qApp->installEventFilter(this);
    if (QLabel* hud = gl_->findChild<QLabel*>()) {
        hud->setParent(this);
        hud->raise();
    }
    bridge_->attach(gl_, view_);
}

void MeshStudioPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (gl_) gl_->setGeometry(rect());
    if (view_) {
        view_->setGeometry(rect());
        view_->raise();
    }
    if (QLabel* hud = findChild<QLabel*>()) hud->raise();
}

bool MeshStudioPage::text_has_tab() const {
    if (!view_) return false;
    QQuickWindow* window = view_->quickWindow();
    QQuickItem* item = window ? window->activeFocusItem() : nullptr;
    while (item) {
        const QByteArray name = item->metaObject()->className();
        if (name.contains("TextInput") || name.contains("TextEdit") || name.contains("TextArea")) return true;
        item = item->parentItem();
    }
    return false;
}

bool MeshStudioPage::filter_tab(QEvent* event) {
    if (!isVisible() || !bridge_ || !view_) return false;
    const bool press = event->type() == QEvent::KeyPress || event->type() == QEvent::ShortcutOverride;
    const bool release = event->type() == QEvent::KeyRelease;
    if (!press && !release) return false;
    auto* key = static_cast<QKeyEvent*>(event);
    const bool tab = key->key() == Qt::Key_Tab || key->key() == Qt::Key_Backtab;
    if (press && key->key() == Qt::Key_Escape && !key->isAutoRepeat() && bridge_->pieOpen()) {
        bridge_->cancelPie();
        return true;
    }
    if (!tab || text_has_tab()) return false;
    if (key->isAutoRepeat()) return true;
    if (press) {
        if (!bridge_->pieOpen()) {
            tab_clock_.restart();
            const QPoint local = view_->mapFromGlobal(QCursor::pos());
            bridge_->armPie(local.x(), local.y());
        }
        return true;
    }
    bridge_->releasePie(tab_clock_.isValid() ? tab_clock_.elapsed() : 1000);
    return true;
}

bool MeshStudioPage::eventFilter(QObject* watched, QEvent* event) {
    Q_UNUSED(watched);
    if (filter_tab(event)) return true;
    if (watched == view_ && gl_ && (event->type() == QEvent::KeyPress || event->type() == QEvent::KeyRelease)) {
        auto* key = static_cast<QKeyEvent*>(event);
        const int code = key->key();
        const bool walk = code == Qt::Key_Up || code == Qt::Key_Down || code == Qt::Key_Left || code == Qt::Key_Right || code == Qt::Key_PageUp || code == Qt::Key_PageDown || code == Qt::Key_F3 || code == Qt::Key_R;
        if (walk) {
            const bool press = event->type() == QEvent::KeyPress;
            if (key->isAutoRepeat() && !press) return true;
            if (code == Qt::Key_F3 && press && !key->isAutoRepeat()) gl_->toggleFps();
            else if (code == Qt::Key_R && press && !key->isAutoRepeat()) gl_->resetCamera();
            else if (code != Qt::Key_F3 && code != Qt::Key_R) gl_->setWalk(code, press);
            return true;
        }
    }
    return QWidget::eventFilter(watched, event);
}

bool MeshStudioPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList MeshStudioPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void MeshStudioPage::loadFile(const QString& path) { bridge_->load_file(path); }
bool MeshStudioPage::loadOpen() const { return bridge_->loadOpen(); }
int MeshStudioPage::loadSteps() const { return bridge_->loadSteps(); }
QString MeshStudioPage::sideJson() const { return bridge_->sideJson(); }
QImage MeshStudioPage::grabView() { return gl_ ? gl_->grabFramebuffer() : QImage(); }
bool MeshStudioPage::pieOpen() const { return bridge_ && bridge_->pieOpen(); }

void MeshStudioPage::loadScene(const QStringList& paths, const QStringList& labels, const QList<double>& yaws) { bridge_->load_scene(paths, labels, yaws); }
