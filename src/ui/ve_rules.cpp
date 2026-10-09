#include "ve_rules.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QImageReader>
#include <QRandomGenerator>
#include <QRegularExpression>
#include <QSet>
#include <QtEndian>

#include <algorithm>
#include <cmath>
#include <cstring>

#include "io/lm_txt.h"
#include "io/mat_name.h"
#include "io/texture_txt.h"
#include "io/trainzmesh.h"

namespace {

constexpr int k_high_poly_faces = 5000;  // VE81 soft threshold when no sibling .lm.txt
constexpr int k_max_tex_dim = 4096;
const QStringList k_image_exts = {QStringLiteral(".png"), QStringLiteral(".tga"), QStringLiteral(".jpg"), QStringLiteral(".jpeg"), QStringLiteral(".bmp"), QStringLiteral(".dds")};
const QStringList k_obsolete_tags = {QStringLiteral("light"), QStringLiteral("nightmode"), QStringLiteral("cabinsway")};

const QRegularExpression& re(const char* pattern) {
    static QHash<const char*, QRegularExpression> cache;
    auto it = cache.find(pattern);
    if (it == cache.end()) it = cache.insert(pattern, QRegularExpression(QString::fromLatin1(pattern), QRegularExpression::CaseInsensitiveOption | QRegularExpression::MultilineOption));
    return *it;
}

VeFinding finding(int code, const char* level, const QString& path, const QString& message, bool fixable = false, const char* kind = "") {
    return {code, QString::fromLatin1(level), path, message, fixable, QString::fromLatin1(kind)};
}

QString suffix_of(const QString& path) {
    const QString name = QFileInfo(path).fileName().toLower();
    const qsizetype dot = name.lastIndexOf(QLatin1Char('.'));
    return dot < 0 ? QString() : name.mid(dot);
}
bool is_image(const QString& path) { return k_image_exts.contains(suffix_of(path)); }
bool is_texture_txt(const QString& path) {
    const QString low = path.toLower();
    return low.endsWith(QLatin1String(".texture.txt")) || low.endsWith(QLatin1String(".texture"));
}
bool is_lm(const QString& path) {
    const QString low = path.toLower();
    return low.endsWith(QLatin1String(".lm.txt")) || low.endsWith(QLatin1String(".lm"));
}
bool is_mesh(const QString& path) {
    static const QStringList exts = {QStringLiteral(".trainzmesh"), QStringLiteral(".im"), QStringLiteral(".fbx"), QStringLiteral(".pm")};
    return exts.contains(suffix_of(path));
}
QString stem(const QString& path) { return QFileInfo(path).completeBaseName(); }
QString sibling(const QString& path, const QString& name) { return QFileInfo(path).dir().filePath(name); }

QByteArray read_bytes(const QString& path, qint64 max = -1) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    return max < 0 ? file.readAll() : file.read(max);
}
QString read_text(const QString& path) { return QString::fromUtf8(read_bytes(path)); }

bool power_of_two(int n) { return n > 0 && (n & (n - 1)) == 0; }
int pot_down(int n) {
    int v = 1;
    while (v * 2 <= n) v *= 2;
    return v;
}

QSize image_size(const QString& path) {
    QImageReader reader(path);
    QSize size = reader.size();
    if (size.isValid()) return size;
    const QByteArray head = read_bytes(path, 1 << 16);
    const auto wh = image_size_header(reinterpret_cast<const uint8_t*>(head.constData()), size_t(head.size()), suffix_of(path).toStdString());
    return {wh.first, wh.second};
}

void backup_once(const QString& path) {
    const QString bak = path + QStringLiteral(".bak");
    if (!QFileInfo::exists(bak)) QFile::copy(path, bak);
}

// Downsample to ≤64² then spot-check the full image (same as ve39.is_uniform_color).
bool uniform_color(const QImage& source, QColor* color, int tolerance = 2) {
    const QImage rgba = source.convertToFormat(QImage::Format_RGBA8888);
    const int w = rgba.width(), h = rgba.height();
    if (w < 1 || h < 1) return false;
    const QImage small = (w <= 64 && h <= 64) ? rgba : rgba.scaled(std::min(64, w), std::min(64, h), Qt::IgnoreAspectRatio, Qt::FastTransformation);
    const QRgb base = small.pixel(0, 0);
    *color = QColor::fromRgba(base);
    const auto near = [&](QRgb px) {
        return std::abs(qRed(px) - qRed(base)) <= tolerance && std::abs(qGreen(px) - qGreen(base)) <= tolerance
            && std::abs(qBlue(px) - qBlue(base)) <= tolerance && std::abs(qAlpha(px) - qAlpha(base)) <= tolerance;
    };
    for (int y = 0; y < small.height(); ++y)
        for (int x = 0; x < small.width(); ++x)
            if (!near(small.pixel(x, y))) return false;
    if (w * h > 4096) {
        const QPoint spots[] = {{0, 0}, {w - 1, 0}, {0, h - 1}, {w - 1, h - 1}, {w / 2, h / 2}, {w / 4, h / 4}, {3 * w / 4, 3 * h / 4}};
        for (const QPoint& p : spots)
            if (!near(rgba.pixel(p))) return false;
    }
    return true;
}

QString hex_of(const QColor& c) { return QStringLiteral("#%1%2%3").arg(c.red(), 2, 16, QLatin1Char('0')).arg(c.green(), 2, 16, QLatin1Char('0')).arg(c.blue(), 2, 16, QLatin1Char('0')).toUpper(); }

QString texture_key(const std::vector<std::pair<std::string, std::string>>& keys, const char* name) {
    for (const auto& row : keys)
        if (QString::fromStdString(row.first).compare(QLatin1String(name), Qt::CaseInsensitive) == 0) return QString::fromStdString(row.second);
    return {};
}

bool write_texture_txt(const QString& path, const std::vector<std::pair<std::string, std::string>>& keys) {
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    file.write(QByteArray::fromStdString(format_texture_txt(keys)));
    return true;
}

QStringList im_attachments(const QByteArray& data) {
    const auto u32 = [&](qsizetype at) { return qFromLittleEndian<quint32>(data.constData() + at); };
    if (data.size() < 12 || !data.startsWith("JIRF") || data.mid(8, 4) != "IDXM") throw std::runtime_error("not a JIRF/.im file");
    qsizetype off = 12;
    while (off + 8 <= data.size()) {
        const QByteArray tag = data.mid(off, 4);
        const qsizetype body = off + 8, size = u32(off + 4);
        if (body + size > data.size()) throw std::runtime_error("chunk walk ran past EOF");
        if (tag == "ATCH") {
            if (u32(body) != 100) throw std::runtime_error("unsupported ATCH version");
            const quint32 count = u32(body + 4);
            qsizetype p = body + 8;
            QStringList names;
            for (quint32 i = 0; i < count; ++i) {
                if (p + 4 > body + size) throw std::runtime_error("ATCH parse overrun");
                const qsizetype len = u32(p);
                p += 4;
                if (p + len + 48 > body + size) throw std::runtime_error("ATCH parse overrun");
                names << QString::fromUtf8(data.mid(p, len).split('\0').first());
                p += len + 48;  // 9 orient + 3 pos floats
            }
            return names;
        }
        off = body + size;
    }
    throw std::runtime_error("no ATCH chunk in this .im");
}

// tzMF: u8 len + "a.name" + 7× BE float32 (pos + quat). Jump via "a." — a byte walk is slow on big meshes.
QStringList trainzmesh_attachments(const QByteArray& data) {
    static const QRegularExpression name_re(QStringLiteral("^a\\.[A-Za-z0-9_]+$"));
    QStringList out;
    const qsizetype n = data.size();
    const auto be_float = [&](qsizetype at) {
        const quint32 bits = qFromBigEndian<quint32>(data.constData() + at);
        float v;
        std::memcpy(&v, &bits, 4);
        return v;
    };
    qsizetype j = 0;
    while ((j = data.indexOf("a.", j)) >= 1) {
        const int len = static_cast<unsigned char>(data[j - 1]);
        if (len < 3 || len > 64 || j + len + 28 > n) {
            ++j;
            continue;
        }
        const QString name = QString::fromLatin1(data.mid(j, len));
        if (!name_re.match(name).hasMatch()) {
            ++j;
            continue;
        }
        float f[7];
        bool finite = true;
        for (int i = 0; i < 7; ++i) finite = finite && std::isfinite(f[i] = be_float(j + len + 4 * i));
        const float qn = f[3] * f[3] + f[4] * f[4] + f[5] * f[5] + f[6] * f[6];
        if (!finite || qn < 0.25f || qn > 4.f || std::max({std::fabs(f[0]), std::fabs(f[1]), std::fabs(f[2])}) > 1.0e4f) {
            ++j;
            continue;
        }
        out << name;
        j += len + 28;
    }
    return out;
}

QString config_kind(const QString& text) {
    auto m = re(R"x(^\s*kind\s+"([^"]+)")x").match(text);
    if (!m.hasMatch()) m = re(R"x(^\s*kind\s+(\S+))x").match(text);
    return m.hasMatch() ? m.captured(1).remove(QLatin1Char('"')).trimmed().toLower() : QString();
}

QPair<QSet<QString>, QSet<QString>> config_meshes_atts(const QString& text) {
    QSet<QString> meshes, atts;
    for (auto it = re(R"x(^\s*mesh\s+"([^"]+\.(?:im|trainzmesh|fbx|lm))")x").globalMatch(text); it.hasNext();) meshes.insert(it.next().captured(1));
    for (auto it = re(R"x(^\s*(?:att|attachment)\s+"([^"]*)")x").globalMatch(text); it.hasNext();) atts.insert(it.next().captured(1));
    return {meshes, atts};
}

QStringList top_level_tags(const QString& text) {
    QStringList tags;
    for (const QString& raw : text.split(QLatin1Char('\n'))) {
        const QString line = raw.section(QStringLiteral("//"), 0, 0);
        if (line.trimmed().isEmpty() || line.at(0).isSpace()) continue;
        QString first = line.trimmed();
        first.replace(QLatin1Char('{'), QLatin1Char(' ')).replace(QLatin1Char('}'), QLatin1Char(' '));
        const QString key = first.section(QLatin1Char(' '), 0, 0, QString::SectionSkipEmpty).remove(QLatin1Char('"')).toLower();
        if (!key.isEmpty()) tags << key;
    }
    return tags;
}

int face_count(const QString& path) {
    const QByteArray bytes = read_bytes(path);
    try {
        const TrainzMesh mesh = parse_trainzmesh(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()));
        size_t faces = 0;
        for (const SubMesh& sub : mesh.submeshes) faces += sub.indices.size() / 3;
        return int(faces);
    } catch (const std::exception&) {
        return -1;
    }
}

QString missing_texture_note(const QString& image) { return QStringLiteral("missing %1.texture.txt").arg(stem(image)); }

QSet<QString> attachment_union(const QStringList& meshes) {
    QSet<QString> all;
    for (const QString& mesh : meshes)
        for (const QString& name : ve_attachment_names(mesh)) all.insert(name);
    return all;
}

}  // namespace

QList<int> VeReport::codes() const {
    QList<int> out;
    for (const VeFinding& f : findings)
        if (f.code > 0 && !out.contains(f.code)) out << f.code;
    std::sort(out.begin(), out.end());
    return out;
}

int VeReport::error_count() const { return int(std::count_if(findings.begin(), findings.end(), [](const VeFinding& f) { return f.level == QLatin1String("error"); })); }
int VeReport::warn_count() const { return int(std::count_if(findings.begin(), findings.end(), [](const VeFinding& f) { return f.level == QLatin1String("warn"); })); }

QString VeReport::status() const {
    if (findings.isEmpty()) return QStringLiteral("OK");
    QList<VeFinding> pool;
    for (const VeFinding& f : findings)
        if (f.level == QLatin1String("error")) pool << f;
    if (pool.isEmpty()) pool = findings;
    QList<int> shown, all;
    for (const VeFinding& f : pool) {
        if (f.code <= 0 || all.contains(f.code)) continue;
        all << f.code;
        if (shown.size() < 3) shown << f.code;
    }
    if (shown.isEmpty()) return pool.first().message.left(28);
    if (shown == QList<int>{39}) {
        for (const VeFinding& f : findings)
            if (f.code == 39 && f.message.contains(QLatin1Char('#'))) return QStringLiteral("VE39 #") + f.message.section(QLatin1Char('#'), -1).trimmed().left(6);
    }
    QStringList parts;
    for (int c : shown) parts << QStringLiteral("VE%1").arg(c);
    QString text = parts.join(QStringLiteral("·"));
    if (all.size() > shown.size()) text += QStringLiteral("+%1").arg(all.size() - shown.size());
    return text;
}

QStringList ve_attachment_names(const QString& path, QString* error) {
    const QString suf = suffix_of(path);
    try {
        if (suf == QLatin1String(".trainzmesh")) return trainzmesh_attachments(read_bytes(path));
        if (suf == QLatin1String(".im")) return im_attachments(read_bytes(path));
    } catch (const std::exception& e) {
        if (error) *error = QString::fromUtf8(e.what());
    }
    // ponytail: FBX attachment names need the full FBX loader — skipped in batch scans.
    return {};
}

VeReport ve_scan_image(const QString& path) {
    VeReport report{path, {}};
    if (!QFileInfo(path).isFile()) {
        report.findings << finding(30, "error", path, QStringLiteral("file does not exist"));
        return report;
    }
    static const QRegularExpression ansi(QStringLiteral("^[\\x20-\\x7E]+$"));
    if (!ansi.match(QFileInfo(path).fileName()).hasMatch()) report.findings << finding(66, "error", path, QStringLiteral("filename contains non-ANSI characters"));
    const QSize size = image_size(path);
    const int w = size.width(), h = size.height();
    if (w <= 0 || h <= 0) {
        report.findings << finding(36, "error", path, QStringLiteral("could not read image size"));
        return report;
    }
    if (!power_of_two(w) || !power_of_two(h))
        report.findings << finding(37, "error", path, QStringLiteral("size %1x%2 is not power-of-2 (→ %3x%4)").arg(w).arg(h).arg(pot_down(w)).arg(pot_down(h)), true, "pot");
    if (re("(cube|cubemap|skybox)").match(stem(path)).hasMatch() && w != h)
        report.findings << finding(38, "error", path, QStringLiteral("cubemap texture is not square (%1x%2)").arg(w).arg(h));
    if (w > k_max_tex_dim || h > k_max_tex_dim)
        report.findings << finding(167, "error", path, QStringLiteral("source image too large (%1x%2 > %3)").arg(w).arg(h).arg(k_max_tex_dim), true, "pot");
    QImageReader reader(path);
    const QImage image = reader.read();
    if (image.isNull()) {
        report.findings << finding(36, "error", path, QStringLiteral("texture failed to load: ") + reader.errorString());
        return report;
    }
    QColor color;
    if (uniform_color(image, &color)) report.findings << finding(39, "error", path, QStringLiteral("uniform / solid color ") + hex_of(color), true, "ve39");
    return report;
}

VeReport ve_scan_texture_txt(const QString& path) {
    VeReport report{path, {}};
    const QString text = read_text(path);
    const auto keys = parse_texture_txt(text.toStdString());
    const QString primary = texture_key(keys, "Primary"), alpha = texture_key(keys, "Alpha");
    const QString primary_path = primary.isEmpty() ? QString() : sibling(path, primary);
    const bool primary_found = !primary.isEmpty() && QFileInfo(primary_path).isFile();
    const QSize psize = primary_found ? image_size(primary_path) : QSize();
    const TextureReport tex = check_texture_txt(path.toStdString(), text.toStdString(), psize.width(), psize.height(), primary_found);
    for (const TexIssue& issue : tex.issues) {
        const QString msg = QString::fromStdString(issue.message);
        const QString low = msg.toLower();
        const QByteArray level = QByteArray::fromStdString(issue.level);
        if (low.contains(QLatin1String("missing primary"))) report.findings << finding(67, "error", path, msg, true, "texture_txt");
        else if (low.contains(QLatin1String("primary image missing"))) report.findings << finding(30, "error", path, msg);
        else if (low.contains(QLatin1String("not power-of-two"))) report.findings << finding(37, "error", primary_path, msg, true, "pot");
        else report.findings << finding(65, level == "error" ? "error" : "warn", path, msg);
    }
    if (primary_found && (psize.width() > k_max_tex_dim || psize.height() > k_max_tex_dim))
        report.findings << finding(167, "error", primary_path, QStringLiteral("Primary exceeds 4096 (%1x%2)").arg(psize.width()).arg(psize.height()), true, "pot");
    if (!alpha.isEmpty()) {
        const QString alpha_path = sibling(path, alpha);
        if (!QFileInfo(alpha_path).isFile()) {
            report.findings << finding(30, "error", path, QStringLiteral("Alpha image missing: ") + alpha);
        } else if (primary_found) {
            const QSize asize = image_size(alpha_path);
            if (asize != psize)
                report.findings << finding(68, "error", path, QStringLiteral("Alpha size %1x%2 != Primary %3x%4").arg(asize.width()).arg(asize.height()).arg(psize.width()).arg(psize.height()), true, "alpha_size");
        }
    }
    return report;
}

QList<VeReport> ve_scan_texture_folder(const QString& folder) {
    QList<VeReport> reports;
    const QDir dir(folder);
    if (!dir.exists()) return reports;
    QSet<QString> covered;
    QStringList images;
    for (const QFileInfo& info : dir.entryInfoList(QDir::Files, QDir::Name | QDir::IgnoreCase)) {
        const QString path = info.filePath();
        if (is_image(path)) {
            images << path;
            continue;
        }
        if (!is_texture_txt(path)) continue;
        reports << ve_scan_texture_txt(path);
        const QString primary = texture_key(parse_texture_txt(read_text(path).toStdString()), "Primary");
        if (!primary.isEmpty()) covered.insert(stem(primary).toLower());
        QString base = info.fileName().toLower();
        base.chop(base.endsWith(QLatin1String(".texture.txt")) ? 12 : 8);
        covered.insert(base);
    }
    for (const QString& image : images) {
        VeReport r = ve_scan_image(image);
        if (!QFileInfo::exists(sibling(image, stem(image) + QStringLiteral(".texture.txt"))) && !covered.contains(stem(image).toLower()))
            r.findings << finding(65, "error", image, missing_texture_note(image), true, "texture_txt");
        reports << r;
    }
    return reports;
}

VeReport ve_scan_mesh(const QString& path) {
    VeReport report{path, {}};
    if (!QFileInfo(path).isFile()) {
        report.findings << finding(72, "error", path, QStringLiteral("unable to load mesh — file missing"));
        return report;
    }
    const QString suf = suffix_of(path);
    if (suf == QLatin1String(".pm")) report.findings << finding(86, "error", path, QStringLiteral("legacy .pm no longer supported — switch to .lm"));
    const QByteArray bytes = read_bytes(path);
    for (const std::string& name : list_material_names(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()))) {
        const MatNameIssue issue = check_mat_name(name);
        if (issue.needs_fix())
            report.findings << finding(173, "error", path, QStringLiteral("material '%1': %2").arg(QString::fromStdString(issue.name), QString::fromStdString(issue.detail)), true, "mat_name");
    }
    QString error;
    const QStringList names = ve_attachment_names(path, &error);
    if (!error.isEmpty() && suf == QLatin1String(".im")) report.findings << finding(72, "error", path, QStringLiteral("unable to read attachments: ") + error);
    for (const QString& n : names)
        if (n.trimmed().isEmpty()) report.findings << finding(285, "error", path, QStringLiteral("empty attachment name in mesh"));
    if (suf == QLatin1String(".trainzmesh")) {
        const int faces = face_count(path);
        if (faces >= k_high_poly_faces && !QFileInfo::exists(sibling(path, stem(path) + QStringLiteral(".lm.txt"))))
            report.findings << finding(81, "warn", path, QStringLiteral("high-poly mesh (%1 faces) should have LOD (.lm.txt)").arg(faces));
    }
    if (suf == QLatin1String(".fbx") && bytes.startsWith("Kaydara FBX Binary") && bytes.size() >= 27) {
        const quint32 ver = qFromLittleEndian<quint32>(bytes.constData() + 23);
        if (ver && ver < 7100) report.findings << finding(183, "warn", path, QStringLiteral("FBX binary version %1 may be unsupported older format").arg(ver));
    }
    return report;
}

VeReport ve_scan_lm_txt(const QString& path) {
    VeReport report{path, {}};
    if (!QFileInfo(path).isFile()) {
        report.findings << finding(158, "error", path, QStringLiteral("unable to open .lm.txt"));
        return report;
    }
    LmFile lm;
    try {
        lm = parse_lm_txt(read_text(path).toStdString());
    } catch (const std::exception& e) {
        report.findings << finding(159, "error", path, QStringLiteral("unable to parse .lm.txt: ") + QString::fromUtf8(e.what()));
        return report;
    }
    if (lm.meshes.empty()) {
        report.findings << finding(160, "error", path, QStringLiteral("no mesh keys found in .lm.txt"));
        return report;
    }
    if (lm.meshes.size() < 2) report.findings << finding(84, "warn", path, QStringLiteral("LM has only a single mesh — may hurt performance"));
    report.findings << finding(161, "info", path, QStringLiteral("%1 LOD(s) in .lm.txt").arg(lm.meshes.size()));
    std::vector<LmMesh> sorted = lm.meshes;
    std::stable_sort(sorted.begin(), sorted.end(), [](const LmMesh& a, const LmMesh& b) { return a.width < b.width; });
    QStringList widths;
    bool unique = true;
    for (size_t i = 0; i < lm.meshes.size(); ++i) {
        widths << QString::number(lm.meshes[i].width);
        if (i > 0 && lm.meshes[i].width <= lm.meshes[i - 1].width) unique = false;
    }
    if (!unique) report.findings << finding(215, "error", path, QStringLiteral("invalid LOD widths (need unique ascending): [%1]").arg(widths.join(QStringLiteral(", "))));
    QList<QSet<QString>> att_sets;
    for (const LmMesh& mesh : sorted) {
        QString mesh_path = sibling(path, QString::fromStdString(mesh.name));
        if (!QFileInfo(mesh_path).isFile()) mesh_path = sibling(path, QFileInfo(QString::fromStdString(mesh.name)).fileName());
        if (!QFileInfo(mesh_path).isFile()) {
            report.findings << finding(30, "error", path, QStringLiteral("LOD mesh missing: ") + QString::fromStdString(mesh.name));
            continue;
        }
        const QStringList names = ve_attachment_names(mesh_path);
        att_sets << QSet<QString>(names.begin(), names.end());
    }
    for (int i = 1; i < att_sets.size(); ++i) {
        QStringList extra = (att_sets[i] - att_sets[0]).values();
        extra.sort();
        for (const QString& a : extra) report.findings << finding(162, "error", path, QStringLiteral("LOD[%1] introduces new attachment: %2").arg(i).arg(a));
    }
    return report;
}

VeReport ve_scan_config(const QString& path) {
    VeReport report{path, {}};
    if (!QFileInfo(path).isFile()) {
        report.findings << finding(101, "error", path, QStringLiteral("config file does not exist"));
        return report;
    }
    const QString text = read_text(path);
    if (config_kind(text).isEmpty()) report.findings << finding(49, "error", path, QStringLiteral("required tag 'kind' is not present"));
    const auto build = re(R"x(^\s*trainz-build\s+([0-9.]+))x").match(text);
    if (!build.hasMatch()) {
        report.findings << finding(88, "warn", path, QStringLiteral("trainz-build tag missing"));
    } else {
        bool ok = false;
        const double value = build.captured(1).toDouble(&ok);
        if (!ok) report.findings << finding(88, "warn", path, QStringLiteral("unrecognised trainz-build value"));
        else if (value < 3.5) report.findings << finding(48, "error", path, QStringLiteral("obsolete trainz-build %1 (raise to 4.x+)").arg(build.captured(1)));
    }
    static const QStringList uniques = {QStringLiteral("kind"), QStringLiteral("kuid"), QStringLiteral("username"), QStringLiteral("trainz-build"), QStringLiteral("mesh-table"), QStringLiteral("bogeys")};
    const QStringList tops = top_level_tags(text);
    for (const QString& tag : uniques)
        if (tops.count(tag) > 1) report.findings << finding(93, "error", path, QStringLiteral("duplicate '%1' tags/containers").arg(tag));
    for (const QString& tag : k_obsolete_tags)
        if (QRegularExpression(QStringLiteral("^\\s*%1\\b").arg(QRegularExpression::escape(tag)), QRegularExpression::CaseInsensitiveOption | QRegularExpression::MultilineOption).match(text).hasMatch())
            report.findings << finding(44, "error", path, QStringLiteral("tag '%1' is obsolete — remove or migrate").arg(tag));
    const auto [meshes, atts] = config_meshes_atts(text);
    QStringList sorted = meshes.values();
    sorted.sort();
    for (const QString& m : sorted)
        if (!QFileInfo(sibling(path, QFileInfo(m).fileName())).isFile() && !QFileInfo(sibling(path, m)).isFile())
            report.findings << finding(30, "error", path, QStringLiteral("mesh-table refers to nonexistent file: ") + m);
    for (const QString& a : atts)
        if (a.trimmed().isEmpty()) report.findings << finding(18, "error", path, QStringLiteral("empty attachment reference in config"));
    return report;
}

QList<VeReport> ve_scan_mesh_folder(const QString& folder) {
    QList<VeReport> reports;
    const QDir dir(folder);
    if (!dir.exists()) return reports;
    QStringList meshes;
    QSet<QString> referenced;
    for (const QFileInfo& info : dir.entryInfoList(QDir::Files, QDir::Name | QDir::IgnoreCase)) {
        const QString path = info.filePath();
        if (is_mesh(path)) meshes << path;
        if (!is_lm(path)) continue;
        reports << ve_scan_lm_txt(path);
        try {
            for (const LmMesh& m : parse_lm_txt(read_text(path).toStdString()).meshes) referenced.insert(QFileInfo(QString::fromStdString(m.name)).fileName().toLower());
        } catch (const std::exception&) {
        }
    }
    const QString cfg = dir.filePath(QStringLiteral("config.txt"));
    const bool has_cfg = QFileInfo(cfg).isFile();
    QSet<QString> cfg_meshes, cfg_atts;
    QString kind;
    if (has_cfg) {
        reports << ve_scan_config(cfg);
        const QString text = read_text(cfg);
        kind = config_kind(text);
        std::tie(cfg_meshes, cfg_atts) = config_meshes_atts(text);
    }
    QSet<QString> cfg_lower;
    for (const QString& m : cfg_meshes) cfg_lower.insert(QFileInfo(m).fileName().toLower());
    for (const QString& mesh : meshes) {
        VeReport r = ve_scan_mesh(mesh);
        if (!referenced.isEmpty() || !cfg_meshes.isEmpty()) {
            const QString name = QFileInfo(mesh).fileName().toLower(), st = stem(mesh).toLower();
            const QSet<QString> alts = {name, st + QStringLiteral(".im"), st + QStringLiteral(".trainzmesh")};
            const bool hit = alts.intersects(referenced) || alts.intersects(cfg_lower)
                || std::any_of(cfg_meshes.begin(), cfg_meshes.end(), [&](const QString& m) { return m.toLower().contains(st); });
            if (!hit) r.findings << finding(268, "warn", mesh, QStringLiteral("mesh file appears unused (not in .lm.txt / mesh-table)"));
        }
        reports << r;
    }
    if (meshes.isEmpty()) return reports;
    const QSet<QString> all_atts = attachment_union(meshes);
    QStringList wanted = cfg_atts.values();
    wanted.sort();
    for (const QString& att : wanted)
        if (!att.isEmpty() && !all_atts.contains(att)) reports << VeReport{cfg, {finding(15, "error", cfg, QStringLiteral("attachment '%1' not found on any mesh in folder").arg(att))}};
    if (kind == QLatin1String("traincar")) {
        const QString where = has_cfg ? cfg : meshes.first();
        for (const char* req : {"a.bog0", "a.bog1"})
            if (!all_atts.contains(QLatin1String(req))) reports << VeReport{where, {finding(201, "error", where, QStringLiteral("traincar missing required attachment: ") + QLatin1String(req))}};
        const auto bogeys = std::count_if(all_atts.begin(), all_atts.end(), [](const QString& n) { return n.startsWith(QLatin1String("a.bog")); });
        if (bogeys < 2) reports << VeReport{where, {finding(212, "error", where, QStringLiteral("traincar asset must have at least two bogeys (a.bog*)"))}};
    }
    return reports;
}

VeReport ve_scan_sound(const QString& path) {
    VeReport report{path, {}};
    if (!QFileInfo(path).isFile()) {
        report.findings << finding(102, "error", path, QStringLiteral("sound file does not exist"));
        return report;
    }
    const QString suf = suffix_of(path);
    if (suf != QLatin1String(".wav") && suf != QLatin1String(".wave")) {
        report.findings << finding(102, "warn", path, QStringLiteral("not a .wav file (%1) — Trainz soundscript expects WAV").arg(suf.isEmpty() ? QStringLiteral("no ext") : suf));
        return report;
    }
    const QByteArray head = read_bytes(path, 12);
    if (head.size() < 12 || !head.startsWith("RIFF") || head.mid(8, 4) != "WAVE") report.findings << finding(102, "error", path, QStringLiteral("not a valid RIFF/WAVE file"));
    return report;
}

QList<VeReport> ve_scan_asset_folder(const QString& folder) {
    return ve_scan_mesh_folder(folder) + ve_scan_texture_folder(folder);  // mesh pass already scans config.txt
}

QList<VeReport> ve_scan_paths(const QStringList& paths) {
    QList<VeReport> reports;
    for (const QString& path : paths) {
        const QString name = QFileInfo(path).fileName().toLower();
        const QString suf = suffix_of(path);
        if (QFileInfo(path).isDir()) reports += ve_scan_asset_folder(path);
        else if (is_texture_txt(path)) reports << ve_scan_texture_txt(path);
        else if (is_image(path)) {
            reports << ve_scan_image(path);
            if (!QFileInfo::exists(sibling(path, stem(path) + QStringLiteral(".texture.txt")))) reports.last().findings << finding(65, "error", path, missing_texture_note(path), true, "texture_txt");
        } else if (is_lm(path)) reports << ve_scan_lm_txt(path);
        else if (is_mesh(path)) reports << ve_scan_mesh(path);
        else if (name == QLatin1String("config.txt")) reports << ve_scan_config(path);
        else if (QStringList{QStringLiteral(".wav"), QStringLiteral(".wave"), QStringLiteral(".mp3"), QStringLiteral(".ogg"), QStringLiteral(".flac")}.contains(suf)) reports << ve_scan_sound(path);
        else reports << VeReport{path, {finding(0, "info", path, QStringLiteral("no VE rules for this file type"))}};
    }
    return reports;
}

QPair<bool, QString> ve_fix_finding(const VeFinding& f, bool bak) {
    const QString& path = f.path;
    if (!f.fixable || f.fix_kind.isEmpty()) return {false, QStringLiteral("not fixable")};
    if (f.fix_kind == QLatin1String("ve39")) {
        QImage image = QImageReader(path).read();
        QColor color;
        if (image.isNull()) return {false, QStringLiteral("not found")};
        if (!uniform_color(image, &color)) return {false, QStringLiteral("not uniform (skip)")};
        if (bak) backup_once(path);
        image = image.convertToFormat(QImage::Format_RGBA8888);
        const QColor noise(255 - color.red(), 255 - color.green(), 255 - color.blue());
        auto* rng = QRandomGenerator::global();
        for (int i = 0; i < 3; ++i) {
            const int cx = rng->bounded(image.width()), cy = rng->bounded(image.height()), rad = rng->bounded(1, 6) / 2;
            for (int y = std::max(0, cy - rad); y <= std::min(image.height() - 1, cy + rad); ++y)
                for (int x = std::max(0, cx - rad); x <= std::min(image.width() - 1, cx + rad); ++x)
                    if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= rad * rad) image.setPixelColor(x, y, noise);
        }
        return image.save(path) ? QPair<bool, QString>{true, QStringLiteral("fixed (dots)")} : QPair<bool, QString>{false, QStringLiteral("cannot write ") + QFileInfo(path).fileName()};
    }
    if (f.fix_kind == QLatin1String("pot")) {
        QImage image = QImageReader(path).read();
        if (image.isNull()) return {false, QStringLiteral("not found")};
        const int tw = std::min(pot_down(image.width()), k_max_tex_dim), th = std::min(pot_down(image.height()), k_max_tex_dim);
        if (tw == image.width() && th == image.height()) return {true, QStringLiteral("already %1x%2").arg(tw).arg(th)};
        if (bak) backup_once(path);
        const bool ok = image.scaled(tw, th, Qt::IgnoreAspectRatio, Qt::SmoothTransformation).save(path);
        return {ok, ok ? QStringLiteral("PoT → %1x%2").arg(tw).arg(th) : QStringLiteral("cannot write ") + QFileInfo(path).fileName()};
    }
    if (f.fix_kind == QLatin1String("texture_txt")) {
        if (is_image(path)) {
            const QString out = sibling(path, stem(path) + QStringLiteral(".texture.txt"));
            if (!write_texture_txt(out, keys_for_image(QFileInfo(path).fileName().toStdString(), "", "", ""))) return {false, QStringLiteral("cannot write ") + QFileInfo(out).fileName()};
            return {true, QStringLiteral("wrote ") + QFileInfo(out).fileName()};
        }
        if (!path.toLower().endsWith(QLatin1String(".texture.txt"))) return {false, QStringLiteral("no image/texture.txt")};
        auto keys = parse_texture_txt(read_text(path).toStdString());
        if (texture_key(keys, "Primary").isEmpty()) {
            QString base = QFileInfo(path).fileName();
            base.chop(12);
            QString primary = base + QStringLiteral(".tga");
            for (const char* ext : {".tga", ".png", ".bmp", ".jpg", ".jpeg", ".dds"})
                if (QFileInfo(sibling(path, base + QLatin1String(ext))).isFile()) {
                    primary = base + QLatin1String(ext);
                    break;
                }
            keys = keys_for_image(primary.toStdString(), "", "", "");
        }
        if (!write_texture_txt(path, keys)) return {false, QStringLiteral("cannot write ") + QFileInfo(path).fileName()};
        return {true, QStringLiteral("updated ") + QFileInfo(path).fileName()};
    }
    if (f.fix_kind == QLatin1String("alpha_size")) {
        const auto keys = parse_texture_txt(read_text(path).toStdString());
        const QString prim = texture_key(keys, "Primary"), alpha = texture_key(keys, "Alpha");
        if (prim.isEmpty() || alpha.isEmpty()) return {false, QStringLiteral("missing Primary/Alpha")};
        const QSize psize = image_size(sibling(path, prim));
        const QString alpha_path = sibling(path, alpha);
        const QImage image = QImageReader(alpha_path).read();
        if (!psize.isValid() || image.isNull()) return {false, QStringLiteral("Primary/Alpha file missing")};
        if (bak) backup_once(alpha_path);
        const bool ok = image.scaled(psize, Qt::IgnoreAspectRatio, Qt::SmoothTransformation).save(alpha_path);
        return {ok, QStringLiteral("Alpha → %1x%2").arg(psize.width()).arg(psize.height())};
    }
    if (f.fix_kind == QLatin1String("mat_name")) {
        QByteArray bytes = read_bytes(path);
        int renamed = 0;
        for (const std::string& name : list_material_names(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()))) {
            const MatNameIssue issue = check_mat_name(name);
            if (!issue.needs_fix()) continue;
            const QByteArray from = QByteArray::fromStdString(issue.name), to = QByteArray::fromStdString(issue.suggested);
            // Binary meshes keep offsets: only same-length renames are safe there.
            if ((from.size() != to.size() && bytes.contains('\0')) || !bytes.contains(from)) continue;
            bytes.replace(from, to);
            ++renamed;
        }
        if (renamed == 0) return {false, QStringLiteral("no safe renames (binary length change)")};
        if (bak) backup_once(path);
        QFile file(path);
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return {false, QStringLiteral("cannot write ") + QFileInfo(path).fileName()};
        file.write(bytes);
        return {true, QStringLiteral("%1 material rename(s)").arg(renamed)};
    }
    return {false, QStringLiteral("unknown fix ") + f.fix_kind};
}

QList<VeFix> ve_fix_reports(const QList<VeReport>& reports, bool bak) {
    QSet<QString> seen;
    QList<VeFix> out;
    for (const VeReport& r : reports)
        for (const VeFinding& f : r.findings) {
            if (!f.fixable) continue;
            const QString key = QFileInfo(f.path).absoluteFilePath() + QLatin1Char('|') + f.fix_kind;
            if (seen.contains(key)) continue;
            seen.insert(key);
            const auto [ok, msg] = ve_fix_finding(f, bak);
            out << VeFix{f, ok, msg};
        }
    return out;
}

VeSummary ve_summarize(const QList<VeReport>& reports) {
    VeSummary s;
    for (const VeReport& r : reports) {
        bool hit = false;
        for (const VeFinding& f : r.findings) {
            hit = hit || f.level != QLatin1String("info");
            s.fixable += f.fixable ? 1 : 0;
        }
        s.hits += hit ? 1 : 0;
        s.errors += r.error_count();
        s.warns += r.warn_count();
        for (int c : r.codes())
            if (!s.codes.contains(c)) s.codes << c;
    }
    std::sort(s.codes.begin(), s.codes.end());
    QStringList parts;
    for (int i = 0; i < std::min<qsizetype>(6, s.codes.size()); ++i) parts << QStringLiteral("VE%1").arg(s.codes[i]);
    QString codes = parts.join(QStringLiteral("·"));
    if (s.codes.size() > 6) codes += QStringLiteral("+%1").arg(s.codes.size() - 6);
    if (s.errors || s.warns) s.line = QStringLiteral("%1 report(s) · %2e/%3w").arg(s.hits).arg(s.errors).arg(s.warns) + (codes.isEmpty() ? QString() : QStringLiteral(" · ") + codes);
    else s.line = QStringLiteral("OK — no VE hits");
    return s;
}

QString ve_format_report(const VeReport& report) {
    QString out = QStringLiteral("%1  [%2]").arg(QFileInfo(report.path).fileName(), report.status());
    if (report.findings.isEmpty()) return out + QStringLiteral("\n  OK");
    for (const VeFinding& f : report.findings)
        out += QStringLiteral("\n%1 %2: %3 — %4%5").arg(f.code ? QStringLiteral("VE%1").arg(f.code) : QStringLiteral("MAT"), f.level, QFileInfo(f.path).fileName(), f.message, f.fixable ? QStringLiteral(" [fixable]") : QString());
    return out;
}

QString ve_format_reports(const QList<VeReport>& reports) {
    QStringList blocks;
    for (const VeReport& r : reports) blocks << ve_format_report(r);
    return blocks.join(QStringLiteral("\n\n"));
}
