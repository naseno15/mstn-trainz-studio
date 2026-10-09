#pragma once

#include <functional>

#include <QList>
#include <QString>
#include <QStringList>

// Preview Asset: walk what an asset really uses (mesh-table, interior, bogeys, ...) and list the
// meshes Trainz would auto-create, each with the yaw its mesh-table entry asks for.

struct SceneMesh {
    QString label;  // mesh-table entry name
    QString path;   // absolute .trainzmesh / .im
    double yaw = 0;  // radians about Z (mesh-table `orientation` z)
};

struct PreviewNode {
    QString kuid;
    QString name;
    QString parent;
    int depth = 0;
    bool missing = false;
    int unresolved = 0;  // mesh-table entries whose mesh file could not be found
    QList<SceneMesh> scene;
};

struct MeshEntry {
    QString name;
    QString asset;  // mesh-asset kuid; empty means the asset itself
    QString mesh;   // as written, e.g. body/body.lm
    bool auto_create = false;
    int lod = 0;
    double yaw = 0;
};

QList<MeshEntry> parse_mesh_table(const QString& config_text);
// kuids outside kuid-table / soundscript / queues / script-include-table / extensions, in order.
QStringList preview_dependencies(const QString& config_text, const QString& skip);

using ConfigReader = std::function<QString(const QString& kuid)>;   // config text; empty = not installed
using FolderLocator = std::function<QString(const QString& kuid)>;  // unpacked folder; only asked for mesh owners

using PreviewProgress = std::function<void(const QString& stage, int pct)>;

// Breadth-first, each asset once. Stops at max_depth / max_nodes. `progress` runs on the calling thread
// before each config read and each unpack; pct is an estimate (the tree grows as it is walked).
QList<PreviewNode> resolve_preview(const QString& root_kuid, const ConfigReader& read_config, const FolderLocator& locate, int max_depth = 8, int max_nodes = 400, const PreviewProgress& progress = {});

struct ContentIndex;
// Installed library: editing folder first, else the archive. Falls back to the highest installed version
// when the exact kuid is absent.
struct IndexSource {
    ConfigReader read_config;
    FolderLocator locate;
};
IndexSource index_source(const ContentIndex& index);

struct PreviewScene {
    QStringList paths;
    QStringList labels;
    QList<double> yaws;
};
PreviewScene preview_scene(const QList<PreviewNode>& nodes, int cap = 400);

QString preview_text(const QList<PreviewNode>& nodes);
