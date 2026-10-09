#include "ui/asset_preview.h"

#include <memory>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QRegularExpression>
#include <QSet>

#include "io/chump.h"
#include "io/tzarc.h"
#include "ui/trainz_meta.h"

namespace {

QStringList tokens_of(const QString& text) {
    QStringList out;
    for (QString line : text.split(QLatin1Char('\n'))) {
        const int slash = line.indexOf(QLatin1String("//"));
        if (slash >= 0) line.truncate(slash);
        if (line.trimmed().startsWith(QLatin1Char('#'))) continue;
        for (int i = 0; i < line.size();) {
            const QChar c = line[i];
            if (c.isSpace()) {
                ++i;
                continue;
            }
            if (c == QLatin1Char('{') || c == QLatin1Char('}')) {
                out << QString(c);
                ++i;
                continue;
            }
            if (c == QLatin1Char('"')) {
                const int end = line.indexOf(QLatin1Char('"'), i + 1);
                out << line.mid(i + 1, (end < 0 ? line.size() : end) - i - 1);
                i = end < 0 ? line.size() : end + 1;
                continue;
            }
            int end = i;
            while (end < line.size() && !line[end].isSpace() && line[end] != QLatin1Char('{') && line[end] != QLatin1Char('}')) ++end;
            out << line.mid(i, end - i);
            i = end;
        }
    }
    return out;
}

bool is_open(const QStringList& tok, int i) { return i < tok.size() && tok[i] == QLatin1String("{"); }

// Config as text from a config.txt or config.chump body.
QString text_of_config(const QByteArray& bytes) {
    if (bytes.isEmpty()) return {};
    try {
        return QString::fromStdString(chump_to_text(read_chump(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()))));
    } catch (const std::exception&) {
        return QString::fromUtf8(bytes);
    }
}

QString username_of(const QString& text) {
    static const QRegularExpression re(QStringLiteral(R"(^\s*username\s+"?([^"\r\n]*))"), QRegularExpression::MultilineOption | QRegularExpression::CaseInsensitiveOption);
    return re.match(text).captured(1).trimmed();
}

// <kuid2:a:b:v> / <kuid:a:b> -> "a:b" and version.
bool split_kuid(const QString& kuid, QString& base, int& version) {
    static const QRegularExpression re(QStringLiteral(R"(^<kuid2?:(-?\d+):(-?\d+)(?::(-?\d+))?>$)"));
    const QRegularExpressionMatch m = re.match(kuid);
    if (!m.hasMatch()) return false;
    base = m.captured(1) + QLatin1Char(':') + m.captured(2);
    version = m.captured(3).isEmpty() ? 0 : m.captured(3).toInt();
    return true;
}

// Compiled mesh for a mesh-table `mesh` name (body/body.lm -> body/body.trainzmesh, else .im).
QString mesh_file(const QString& folder, const QString& mesh) {
    const QFileInfo info(mesh);
    const QString stem = QDir(folder).absoluteFilePath(info.path() + QLatin1Char('/') + info.completeBaseName());
    for (const char* ext : {".trainzmesh", ".im"})
        if (QFileInfo::exists(stem + QLatin1String(ext))) return stem + QLatin1String(ext);
    return {};
}

}  // namespace

QList<MeshEntry> parse_mesh_table(const QString& text) {
    const QStringList tok = tokens_of(text);
    int i = 0;
    while (i + 1 < tok.size() && !(tok[i].compare(QLatin1String("mesh-table"), Qt::CaseInsensitive) == 0 && is_open(tok, i + 1))) ++i;
    QList<MeshEntry> out;
    if (i + 1 >= tok.size()) return out;
    i += 2;
    while (i < tok.size() && tok[i] != QLatin1String("}")) {
        if (!is_open(tok, i + 1)) {
            ++i;
            continue;
        }
        MeshEntry entry;
        entry.name = tok[i];
        entry.auto_create = entry.name.compare(QLatin1String("default"), Qt::CaseInsensitive) == 0;
        i += 2;
        for (int depth = 1; i < tok.size() && depth > 0; ++i) {
            if (tok[i] == QLatin1String("{")) ++depth;
            else if (tok[i] == QLatin1String("}")) --depth;
            else if (depth == 1 && i + 1 < tok.size()) {
                const QString& key = tok[i];
                const QString& value = tok[i + 1];
                if (key.compare(QLatin1String("mesh"), Qt::CaseInsensitive) == 0) entry.mesh = value;
                else if (key.compare(QLatin1String("mesh-asset"), Qt::CaseInsensitive) == 0) entry.asset = value;
                else if (key.compare(QLatin1String("auto-create"), Qt::CaseInsensitive) == 0) entry.auto_create = value.toInt() != 0;
                else if (key.compare(QLatin1String("lod-level"), Qt::CaseInsensitive) == 0) entry.lod = value.toInt();
                else if (key.compare(QLatin1String("orientation"), Qt::CaseInsensitive) == 0) entry.yaw = value.section(QLatin1Char(','), 2, 2).toDouble();
            }
        }
        if (!entry.mesh.isEmpty()) out << entry;
    }
    return out;
}

QStringList preview_dependencies(const QString& text, const QString& skip) {
    static const QSet<QString> noise = {QStringLiteral("kuid-table"), QStringLiteral("soundscript"), QStringLiteral("queues"), QStringLiteral("script-include-table"), QStringLiteral("extensions")};
    static const QRegularExpression kuid(QStringLiteral(R"(^<kuid2?:-?\d+:-?\d+(?::-?\d+)?>$)"));
    const QStringList tok = tokens_of(text);
    QStringList out;
    int depth = 0;
    bool skipping = false;
    for (int i = 0; i < tok.size(); ++i) {
        if (tok[i] == QLatin1String("{")) {
            if (depth == 0 && i > 0) skipping = noise.contains(tok[i - 1].toLower());
            ++depth;
        } else if (tok[i] == QLatin1String("}")) {
            if (--depth <= 0) {
                depth = 0;
                skipping = false;
            }
        } else if (!skipping && kuid.match(tok[i]).hasMatch() && tok[i] != skip && !out.contains(tok[i])) {
            out << tok[i];
        }
    }
    return out;
}

QList<PreviewNode> resolve_preview(const QString& root_kuid, const ConfigReader& read_config, const FolderLocator& locate, int max_depth, int max_nodes, const PreviewProgress& progress) {
    QList<PreviewNode> out;
    QSet<QString> seen{root_kuid};
    QHash<QString, QString> folders;  // locate() unpacks, so ask once per asset
    QList<PreviewNode> queue;
    int head = 0;
    auto say = [&](const QString& stage) {
        if (progress) progress(stage, 100 * head / qMax<int>(queue.size(), 1));
    };
    auto folder_of = [&](const QString& kuid) {
        if (!folders.contains(kuid)) {
            say(QStringLiteral("Unpacking %1 (asset %2 of %3)").arg(kuid).arg(head + 1).arg(queue.size()));
            folders.insert(kuid, locate(kuid));
        }
        return folders.value(kuid);
    };
    PreviewNode root;
    root.kuid = root_kuid;
    queue << root;
    for (; head < queue.size() && out.size() < max_nodes; ++head) {
        PreviewNode node = queue[head];
        say(QStringLiteral("Reading config %1 of %2: %3").arg(head + 1).arg(queue.size()).arg(node.kuid));
        const QString text = read_config(node.kuid);
        node.missing = text.isEmpty();
        node.name = username_of(text);
        // ponytail: no mesh-table means no scene meshes; old-style `mesh` tags are not read.
        for (const MeshEntry& entry : parse_mesh_table(text)) {
            if (!entry.auto_create || entry.lod != 0) continue;
            const QString folder = folder_of(entry.asset.isEmpty() ? node.kuid : entry.asset);
            const QString path = folder.isEmpty() ? QString() : mesh_file(folder, entry.mesh);
            if (path.isEmpty()) ++node.unresolved;
            else node.scene.append({entry.name, path, entry.yaw});
        }
        out << node;
        if (node.depth >= max_depth) continue;
        for (const QString& dep : preview_dependencies(text, node.kuid)) {
            if (seen.contains(dep)) continue;
            seen.insert(dep);
            PreviewNode child;
            child.kuid = dep;
            child.parent = node.kuid;
            child.depth = node.depth + 1;
            queue << child;
        }
    }
    return out;
}

IndexSource index_source(const ContentIndex& index) {
    auto shared = std::make_shared<ContentIndex>(index);
    QSet<QString> have;
    for (const QString& k : index.editing_folder.keys()) have.insert(k);
    for (const QString& k : index.chosen().keys()) have.insert(k);
    auto key_of = [shared, have](const QString& wanted) -> QString {
        if (have.contains(wanted)) return wanted;
        QString base;
        int version = 0;
        if (!split_kuid(wanted, base, version)) return {};
        QString best_key;
        int best = -1;
        for (const QString& cand : have) {
            QString cb;
            int cv = 0;
            if (split_kuid(cand, cb, cv) && cb == base && cv > best) {
                best = cv;
                best_key = cand;
            }
        }
        return best_key;
    };
    IndexSource source;
    source.read_config = [shared, key_of](const QString& wanted) -> QString {
        const QString key = key_of(wanted);
        if (key.isEmpty()) return {};
        const QString folder = shared->editing_folder.value(key);
        if (!folder.isEmpty() && QFileInfo(folder).isDir()) {
            QFile txt(folder + QStringLiteral("/config.txt"));
            return txt.open(QIODevice::ReadOnly) ? QString::fromUtf8(txt.readAll()) : QString();
        }
        const QString archive = shared->chosen().value(key).path;
        QFile file(archive);
        if (archive.isEmpty() || !file.open(QIODevice::ReadOnly)) return {};
        // Mapped, and the reader inflates only the chunks holding the config: a 500 MB archive costs ~1 MB of work.
        const uchar* mapped = file.map(0, file.size());
        QByteArray fallback;
        if (!mapped) {
            fallback = file.readAll();
            mapped = reinterpret_cast<const uchar*>(fallback.constData());
        }
        try {
            const std::vector<uint8_t> config = read_tzarc_config(mapped, static_cast<size_t>(file.size()));
            return text_of_config(QByteArray(reinterpret_cast<const char*>(config.data()), static_cast<qsizetype>(config.size())));
        } catch (const std::exception&) {
            return {};
        }
    };
    source.locate = [shared, key_of](const QString& wanted) -> QString {
        const QString key = key_of(wanted);
        return key.isEmpty() ? QString() : asset_browse_dir(*shared, key, true);
    };
    return source;
}

PreviewScene preview_scene(const QList<PreviewNode>& nodes, int cap) {
    PreviewScene out;
    for (const PreviewNode& n : nodes)
        for (const SceneMesh& m : n.scene) {
            if (out.paths.size() >= cap) return out;
            out.paths << m.path;
            out.labels << m.label;
            out.yaws << m.yaw;
        }
    return out;
}

QString preview_text(const QList<PreviewNode>& nodes) {
    QStringList lines;
    int missing = 0;
    int meshes = 0;
    for (const PreviewNode& n : nodes) {
        const QString pad(n.depth * 2, QLatin1Char(' '));
        QString line = pad + (n.depth ? QStringLiteral("+ ") : QString()) + (n.name.isEmpty() ? n.kuid : n.name + QStringLiteral("  ") + n.kuid);
        if (n.missing) {
            line += QStringLiteral("  [MISSING]");
            ++missing;
        } else if (!n.scene.isEmpty() || n.unresolved) {
            line += QStringLiteral("  meshes %1").arg(n.scene.size());
            if (n.unresolved) line += QStringLiteral(", %1 not found").arg(n.unresolved);
            meshes += n.scene.size();
        }
        lines << line;
    }
    lines.prepend(QStringLiteral("%1 assets, %2 meshes, %3 missing").arg(nodes.size()).arg(meshes).arg(missing));
    return lines.join(QLatin1Char('\n'));
}
