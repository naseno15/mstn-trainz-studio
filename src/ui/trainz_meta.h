#pragma once

#include <functional>

#include <QHash>
#include <QPair>
#include <QString>
#include <QStringList>
#include <QVariantList>

// Pure helpers behind the TrainzUtil library. Ported from trainz_studio/io/trainz_install.py.

QString category_label(const QString& code);
bool category_is_enginespec(const QString& code);
QStringList status_bits(const QString& flags, bool open_for_edit, bool locally_modified);
int status_rank(const QStringList& bits);
QString decode_status(const QString& raw);
QString tidy_trainzutil(const QString& text);
QString config_credits(const QString& text);
QPair<bool, QString> task_outcome(const QString& raw);
QPair<QString, QString> classify_trainz_line(const QString& line);
QVariantList classify_trainz_log(const QString& text);
QStringList dependency_kuids(const QString& text, const QString& skip);
QString kuid_from_archive_name(const QString& name);
qint64 kuid_user_id(const QString& kuid);
QHash<qint64, QString> parse_kuid_owners(const QByteArray& tdx);
QHash<qint64, QString> read_kuid_owners(const QString& tdx_path);
QString format_bytes(qint64 size);
QString fmt_mtime(qint64 unix_secs);
QString cdp_stem(const QString& name, const QString& kuid);

struct ArchiveHit {
    QString path;
    qint64 mtime_ns = 0;
    qint64 size = 0;
};

struct ContentIndex {
    QHash<QString, ArchiveHit> original;
    QHash<QString, ArchiveHit> local;
    QHash<QString, qint64> editing_mtime;
    QHash<QString, QString> editing_folder;
    QHash<QString, ArchiveHit> chosen() const;
};

QStringList content_roots(const QString& data_dir);
ContentIndex index_content(const QStringList& roots);

struct AssetMeta {
    QString author;
    QString build;
    QString username;
};

// Author, trainz-build, and username from each archive config. Cached by mtime in
// ~/.cache/trainz_studio/tu-archive-meta.json, the same file the Python app uses.
QHash<QString, AssetMeta> scan_archive_meta(
    const ContentIndex& index, const QString& cache_file, const std::function<void(const QString&)>& status);
QString meta_cache_file();

QString asset_cover_path(const ContentIndex& index, const QString& kuid);
// preview_only unpacks just meshes and texture images (into a separate cache) - far less to inflate and write.
QString asset_browse_dir(const ContentIndex& index, const QString& kuid, bool preview_only = false);
QString config_in_editing(const QString& editing, const QString& kuid);

struct AssetBackup {
    QString day;
    QString day_key;
    QString name;
    QString kind;
    QString path;
    qint64 size = 0;
    qint64 mtime = 0;
    QString kuid;
    QString when;
};

QList<AssetBackup> find_asset_backups(const QString& data_dir, const QString& query, int limit = 2000);
QHash<QString, QString> describe_backup(const QString& path);

QStringList collect_script_files(const QStringList& paths);
QHash<QString, QString> encrypt_error_map(const QString& text);
