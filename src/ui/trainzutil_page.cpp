#include "trainzutil_page.h"
#include "res_path.h"

#include "asset_preview.h"
#include "i18n.h"
#include "icons.h"
#include "shell_window.h"
#include "status_hub.h"

#include "io/cdp.h"
#include "io/enginespec.h"
#include "io/tzarc.h"
#include "io/zip_read.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <functional>

#include <QClipboard>
#include <QCoreApplication>
#include <QDateTime>
#include <QDeadlineTimer>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QGuiApplication>
#include <QHash>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QVBoxLayout>
#include <QPointer>
#include <QProcess>
#include <QProcessEnvironment>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QSet>
#include <QSettings>
#include <QTemporaryDir>
#include <QThread>
#include <QUrl>
#include <QUuid>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

struct TrainzScanGate {
    std::atomic<bool> alive{true};
    std::atomic<qint64> pid{0};
};

namespace {

QString qml_file() {
return res_qml_dir() + QStringLiteral("/TrainzUtilPage.qml");
}

QString glyph(const char* name) { return material_glyph(name); }

constexpr int kRoleName = Qt::UserRole + 2;
constexpr int kRolePicked = Qt::UserRole + 6;
constexpr int kRolePacked = Qt::UserRole + 7;
constexpr int kRoleCredits = Qt::UserRole + 5;
constexpr int kRoleAuthor = Qt::UserRole + 12;
constexpr int kRoleBuild = Qt::UserRole + 13;

LibraryAsset asset_from_tzarc(const QString& path) {
    QFile file(path);
    LibraryAsset asset;
    asset.name = QFileInfo(path).completeBaseName();
    if (!file.open(QIODevice::ReadOnly)) return asset;
    const QByteArray bytes = file.readAll();
    try {
        const std::vector<uint8_t> config = read_tzarc_config(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
        const LibraryRow row = library_row_from_config(config.data(), config.size());
        if (!row.name.empty()) asset.name = QString::fromUtf8(row.name.c_str());
        asset.kuid = QString::fromUtf8(row.kuid.c_str());
        asset.author = QString::fromUtf8(row.author.c_str());
        asset.build = QString::fromUtf8(row.build.c_str());
    } catch (const std::exception&) {
    }
    if (asset.kuid.isEmpty()) asset.kuid = kuid_from_archive_name(QFileInfo(path).fileName());
    if (asset.kuid.isEmpty()) asset.kuid = path;
    return asset;
}

QString label_of(const QString& author, const QString& build) {
    return QString::fromStdString(author_label(author.toStdString(), build.toStdString()));
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

void hide_console(QProcess& proc) {
#ifdef Q_OS_WIN
    proc.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments* args) {
        args->flags |= CREATE_NO_WINDOW;
    });
#else
    Q_UNUSED(proc);
#endif
}

struct RunOut {
    QString text;
    bool timeout = false;
};

RunOut run_trainzutil(const QString& exe, const QStringList& args, int timeout_ms, const std::shared_ptr<TrainzScanGate>& state) {
    RunOut out;
    if (!state->alive.load()) {
        out.timeout = true;
        return out;
    }
    QProcess proc;
    hide_console(proc);
    proc.setWorkingDirectory(QFileInfo(exe).absolutePath());
    proc.start(exe, args);
    if (!proc.waitForStarted(5000)) {
        out.timeout = true;
        return out;
    }
    state->pid.store(static_cast<qint64>(proc.processId()));
    if (!proc.waitForFinished(timeout_ms)) {
        proc.kill();
        proc.waitForFinished(2000);
        out.timeout = true;
    }
    state->pid.store(0);
    out.text = QString::fromUtf8(proc.readAllStandardOutput() + proc.readAllStandardError()).trimmed();
    return out;
}

QString run_tu(const QString& exe, const QStringList& args, int timeout_ms) {
    const RunOut out = run_trainzutil(exe, args, timeout_ms, std::make_shared<TrainzScanGate>());
    if (out.timeout && out.text.isEmpty()) return QStringLiteral("TrainzUtil timed out");
    return out.text;
}

QString stream_tu(const QString& exe, const QStringList& args, int timeout_ms, const std::function<void(const QString&)>& on_line) {
    QProcess proc;
    hide_console(proc);
    proc.setProcessChannelMode(QProcess::MergedChannels);
    proc.setWorkingDirectory(QFileInfo(exe).absolutePath());
    proc.start(exe, args);
    if (!proc.waitForStarted(5000)) return QStringLiteral("TrainzUtil did not start");
    QStringList lines;
    QDeadlineTimer deadline(timeout_ms);
    auto drain = [&] {
        while (proc.canReadLine()) {
            const QString line = QString::fromUtf8(proc.readLine()).trimmed();
            if (line.isEmpty()) continue;
            lines << line;
            on_line(line);
        }
    };
    while (proc.state() != QProcess::NotRunning) {
        if (deadline.hasExpired()) {
            proc.kill();
            proc.waitForFinished(2000);
            lines << QStringLiteral("TrainzUtil timed out");
            break;
        }
        proc.waitForReadyRead(200);
        drain();
    }
    drain();
    const QString rest = QString::fromUtf8(proc.readAll()).trimmed();
    if (!rest.isEmpty()) {
        lines << rest;
        on_line(rest);
    }
    return lines.join(QLatin1Char('\n')).trimmed();
}

bool launcher_process_running() {
#ifdef Q_OS_WIN
    QProcess proc;
    hide_console(proc);
    proc.start(QStringLiteral("tasklist"), {QStringLiteral("/FO"), QStringLiteral("CSV"), QStringLiteral("/NH")});
    if (!proc.waitForFinished(8000)) return true;
    const QString out = QString::fromUtf8(proc.readAllStandardOutput());
    bool saw = false;
    for (const QString& line : out.split(QLatin1Char('\n'))) {
        if (line.trimmed().isEmpty()) continue;
        saw = true;
        const QString name = line.section(QLatin1Char(','), 0, 0).remove(QLatin1Char('"')).trimmed().toLower();
        if (name.startsWith(QLatin1String("trainz")) || name.startsWith(QLatin1String("trs"))) return true;
    }
    return !saw;
#else
    return true;
#endif
}

bool launcher_reply_blocked(const QString& text) {
    const QString low = text.toLower();
    return low.contains(QLatin1String("not running")) || low.contains(QLatin1String("unable to connect"))
        || low.contains(QLatin1String("must be running")) || low.contains(QLatin1String("debug tools"));
}

bool blocked(const QString& text) { return text.contains(QLatin1String("not running"), Qt::CaseInsensitive); }

QString version_label(const QString& text) {
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        QString body = line.trimmed();
        const int marker = body.indexOf(QLatin1String("<NULL>"));
        if (marker >= 0) {
            const int colon = body.indexOf(QLatin1Char(':'), marker);
            if (colon >= 0) body = body.mid(colon + 1).trimmed();
        }
        if (body.isEmpty() || body.contains(QLatin1String("version"), Qt::CaseInsensitive) || body.contains(QLatin1String("null"), Qt::CaseInsensitive))
            continue;
        return body;
    }
    return QStringLiteral("Connected");
}

QString create_cdp(const QString& exe, const QString& dest, const QStringList& kuids) {
    if (kuids.isEmpty()) return QStringLiteral("Nothing selected");
    const QString batch = QDir::temp().filePath(QStringLiteral("mstn-tu-export-%1.txt").arg(QUuid::createUuid().toString(QUuid::Id128).left(8)));
    QFile file(batch);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return QStringLiteral("Could not write the export batch");
    QStringList quoted;
    for (const QString& kuid : kuids) quoted << QLatin1Char('"') + kuid + QLatin1Char('"');
    file.write((QStringLiteral("\"createCDP\" \"%1\" %2\n").arg(QDir::toNativeSeparators(dest), quoted.join(QLatin1Char(' ')))).toUtf8());
    file.close();
    const QString out = run_tu(exe, {QStringLiteral("@") + batch}, 300000);
    QFile::remove(batch);
    return out;
}

void post(std::function<void()> fn) { QMetaObject::invokeMethod(QCoreApplication::instance(), std::move(fn), Qt::QueuedConnection); }

void spawn(std::function<void()> work) {
    QThread* thread = QThread::create(std::move(work));
    QObject::connect(thread, &QThread::finished, thread, &QObject::deleteLater);
    thread->start();
}

QString new_id() { return QUuid::createUuid().toString(QUuid::Id128).left(12); }

QByteArray read_bytes(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    return file.readAll();
}

bool write_bytes(const QString& path, const QByteArray& bytes) {
    QDir().mkpath(QFileInfo(path).path());
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    return file.write(bytes) == bytes.size();
}

QByteArray to_qbytes(const std::vector<uint8_t>& raw) { return QByteArray(reinterpret_cast<const char*>(raw.data()), static_cast<qsizetype>(raw.size())); }

QByteArray zip_at(const QString& path, const QStringList& chain) {
    QByteArray blob = read_bytes(path);
    for (const QString& member : chain) {
        if (!safe_zip_name(member.toStdString())) throw std::runtime_error("unsafe zip path");
        const auto* data = reinterpret_cast<const uint8_t*>(blob.constData());
        const size_t size = static_cast<size_t>(blob.size());
        const std::vector<ZipEntry> entries = list_zip(data, size);
        const auto hit = std::find_if(entries.begin(), entries.end(), [&](const ZipEntry& e) { return QString::fromStdString(e.name) == member; });
        if (hit == entries.end()) throw std::runtime_error("zip member missing");
        blob = to_qbytes(read_zip_entry(data, size, *hit));
    }
    return blob;
}

int pulse_percent(const QString& line, int& seen) {
    static const QRegularExpression pct(QStringLiteral(R"((?<!\d)(\d{1,3})\s*%)"));
    const QString low = line.toLower();
    const QRegularExpressionMatch m = pct.match(line);
    const bool bump = low.contains(QLatin1String("<kuid")) || low.contains(QLatin1String("install")) || low.contains(QLatin1String("commit"))
        || low.contains(QLatin1String("import")) || low.contains(QLatin1String("saving"));
    if (bump) ++seen;
    if (m.hasMatch()) return std::clamp(m.captured(1).toInt(), 0, 99);
    return bump ? std::min(90, 8 + seen * 5) : -1;
}

QString stage_job(const TuJob& job, const QString& dest) {
    if (job.kind == QLatin1String("cdp")) return job.source;
    if (job.kind == QLatin1String("cdp-inner")) {
        const QByteArray bytes = read_bytes(job.source);
        const std::vector<uint8_t> body = read_cdp_file(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()), job.asset_kuid.toStdString(), job.member.toStdString());
        const QString out = dest + QLatin1Char('/') + QFileInfo(job.member).fileName();
        if (!write_bytes(out, to_qbytes(body))) throw std::runtime_error("could not stage the CDP");
        return out;
    }
    const QByteArray blob = zip_at(job.source, job.chain);
    const auto* data = reinterpret_cast<const uint8_t*>(blob.constData());
    const size_t size = static_cast<size_t>(blob.size());
    const std::vector<ZipEntry> entries = list_zip(data, size);
    if (job.kind == QLatin1String("zip-cdp")) {
        for (const ZipEntry& entry : entries) {
            if (QString::fromStdString(entry.name) != job.member) continue;
            const QString out = dest + QLatin1Char('/') + QFileInfo(job.member).fileName();
            if (!write_bytes(out, to_qbytes(read_zip_entry(data, size, entry)))) throw std::runtime_error("could not stage the CDP");
            return out;
        }
        throw std::runtime_error("zip member missing");
    }
    const QString prefix = QString(job.member).remove(QRegularExpression(QStringLiteral("^/+|/+$")));
    const QString folder = dest + QStringLiteral("/asset");
    bool wrote = false;
    for (const ZipEntry& entry : entries) {
        const QString name = QString::fromStdString(entry.name);
        if (entry.dir || !safe_zip_name(entry.name)) continue;
        QString rel;
        if (!prefix.isEmpty()) {
            if (name != prefix && !name.startsWith(prefix + QLatin1Char('/'))) continue;
            rel = name.mid(prefix.size());
            while (rel.startsWith(QLatin1Char('/'))) rel.remove(0, 1);
        } else {
            if (name.contains(QLatin1Char('/'))) continue;
            rel = name;
        }
        if (rel.isEmpty() || !safe_zip_name(rel.toStdString())) continue;
        if (!write_bytes(folder + QLatin1Char('/') + rel, to_qbytes(read_zip_entry(data, size, entry)))) throw std::runtime_error("could not stage the folder");
        wrote = true;
    }
    if (!wrote) throw std::runtime_error("archive entry was empty");
    return folder;
}

QVariantMap job_row(const TuJob& job) {
    return {
        {QStringLiteral("jobId"), job.id},
        {QStringLiteral("label"), job.label},
        {QStringLiteral("kind"), job.kind},
        {QStringLiteral("detail"), job.detail},
        {QStringLiteral("canInstall"), job.can_install},
        {QStringLiteral("checked"), job.checked && job.can_install},
        {QStringLiteral("openable"), job.kind == QLatin1String("zip-nested")},
    };
}

}  // namespace

QList<TuJob> scan_package(const QString& path, const QStringList& chain) {
    QList<TuJob> jobs;
    if (chain.isEmpty() && path.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive)) {
        const QByteArray bytes = read_bytes(path);
        const std::vector<CdpAssetEntry> assets = list_cdp_assets(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
        QList<TuJob> inner;
        for (const CdpAssetEntry& asset : assets) {
            for (const std::string& file : asset.files) {
                const QString rel = QString::fromStdString(file);
                if (!rel.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive) || !safe_zip_name(file)) continue;
                TuJob job;
                job.id = new_id();
                job.label = QFileInfo(rel).fileName();
                job.kind = QStringLiteral("cdp-inner");
                job.detail = QString::fromStdString(asset.kuid) + QStringLiteral(" · ") + rel;
                job.can_install = true;
                job.source = path;
                job.member = rel;
                job.asset_kuid = QString::fromStdString(asset.kuid);
                inner << job;
            }
        }
        TuJob whole;
        whole.id = new_id();
        whole.label = QFileInfo(path).fileName();
        whole.kind = QStringLiteral("cdp");
        whole.detail = QStringLiteral("%1 asset%2").arg(assets.size()).arg(assets.size() == 1 ? QString() : QStringLiteral("s"));
        whole.can_install = true;
        whole.source = path;
        whole.checked = inner.isEmpty();
        jobs << whole << inner;
        for (const CdpAssetEntry& asset : assets) {
            TuJob info;
            info.id = new_id();
            info.label = QString::fromStdString(asset.username.empty() ? (asset.kuid.empty() ? std::string("asset") : asset.kuid) : asset.username);
            QStringList bits;
            if (!asset.kuid.empty()) bits << QString::fromStdString(asset.kuid);
            if (!asset.kind.empty()) bits << QString::fromStdString(asset.kind);
            info.detail = bits.join(QStringLiteral(" · "));
            info.kind = QStringLiteral("info");
            info.source = path;
            jobs << info;
        }
        return jobs;
    }
    const QByteArray blob = zip_at(path, chain);
    const std::vector<ZipEntry> entries = list_zip(reinterpret_cast<const uint8_t*>(blob.constData()), static_cast<size_t>(blob.size()));
    QSet<QString> folders;
    for (const ZipEntry& entry : entries) {
        const QString name = QString::fromStdString(entry.name);
        if (entry.dir || !safe_zip_name(entry.name)) continue;
        TuJob job;
        job.id = new_id();
        job.source = path;
        job.chain = chain;
        const QString low = name.toLower();
        if (low.endsWith(QLatin1String(".cdp"))) {
            job.label = QFileInfo(name).fileName();
            job.kind = QStringLiteral("zip-cdp");
            job.detail = name;
            job.can_install = true;
            job.member = name;
        } else if (low.endsWith(QLatin1String(".zip"))) {
            job.label = QFileInfo(name).fileName();
            job.kind = QStringLiteral("zip-nested");
            job.detail = QStringLiteral("Open to see inside");
            job.member = name;
        } else if (low.endsWith(QLatin1String("config.txt"))) {
            const int slash = name.lastIndexOf(QLatin1Char('/'));
            const QString folder = slash < 0 ? QString() : name.left(slash);
            if (folders.contains(folder)) continue;
            folders.insert(folder);
            job.label = folder.isEmpty() ? QFileInfo(chain.isEmpty() ? path : chain.last()).completeBaseName() : QFileInfo(folder).fileName();
            job.kind = QStringLiteral("zip-folder");
            job.detail = folder.isEmpty() ? QStringLiteral("(zip root)") : folder;
            job.can_install = true;
            job.member = folder;
        } else {
            continue;
        }
        jobs << job;
    }
    if (jobs.size() == 1 && jobs.first().can_install) jobs.first().checked = true;
    return jobs;
}

QList<LibraryAsset> parse_installed_library(const QString& text) {
    const QRegularExpression re(QStringLiteral(
        R"([+-]\s*(<kuid2?:-?\d+:-?\d+(?::-?\d+)?>)\s*:\s*([A-Za-z]+)\s*:\s*(.*?)\s*:\s*(.*)$)"));
    QHash<QString, LibraryAsset> found;
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        const QRegularExpressionMatch match = re.match(line.trimmed());
        if (!match.hasMatch()) continue;
        const QString flags = match.captured(2);
        if (!flags.contains(QLatin1Char('I'))) continue;
        LibraryAsset asset;
        asset.kuid = match.captured(1);
        asset.flags = flags;
        asset.category = match.captured(3).trimmed();
        asset.name = match.captured(4).trimmed();
        if (asset.name.isEmpty()) asset.name = asset.kuid;
        asset.faulty = flags.contains(QLatin1Char('F'));
        found.insert(asset.kuid, asset);
    }
    QList<LibraryAsset> rows = found.values();
    std::sort(rows.begin(), rows.end(), [](const LibraryAsset& left, const LibraryAsset& right) {
        if (left.faulty != right.faulty) return left.faulty;
        return left.name.compare(right.name, Qt::CaseInsensitive) < 0;
    });
    return rows;
}

QString parse_installation_data_path(const QString& text) {
    const QRegularExpression re(
        QStringLiteral(R"(^\s*\+\s*<NULL>\s*:\s*(.+?)\s*$)"), QRegularExpression::MultilineOption);
    const QRegularExpressionMatch match = re.match(text);
    if (!match.hasMatch()) return {};
    const QString raw = match.captured(1).trimmed().remove(QLatin1Char('"'));
    if (raw.isEmpty() || raw.contains(QLatin1Char('<'))) return {};
    return raw;
}

AssetDates read_asset_dates(const ContentIndex& index) {
    AssetDates dates;
    for (auto it = index.original.begin(); it != index.original.end(); ++it) {
        dates.installed.insert(it.key(), it->mtime_ns / 1000000000LL);
        dates.sizes.insert(it.key(), it->size);
    }
    for (auto it = index.local.begin(); it != index.local.end(); ++it) {
        dates.modified.insert(it.key(), it->mtime_ns / 1000000000LL);
        dates.sizes.insert(it.key(), it->size);
    }
    dates.editing = index.editing_mtime;
    return dates;
}

QString trainzutil_under_common(const QString& common_dir) {
    const QDir common(common_dir);
    if (!common.exists()) return {};
    QStringList hits;
    const QFileInfoList children = common.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot);
    for (const QFileInfo& child : children) {
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

// Every Steam library's steamapps/common: registry Steam path + libraryfolders.vdf "path" entries.
QStringList steam_commons() {
    QStringList roots;
#ifdef Q_OS_WIN
    for (const char* key : {"HKEY_CURRENT_USER\\Software\\Valve\\Steam", "HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Valve\\Steam"}) {
        const QSettings reg(QString::fromLatin1(key), QSettings::NativeFormat);
        for (const char* name : {"SteamPath", "InstallPath"}) {
            const QString value = reg.value(QString::fromLatin1(name)).toString();
            if (!value.isEmpty()) roots << value;
        }
    }
#endif
    static const QRegularExpression path_re(QStringLiteral("\"path\"\\s+\"([^\"]+)\""));
    const QStringList base = roots;
    for (const QString& root : base) {
        QFile vdf(QDir(root).filePath(QStringLiteral("steamapps/libraryfolders.vdf")));
        if (!vdf.open(QIODevice::ReadOnly)) continue;
        const QString text = QString::fromUtf8(vdf.readAll());
        for (auto it = path_re.globalMatch(text); it.hasNext();) roots << QString(it.next().captured(1)).replace(QStringLiteral("\\\\"), QStringLiteral("/"));
    }
    QStringList out;
    for (const QString& root : roots) out << QDir(root).filePath(QStringLiteral("steamapps/common"));
    return out;
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
    for (const QString& common : steam_commons()) {
        const QString key = QDir::cleanPath(common).toLower();
        if (seen.contains(key) || !QFileInfo(common).isDir()) continue;
        seen.insert(key);
        commons << common;
    }
    for (const QString& common : commons) {
        const QString hit = trainzutil_under_common(common);
        if (!hit.isEmpty()) return hit;
    }
    return {};
}

// ---------------------------------------------------------------- LibraryList

LibraryList::LibraryList(QObject* parent) : QAbstractListModel(parent) {}

int LibraryList::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : shown_.size(); }

QVariant LibraryList::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= shown_.size()) return {};
    const LibraryAsset& asset = all_[shown_[index.row()]];
    switch (role) {
    case Qt::UserRole + 1: return asset.kuid;
    case Qt::UserRole + 2: return asset.name;
    case Qt::UserRole + 3: return asset.faulty;
    case Qt::UserRole + 4: {
        const QString label = category_label(asset.category);
        return label.isEmpty() ? asset.category : label;
    }
    case Qt::UserRole + 5: return credits_.value(asset.kuid);
    case Qt::UserRole + 6: return picked_.contains(asset.kuid);
    case Qt::UserRole + 7: return packed_label(asset.kuid);
    case Qt::UserRole + 8: return category_is_enginespec(asset.category);
    case Qt::UserRole + 9: return bits(asset).join(QStringLiteral(", "));
    case Qt::UserRole + 10: return fmt_mtime(installed_.value(asset.kuid));
    case Qt::UserRole + 11: return fmt_mtime(modified_at(asset.kuid));
    case Qt::UserRole + 12: return author(asset);
    case Qt::UserRole + 13: return build(asset);
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

const LibraryAsset* LibraryList::find(const QString& kuid) const {
    for (const LibraryAsset& asset : all_) {
        if (asset.kuid == kuid) return &asset;
    }
    return nullptr;
}

QStringList LibraryList::credit_parts(const QString& kuid) const {
    QStringList parts;
    for (const QString& part : credits_.value(kuid).split(QStringLiteral("·"))) {
        if (!part.trimmed().isEmpty()) parts << part.trimmed();
    }
    return parts;
}

QString LibraryList::author(const LibraryAsset& row) const {
    const QString owner = owners_.value(kuid_user_id(row.kuid));
    if (!owner.isEmpty()) return owner;
    const QString direct = label_of(authors_.value(row.kuid, row.author), builds_.value(row.kuid, row.build));
    if (!direct.isEmpty()) return direct;
    const QStringList parts = credit_parts(row.kuid);
    if (parts.isEmpty()) return {};
    QString build = builds_.value(row.kuid);
    if (build.isEmpty() && parts.size() >= 3) build = parts.last();
    return label_of(parts.first(), build);
}

QString LibraryList::build(const LibraryAsset& row) const {
    const QString direct = builds_.value(row.kuid, row.build);
    if (!direct.isEmpty()) return direct;
    const QStringList parts = credit_parts(row.kuid);
    return parts.size() >= 3 ? parts.last() : QString();
}

QStringList LibraryList::bits(const LibraryAsset& row) const {
    return status_bits(row.flags, editing_.contains(row.kuid), modified_.contains(row.kuid));
}

qint64 LibraryList::modified_at(const QString& kuid) const { return std::max(modified_.value(kuid), editing_.value(kuid)); }

QString LibraryList::packed_label(const QString& kuid) const {
    const QString measured = measured_.value(kuid);
    if (!measured.isEmpty()) return measured;
    const qint64 size = file_sizes_.value(kuid);
    return size > 0 ? format_bytes(size) : QString();
}

void LibraryList::add(const LibraryAsset& asset) {
    all_.removeIf([&](const LibraryAsset& row) { return row.kuid == asset.kuid; });
    all_.push_back(asset);
    rebuild();
}

void LibraryList::replace(const QList<LibraryAsset>& assets) {
    credits_.clear();
    measured_.clear();
    picked_.clear();
    all_ = assets;
    for (LibraryAsset& asset : all_) {
        const QString name = disk_names_.value(asset.kuid);
        if (!name.isEmpty()) asset.name = name;
    }
    add_ghosts();
    rebuild();
    emit picksChanged();
}

void LibraryList::set_dates(const AssetDates& dates) {
    installed_ = dates.installed;
    modified_ = dates.modified;
    editing_ = dates.editing;
    file_sizes_.clear();
    for (auto it = dates.sizes.begin(); it != dates.sizes.end(); ++it) {
        if (it.value() > 0) file_sizes_.insert(it.key(), it.value());
    }
    rebuild();
}

void LibraryList::add_ghosts() {
    QSet<QString> have;
    for (const LibraryAsset& row : all_) have.insert(row.kuid);
    for (const Scope& scope : scopes_) {
        for (const QString& kuid : scope.kuids) {
            if (have.contains(kuid)) continue;
            LibraryAsset ghost;
            ghost.kuid = kuid;
            ghost.name = kuid;
            ghost.flags = QStringLiteral("M");
            ghost.faulty = true;
            ghost.missing = true;
            all_ << ghost;
            have.insert(kuid);
        }
    }
}

void LibraryList::set_scope(const QStringList& kuids, const QString& title) {
    scopes_.push_back({QSet<QString>(kuids.begin(), kuids.end()), title, picked_});
    add_ghosts();
    picked_.clear();
    click_anchor_.clear();
    rebuild();
    emit picksChanged();
}

void LibraryList::pop_scope() {
    if (scopes_.isEmpty()) return;
    picked_ = scopes_.takeLast().picks_before;
    all_.removeIf([this](const LibraryAsset& row) {
        if (!row.missing) return false;
        for (const Scope& scope : scopes_) {
            if (scope.kuids.contains(row.kuid)) return false;
        }
        return true;
    });
    click_anchor_.clear();
    rebuild();
    emit picksChanged();
}

void LibraryList::set_owners(const QHash<qint64, QString>& owners) {
    owners_ = owners;
    if (!query_.isEmpty() || sort_key_ == QLatin1String("author")) {
        rebuild();
        return;
    }
    touch_all({kRoleAuthor});
}

void LibraryList::merge_meta(const QHash<QString, AssetMeta>& meta) {
    bool renamed = false;
    for (auto it = meta.begin(); it != meta.end(); ++it) {
        const QString label = label_of(it->author, it->build);
        if (!label.isEmpty()) authors_.insert(it.key(), label);
        if (!it->build.isEmpty()) builds_.insert(it.key(), it->build);
        // TrainzUtil prints `?` for Japanese usernames. The config file is the source.
        if (!it->username.isEmpty()) disk_names_.insert(it.key(), it->username);
    }
    for (LibraryAsset& asset : all_) {
        const QString name = disk_names_.value(asset.kuid);
        if (name.isEmpty() || name == asset.name) continue;
        asset.name = name;
        renamed = true;
    }
    const bool resort = sort_key_ == QLatin1String("author") || sort_key_ == QLatin1String("build") || (renamed && sort_key_ == QLatin1String("name"));
    if (!query_.isEmpty() || resort) {
        rebuild();
        return;
    }
    touch_all({kRoleName, kRoleAuthor, kRoleBuild});
}

void LibraryList::set_credits(const QString& kuid, const QString& text) {
    credits_.insert(kuid, text);
    const QStringList parts = credit_parts(kuid);
    QString build = parts.size() >= 3 ? parts.last() : builds_.value(kuid);
    if (parts.size() == 1 && label_of(parts.first(), build.isEmpty() ? parts.first() : build).isEmpty()) build = parts.first();
    const QString name = parts.isEmpty() ? QString() : label_of(parts.first(), build);
    if (!name.isEmpty()) authors_.insert(kuid, name);
    else if (authors_.contains(kuid) && label_of(authors_.value(kuid), build).isEmpty()) authors_.remove(kuid);
    if ((parts.size() >= 3 || (parts.size() == 1 && name.isEmpty())) && !build.isEmpty()) builds_.insert(kuid, build);
    touch(kuid, {kRoleCredits, kRoleAuthor, kRoleBuild});
}

void LibraryList::set_size(const QString& kuid, const QString& text) {
    measured_.insert(kuid, text);
    touch(kuid, {kRolePacked});
}

QString LibraryList::cell(int row, int column) const {
    if (row < 0 || row >= shown_.size()) return {};
    const LibraryAsset& asset = all_[shown_[row]];
    if (column == 0) return asset.name;
    if (column == 1) return asset.kuid;
    if (column == 2) return author(asset);
    if (column == 3) return build(asset);
    if (column == 4) return data(index(row), Qt::UserRole + 4).toString();
    if (column == 5) return bits(asset).join(QStringLiteral(", "));
    if (column == 6) return fmt_mtime(modified_at(asset.kuid));
    return packed_label(asset.kuid);
}

void LibraryList::filter(const QString& query) {
    query_ = query.trimmed().toLower();
    rebuild();
}

void LibraryList::sort_by(const QString& key) {
    const QString column = key.trimmed().isEmpty() ? QStringLiteral("name") : key.trimmed();
    if (column == sort_key_) {
        sort_desc_ = !sort_desc_;
    } else {
        sort_key_ = column;
        sort_desc_ = column == QLatin1String("installed") || column == QLatin1String("modified") || column == QLatin1String("size");
    }
    rebuild();
}

QString LibraryList::sort_mark() const { return sort_desc_ ? sort_key_ + QStringLiteral(":desc") : sort_key_; }

QString LibraryList::summary() const {
    const int faulty = static_cast<int>(std::count_if(shown_.begin(), shown_.end(), [&](int i) { return all_[i].faulty; }));
    const QString tail = picked_.isEmpty() ? QString() : ui_tr(QStringLiteral(" · %1 selected")).arg(picked_.size());
    if (!scopes_.isEmpty()) {
        const qsizetype missing = std::count_if(shown_.begin(), shown_.end(), [&](int i) { return all_[i].missing; });
        return ui_tr(QStringLiteral("%1 · %2 shown%3%4")).arg(scopes_.last().title).arg(shown_.size())
            .arg(missing > 0 ? ui_tr(QStringLiteral(" · %1 not installed")).arg(missing) : QString()).arg(tail);
    }
    if (!query_.isEmpty()) return ui_tr(QStringLiteral("%1 match · %2 faulty%3")).arg(shown_.size()).arg(faulty).arg(tail);
    if (all_.isEmpty()) return ui_tr(QStringLiteral("Installed assets from Content Manager"));
    return ui_tr(QStringLiteral("%1 installed · %2 faulty%3")).arg(shown_.size()).arg(faulty).arg(tail);
}

int LibraryList::index_of(const QString& kuid) const {
    for (int i = 0; i < shown_.size(); ++i) {
        if (all_[shown_[i]].kuid == kuid) return i;
    }
    return -1;
}

bool LibraryList::contains(const QString& kuid) const {
    const LibraryAsset* row = find(kuid);
    return row && !row->missing;
}

void LibraryList::touch(const QString& kuid, const QList<int>& roles) {
    const int row = index_of(kuid);
    if (row < 0) return;
    emit dataChanged(index(row), index(row), roles);
}

void LibraryList::touch_all(const QList<int>& roles) {
    if (shown_.isEmpty()) return;
    emit dataChanged(index(0), index(shown_.size() - 1), roles);
}

void LibraryList::toggle_pick(const QString& kuid) {
    if (!picked_.remove(kuid)) picked_.insert(kuid);
    touch(kuid, {kRolePicked});
    emit picksChanged();
}

void LibraryList::click_pick(const QString& kuid, bool shift, bool ctrl) {
    const int at = index_of(kuid);
    if (at < 0) return;
    const int anchor_at = index_of(click_anchor_);
    if (shift) {
        const int from = std::min(anchor_at < 0 ? at : anchor_at, at);
        const int to = std::max(anchor_at < 0 ? at : anchor_at, at);
        if (!ctrl) picked_.clear();
        for (int i = from; i <= to; ++i) picked_.insert(all_[shown_[i]].kuid);
    } else {
        click_anchor_ = kuid;
        if (ctrl) {
            if (!picked_.remove(kuid)) picked_.insert(kuid);
        } else {
            picked_ = {kuid};
        }
    }
    touch_all({kRolePicked});
    emit picksChanged();
}

void LibraryList::begin_drag_pick(const QString& kuid) {
    drag_snapshot_ = picked_;
    drag_on_ = !picked_.contains(kuid);
    drag_anchor_ = kuid;
    click_anchor_ = kuid;
    paint_drag(kuid);
}

void LibraryList::drag_pick(const QString& kuid) {
    if (drag_anchor_.isEmpty()) return;
    paint_drag(kuid);
}

void LibraryList::end_drag_pick() { drag_anchor_.clear(); }

void LibraryList::paint_drag(const QString& kuid) {
    const int anchor_at = index_of(drag_anchor_);
    const int at = index_of(kuid);
    if (anchor_at < 0 || at < 0) return;
    picked_ = drag_snapshot_;
    for (int i = std::min(anchor_at, at); i <= std::max(anchor_at, at); ++i) {
        const QString& row = all_[shown_[i]].kuid;
        if (drag_on_) picked_.insert(row);
        else picked_.remove(row);
    }
    touch_all({kRolePicked});
    emit picksChanged();
}

void LibraryList::set_visible_picked(bool on) {
    for (int i : shown_) {
        if (on) picked_.insert(all_[i].kuid);
        else picked_.remove(all_[i].kuid);
    }
    touch_all({kRolePicked});
    emit picksChanged();
}

QStringList LibraryList::selected_kuids() const {
    QStringList order;
    for (int i : shown_) {
        if (picked_.contains(all_[i].kuid)) order << all_[i].kuid;
    }
    for (const QString& kuid : picked_) {
        if (!order.contains(kuid)) order << kuid;
    }
    return order;
}

QString LibraryList::name_for(const QString& kuid) const {
    const LibraryAsset* row = find(kuid);
    return row ? row->name : kuid;
}

QString LibraryList::flags_for(const QString& kuid) const {
    const LibraryAsset* row = find(kuid);
    return row ? row->flags : QString();
}

QString LibraryList::tuner_kuid() const {
    QString first;
    for (int i : shown_) {
        const LibraryAsset& row = all_[i];
        if (!picked_.contains(row.kuid)) continue;
        if (category_is_enginespec(row.category)) return row.kuid;
        if (first.isEmpty()) first = row.kuid;
    }
    return first;
}

QVariantMap LibraryList::card(const QString& kuid, const QString& note) const {
    const LibraryAsset* row = find(kuid);
    QString category;
    QStringList status;
    QString author_text;
    QString build_text;
    if (row != nullptr) {
        category = category_label(row->category);
        if (category.isEmpty()) category = row->category;
        status = bits(*row);
        author_text = author(*row);
        build_text = build(*row);
    }
    return {
        {QStringLiteral("kuid"), kuid},
        {QStringLiteral("title"), row ? row->name : kuid},
        {QStringLiteral("category"), category},
        {QStringLiteral("statusText"), status.join(QStringLiteral(" · "))},
        {QStringLiteral("build"), build_text},
        {QStringLiteral("installed"), fmt_mtime(installed_.value(kuid))},
        {QStringLiteral("modified"), fmt_mtime(modified_at(kuid))},
        {QStringLiteral("size"), packed_label(kuid)},
        {QStringLiteral("author"), author_text},
        {QStringLiteral("note"), note},
    };
}

bool LibraryList::matches(const LibraryAsset& row, const QStringList& words) const {
    const QString hay = QStringList{
        row.name, row.kuid, row.category, category_label(row.category), bits(row).join(QLatin1Char(' ')),
        credits_.value(row.kuid), author(row), build(row), fmt_mtime(installed_.value(row.kuid)), fmt_mtime(modified_at(row.kuid)),
    }.join(QLatin1Char(' ')).toLower();
    return std::all_of(words.begin(), words.end(), [&](const QString& word) { return hay.contains(word); });
}

void LibraryList::rebuild() {
    beginResetModel();
    shown_.clear();
    const QStringList words = query_.split(QLatin1Char(' '), Qt::SkipEmptyParts);
    const QSet<QString>* scope = scopes_.isEmpty() ? nullptr : &scopes_.last().kuids;
    for (int i = 0; i < all_.size(); ++i) {
        if (scope && !scope->contains(all_[i].kuid)) continue;
        if (words.isEmpty() || matches(all_[i], words)) shown_.push_back(i);
    }
    const QString key = sort_key_;
    const bool desc = sort_desc_;
    // Dates and sizes: a row with no value sorts last when ascending.
    auto number = [&](const LibraryAsset& row) -> double {
        qint64 value = 0;
        if (key == QLatin1String("installed")) value = installed_.value(row.kuid);
        else if (key == QLatin1String("modified")) value = modified_at(row.kuid);
        else value = file_sizes_.value(row.kuid);
        return value || desc ? static_cast<double>(value) : 1e18;
    };
    auto text = [&](const LibraryAsset& row) -> QString {
        if (key == QLatin1String("kuid")) return row.kuid.toLower();
        if (key == QLatin1String("category") || key == QLatin1String("type")) return category_label(row.category).toLower();
        if (key == QLatin1String("author")) return author(row).toLower();
        if (key == QLatin1String("build")) return build(row).toLower();
        return row.name.toLower();
    };
    const bool numeric = key == QLatin1String("installed") || key == QLatin1String("modified") || key == QLatin1String("size");
    const bool status = key == QLatin1String("status");
    QVector<double> numbers;
    QVector<QString> labels;
    QVector<int> ranks;
    if (numeric) {
        numbers.resize(all_.size());
        for (int i = 0; i < all_.size(); ++i) numbers[i] = number(all_[i]);
    } else if (status) {
        ranks.resize(all_.size());
        for (int i = 0; i < all_.size(); ++i) ranks[i] = status_rank(bits(all_[i]));
    } else {
        labels.resize(all_.size());
        for (int i = 0; i < all_.size(); ++i) labels[i] = text(all_[i]);
    }
    std::stable_sort(shown_.begin(), shown_.end(), [&](int li, int ri) {
        const LibraryAsset& l = all_[li];
        const LibraryAsset& r = all_[ri];
        int order = 0;
        if (numeric) {
            const double a = numbers[li];
            const double b = numbers[ri];
            order = a < b ? -1 : a > b ? 1 : 0;
        } else if (status) {
            order = ranks[li] - ranks[ri];
        } else {
            order = labels[li].compare(labels[ri]);
        }
        if (order == 0) order = l.name.compare(r.name, Qt::CaseInsensitive);
        if (order == 0) order = l.kuid.compare(r.kuid);
        return desc ? order > 0 : order < 0;
    });
    endResetModel();
}

// ---------------------------------------------------------------- Bridge

TrainzUtilBridge::TrainzUtilBridge(LibraryList* library, InstallQueue* queue, QObject* parent)
    : QObject(parent), library_(library), queue_(queue) {
    const QString saved = QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).value(QStringLiteral("trainzutil/exe")).toString();
    const QString found = find_trainzutil(saved);
    if (!found.isEmpty()) {
        util_path_ = found;
        queue_->set_exe(found);
    }
    connect(library_, &LibraryList::picksChanged, this, [this] {
        note_library();
        sync_details();
    });
    connect(queue_, &InstallQueue::jobLine, this, [this](const QString& id, const QString& line) {
        static QHash<QString, int> seen;
        const int pct = pulse_percent(line, seen[id]);
        if (pct >= 0) job_pct_[id] = pct;
        job_status_[id] = line.left(96);
        note_install(id, QStringLiteral("Running"), job_pct_.value(id), line);
        if (jobs_.contains(id)) rollup(jobs_.value(id).source);
    });
    connect(queue_, &InstallQueue::jobFinished, this, [this](const QString& id, bool ok, const QString& message) {
        QDir(QDir::temp().filePath(QStringLiteral("mstn-tu-") + id)).removeRecursively();
        const QString label = jobs_.contains(id) ? jobs_.value(id).label : id;
        if (blocked(message)) {
            launcher_ok_ = false;
            launcher_text_ = QStringLiteral("Open the Trainz Launcher, then refresh");
            queue_->stop();
        }
        job_pct_[id] = ok ? 100 : job_pct_.value(id);
        job_status_[id] = ok ? QStringLiteral("Installed") : QStringLiteral("Failed");
        note_install(id, job_status_[id], ok ? 100 : job_pct_.value(id), tidy_trainzutil(message));
        if (jobs_.contains(id)) rollup(jobs_.value(id).source);
        emit jobState(id, job_status_[id]);
        const QString line = (ok ? QStringLiteral("Installed ") : QStringLiteral("Failed ")) + label + (ok || message.isEmpty() ? QString() : QStringLiteral(" — ") + tidy_trainzutil(message).right(200));
        note(line);
        if (ok) StatusHub::instance()->notify(QStringLiteral("save"), QStringLiteral("Installed"), label);
        post_status(line);
        emit changed();
    });
}

QString TrainzUtilBridge::iconFont() const { return material_icon_family(); }
QString TrainzUtilBridge::glyphHome() const { return glyph("home"); }
QString TrainzUtilBridge::glyphFolder() const { return glyph("folder_open"); }
QString TrainzUtilBridge::glyphRefresh() const { return glyph("refresh"); }
QString TrainzUtilBridge::glyphAssets() const { return glyph("inventory_2"); }
QString TrainzUtilBridge::glyphConfig() const { return glyph("file_open"); }
QString TrainzUtilBridge::glyphSearch() const { return glyph("search"); }
QString TrainzUtilBridge::glyphHistory() const { return glyph("history"); }
QString TrainzUtilBridge::glyphEdit() const { return glyph("edit"); }
QString TrainzUtilBridge::glyphPublish() const { return glyph("publish"); }
QString TrainzUtilBridge::glyphCheck() const { return glyph("fact_check"); }
QString TrainzUtilBridge::glyphChevronLeft() const { return glyph("chevron_left"); }
QString TrainzUtilBridge::glyphChevronRight() const { return glyph("chevron_right"); }
QString TrainzUtilBridge::glyphClose() const { return glyph("close"); }
QString TrainzUtilBridge::glyphCopy() const { return glyph("content_copy"); }

void TrainzUtilBridge::note(const QString& text) {
    if (!text.trimmed().isEmpty()) emit logLine(text.trimmed());
}

void TrainzUtilBridge::report(const QString& text) {
    for (const QString& line : text.split(QLatin1Char('\n'))) note(line);
}

void TrainzUtilBridge::note_library() {
    if (library_->total() > 0) library_summary_ = library_->summary();
    if (page_ == QLatin1String("library")) crumb_ = library_summary_;
    emit changed();
}

void TrainzUtilBridge::publish_load(const QString& text) {
    // The sheet waits on Content Manager only. Dates and author names fill the columns after the rows are on screen.
    const bool waiting = fill_library_;
    const QString detail = text.simplified();
    if (!detail.isEmpty() && (load_lines_.isEmpty() || load_lines_.last() != detail)) {
        load_lines_ << detail;
        while (load_lines_.size() > 8) load_lines_.removeFirst();
    }
    load_on_ = waiting;
    load_detail_ = waiting ? detail : QString();
    load_log_ = waiting ? QStringList(load_lines_.mid(0, std::max<qsizetype>(0, load_lines_.size() - 1))).join(QLatin1Char('\n')) : QString();
    if (!waiting) load_lines_.clear();
    note(detail);
    emit changed();
}

void TrainzUtilBridge::showPage(const QString& page) {
    static const QStringList pages = {QStringLiteral("library"), QStringLiteral("files"), QStringLiteral("install"), QStringLiteral("backups"), QStringLiteral("encrypt")};
    if (!pages.contains(page)) return;
    page_ = page;
    if (page_ == QLatin1String("library")) {
        crumb_ = library_summary_;
        if (library_->total() == 0 && !scanning_ && launcher_ok_) refreshLauncher();
    }
    if (page_ == QLatin1String("install")) publish_sources();
    if (page_ == QLatin1String("encrypt")) publish_scripts();
    if (page_ == QLatin1String("backups")) {
        if (backup_query_.isEmpty() && !detail_kuid_.isEmpty()) backup_query_ = detail_kuid_;
        publish_backups();
    }
    emit changed();
}

void TrainzUtilBridge::goHome() { emit homeRequested(); }

void TrainzUtilBridge::browseUtil() {
    // Pick the Trainz root folder (or a Steam library / its common folder); TrainzUtil.exe is located inside.
    const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Select the Trainz folder (or TrainzUtil.exe's folder)"), QFileInfo(util_path_).absolutePath());
    if (dir.isEmpty()) return;
    QString path = first_file({dir + QStringLiteral("/TrainzUtil.exe")});
    if (path.isEmpty()) path = trainzutil_under_common(dir);
    if (path.isEmpty()) path = trainzutil_under_common(dir + QStringLiteral("/steamapps/common"));
    if (path.isEmpty()) path = trainzutil_under_common(dir + QStringLiteral("/common"));
    if (path.isEmpty()) {
        library_summary_ = QStringLiteral("TrainzUtil.exe was not found in ") + QDir::toNativeSeparators(dir);
        note(library_summary_);
        emit changed();
        return;
    }
    util_path_ = path;
    QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).setValue(QStringLiteral("trainzutil/exe"), path);
    queue_->set_exe(path);
    refreshLauncher();
}

void TrainzUtilBridge::browseData() {
    if (QFileInfo(data_dir_).isDir()) {
        open_data_folder();
        return;
    }
    want_data_ = true;
    if (util_path_.isEmpty() || !QFileInfo(util_path_).isFile()) {
        want_data_ = false;
        browseUtil();  // no TrainzUtil yet: let the user point at the Trainz folder
        if (QFileInfo(util_path_).isFile()) want_data_ = true;
        return;
    }
    if (scanning_) {
        library_summary_ = QStringLiteral("Reading the Trainz data folder…");
        emit changed();
        return;
    }
    refreshLauncher();
}

void TrainzUtilBridge::refreshLauncher() {
    if (scanning_) {
        library_summary_ = QStringLiteral("Still checking TrainzUtil…");
        emit changed();
        return;
    }
    if (util_path_.isEmpty() || !QFileInfo(util_path_).isFile()) {
        launcher_ok_ = false;
        launcher_text_ = QStringLiteral("Not found — press Browse");
        library_summary_ = launcher_text_;
        emit changed();
        return;
    }
    scanning_ = true;
    launcher_ok_ = false;
    fill_library_ = true;
    launcher_text_ = QStringLiteral("Checking Launcher…");
    library_summary_ = QStringLiteral("Reading Content Manager…");
    publish_load(QStringLiteral("Asking Content Manager for the installed asset list. The table stays on the last copy, or empty, until TrainzUtil answers."));

    scan_state_ = std::make_shared<TrainzScanGate>();
    const QString exe = util_path_;
    const std::shared_ptr<TrainzScanGate> state = scan_state_;
    scan_thread_ = QThread::create([this, exe, state] {
        const RunOut data = run_trainzutil(exe, {QStringLiteral("getinstallationdatapath")}, 30000, state);
        const QString folder = parse_installation_data_path(data.text);
        if (!state->alive.load()) return;
        QMetaObject::invokeMethod(this, [this, folder] { on_data_folder(folder); }, Qt::QueuedConnection);

        QString fail;
        QString build = QStringLiteral("Connected");
        QList<LibraryAsset> rows;
        if (!launcher_process_running()) {
            fail = QStringLiteral("Open the Trainz Launcher first");
        } else {
            const RunOut version = run_trainzutil(exe, {QStringLiteral("version")}, 20000, state);
            if (version.timeout) fail = QStringLiteral("TrainzUtil timed out");
            else if (launcher_reply_blocked(version.text)) fail = QStringLiteral("Open the Trainz Launcher first");
            else {
                build = version_label(version.text);
                const RunOut authors = run_trainzutil(exe, {QStringLiteral("authors")}, 30000, state);
                if (authors.timeout) fail = QStringLiteral("Launcher did not answer — turn on Advanced debug tools");
                else if (launcher_reply_blocked(authors.text)) fail = QStringLiteral("Launcher is open but Advanced debug tools are off");
            }
        }
        if (fail.isEmpty() && state->alive.load()) {
            const QString batch = QDir::temp().filePath(QStringLiteral("mstn-tu-library.txt"));
            QFile file(batch);
            if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                fail = QStringLiteral("Could not write the library query");
            } else {
                file.write("\"set\" \"all\" \"searchbycategory\" \"-\"\n\"set\" \"inst\" \"filterbystatus\" \"I\" $(all)\n\"print\" \"inst\"\n");
                file.close();
                const RunOut listed = run_trainzutil(exe, {QStringLiteral("@") + batch}, 180000, state);
                if (listed.timeout) fail = QStringLiteral("Content Manager took too long");
                else if (launcher_reply_blocked(listed.text)) fail = QStringLiteral("Open the Trainz Launcher first");
                else {
                    rows = parse_installed_library(listed.text);
                    if (rows.isEmpty() && listed.text.contains(QLatin1String("error"), Qt::CaseInsensitive))
                        fail = listed.text.right(300);
                }
            }
        }
        if (!state->alive.load()) return;
        const bool ok = fail.isEmpty();
        const QString text = ok ? build : fail;
        QMetaObject::invokeMethod(
            this, [this, ok, text, rows] { on_library_scan(ok, text, rows); }, Qt::QueuedConnection);
    });
    connect(scan_thread_, &QThread::finished, this, [this] { scan_thread_ = nullptr; });
    scan_thread_->start();
}

void TrainzUtilBridge::scan_content() {
    const QStringList roots = content_roots(data_dir_);
    if (roots.isEmpty()) return;
    const int gen = ++fill_gen_;
    fill_dates_ = true;
    fill_meta_ = true;
    publish_load(QStringLiteral("Walking original and local archives for install time, modified time, and file size."));
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, gen, roots] {
        auto index = std::make_shared<const ContentIndex>(index_content(roots));
        const AssetDates dates = read_asset_dates(*index);
        post([self, gen, index, dates] {
            if (!self || gen != self->fill_gen_) return;
            self->index_ = index;
            self->fill_dates_ = false;
            self->library_->set_dates(dates);
            self->note_library();
            self->publish_load(ui_tr(QStringLiteral("Dates and file sizes · %1 installed · %2 modified · %3 sized · %4 open for edit.%5"))
                                   .arg(dates.installed.size()).arg(dates.modified.size()).arg(dates.sizes.size()).arg(dates.editing.size())
                                   .arg(self->fill_meta_ ? ui_tr(QStringLiteral(" Author names are still being read from each archive.")) : QString()));
            if (!self->focus_kuid_.isEmpty()) self->load_cover(self->focus_kuid_);
        });
        QHash<qint64, QString> owners;
        for (const QString& root : roots) {
            owners = read_kuid_owners(root + QStringLiteral("/assets.tdx"));
            if (!owners.isEmpty()) break;
        }
        if (!owners.isEmpty()) {
            post([self, gen, owners] {
                if (!self || gen != self->fill_gen_) return;
                self->library_->set_owners(owners);
            });
        }
        const QHash<QString, AssetMeta> meta = scan_archive_meta(*index, meta_cache_file(), [self, gen](const QString& text) {
            post([self, gen, text] {
                if (self && gen == self->fill_gen_) self->publish_load(text);
            });
        });
        post([self, gen, meta] {
            if (!self || gen != self->fill_gen_) return;
            self->fill_meta_ = false;
            self->library_->merge_meta(meta);
            self->publish_load(QStringLiteral("Author and build from archives · %1.%2")
                                   .arg(self->library_->author_count())
                                   .arg(self->fill_library_ ? QStringLiteral(" Content Manager is still sending the installed list.") : QString()));
            self->sync_details();
        });
    });
}

void TrainzUtilBridge::addFiles() {
    if (page_ == QLatin1String("encrypt")) {
        addScripts();
        return;
    }
    const QStringList paths = QFileDialog::getOpenFileNames(nullptr, QStringLiteral("Add packages"), {}, QStringLiteral("Packages (*.cdp *.zip *.tzarc)"));
    QVariantList urls;
    for (const QString& path : paths) urls << QUrl::fromLocalFile(path).toString();
    dropUrls(urls);
}

void TrainzUtilBridge::clearSources() {
    if (page_ == QLatin1String("encrypt")) {
        clearScripts();
        return;
    }
    queue_->stop();
    sources_.clear();
    jobs_.clear();
    job_order_.clear();
    job_pct_.clear();
    job_status_.clear();
    install_rows_.clear();
    install_order_.clear();
    publish_tasks();
    selected_source_.clear();
    view_stack_.clear();
    publish_sources();
    show_jobs(QStringLiteral("Drop a zip or CDP"), {});
}

void TrainzUtilBridge::dropUrls(const QVariantList& urls) {
    QStringList paths;
    for (const QVariant& url_value : urls) {
        const QUrl url(url_value.toString());
        const QString path = url.isLocalFile() ? url.toLocalFile() : url_value.toString();
        if (!path.isEmpty()) paths << path;
    }
    if (paths.isEmpty()) return;
    QStringList scripts;
    QStringList packs;
    for (const QString& path : paths) {
        if (path.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
            library_->add(asset_from_tzarc(path));
            note_library();
            continue;
        }
        if (QFileInfo(path).isDir() || path.endsWith(QLatin1String(".gs"), Qt::CaseInsensitive)) scripts << path;
        else packs << path;
    }
    if (page_ == QLatin1String("encrypt") || (!scripts.isEmpty() && packs.isEmpty())) {
        add_script_paths(page_ == QLatin1String("encrypt") ? scripts + packs : scripts);
        return;
    }
    if (!packs.isEmpty()) add_package_paths(packs);
    if (!scripts.isEmpty()) add_script_paths(scripts);
}

void TrainzUtilBridge::add_package_paths(const QStringList& paths) {
    QStringList fresh;
    for (const QString& raw : paths) {
        const QFileInfo info(raw);
        if (!info.isFile()) continue;
        const QString suffix = info.suffix().toLower();
        if (suffix != QLatin1String("zip") && suffix != QLatin1String("cdp")) {
            note(QStringLiteral("Skipped ") + info.fileName());
            continue;
        }
        const QString id = info.absoluteFilePath();
        if (std::any_of(sources_.begin(), sources_.end(), [&](const Source& s) { return s.id == id; })) continue;
        Source source;
        source.id = id;
        source.path = id;
        source.name = info.fileName();
        source.kind = suffix;
        source.status = QStringLiteral("Reading…");
        sources_.push_back(source);
        fresh << id;
    }
    if (fresh.isEmpty()) return;
    publish_sources();
    showPage(QStringLiteral("install"));
    QPointer<TrainzUtilBridge> self(this);
    for (const QString& id : fresh) {
        spawn([self, id] {
            QList<TuJob> jobs;
            QString err;
            try {
                jobs = scan_package(id);
            } catch (const std::exception& exc) {
                err = QString::fromUtf8(exc.what());
            }
            post([self, id, jobs, err] {
                if (!self) return;
                auto it = std::find_if(self->sources_.begin(), self->sources_.end(), [&](const Source& s) { return s.id == id; });
                if (it == self->sources_.end()) return;
                if (!err.isEmpty()) {
                    it->status = QStringLiteral("Unreadable");
                    self->note(err);
                    self->publish_sources();
                    return;
                }
                for (const TuJob& job : jobs) {
                    self->jobs_.insert(job.id, job);
                    self->job_order_ << job.id;
                }
                const int n = static_cast<int>(std::count_if(jobs.begin(), jobs.end(), [](const TuJob& j) { return j.can_install; }));
                it->status = QStringLiteral("%1 to install").arg(n);
                self->publish_sources();
                if (self->selected_source_.isEmpty() || self->selected_source_ == id) self->show_source(id);
            });
        });
    }
}

void TrainzUtilBridge::show_jobs(const QString& crumb, const QList<TuJob>& jobs) {
    QVariantList rows;
    for (const TuJob& job : jobs) rows << job_row(job);
    if (page_ != QLatin1String("library")) crumb_ = crumb;
    emit contentsReady(rows);
    emit changed();
}

void TrainzUtilBridge::show_source(const QString& source_id) {
    auto it = std::find_if(sources_.begin(), sources_.end(), [&](const Source& s) { return s.id == source_id; });
    if (it == sources_.end()) return;
    selected_source_ = source_id;
    view_stack_ = {{source_id, {}}};
    QList<TuJob> jobs;
    for (const QString& id : job_order_) {
        const TuJob& job = jobs_[id];
        if (job.source == it->path && job.chain.isEmpty()) jobs << job;
    }
    show_jobs(it->name, jobs);
}

void TrainzUtilBridge::openEntry(const QString& job_id) {
    if (!jobs_.contains(job_id) || jobs_.value(job_id).kind != QLatin1String("zip-nested")) return;
    const TuJob job = jobs_.value(job_id);
    const QStringList chain = job.chain + QStringList{job.member};
    QList<TuJob> found;
    try {
        found = scan_package(job.source, chain);
    } catch (const std::exception& exc) {
        note(QString::fromUtf8(exc.what()));
        return;
    }
    for (const TuJob& item : found) {
        jobs_.insert(item.id, item);
        job_order_ << item.id;
    }
    view_stack_.push_back({job.source, chain});
    show_jobs(job.label, found);
}

void TrainzUtilBridge::backContents() {
    if (view_stack_.size() <= 1) {
        if (!selected_source_.isEmpty()) show_source(selected_source_);
        return;
    }
    view_stack_.pop_back();
    const auto [source, chain] = view_stack_.last();
    if (chain.isEmpty()) {
        show_source(selected_source_.isEmpty() ? source : selected_source_);
        return;
    }
    QList<TuJob> jobs;
    for (const QString& id : job_order_) {
        const TuJob& job = jobs_[id];
        if (job.source == source && job.chain == chain) jobs << job;
    }
    show_jobs(QFileInfo(chain.last()).fileName(), jobs);
}

QList<TuJob> TrainzUtilBridge::package_jobs(const QString& path) const {
    const bool cdp = path.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive);
    QList<TuJob> out;
    for (const QString& id : job_order_) {
        const TuJob& job = jobs_[id];
        if (job.source != path || !job.chain.isEmpty()) continue;
        if (cdp ? job.kind == QLatin1String("cdp") : (job.can_install && (job.kind == QLatin1String("zip-cdp") || job.kind == QLatin1String("zip-folder")))) out << job;
    }
    return out;
}

void TrainzUtilBridge::installChecked() {
    if (util_path_.isEmpty() || !QFileInfo::exists(util_path_)) {
        note(QStringLiteral("Pick TrainzUtil.exe with Browse"));
        return;
    }
    if (!launcher_ok_) {
        note(launcher_text_.isEmpty() ? QStringLiteral("Open the Trainz Launcher first") : launcher_text_);
        return;
    }
    QList<TuJob> picked;
    for (Source& source : sources_) {
        if (!source.checked || source.percent >= 100) continue;
        const QList<TuJob> jobs = package_jobs(source.path);
        if (jobs.isEmpty()) {
            source.status = QStringLiteral("Nothing to install");
            continue;
        }
        source.status = QStringLiteral("Queued");
        source.percent = 0;
        for (const TuJob& job : jobs) {
            job_pct_[job.id] = 0;
            job_status_[job.id] = QStringLiteral("Queued");
            note_install(job.id, QStringLiteral("Queued"), 0, QStringLiteral("Queued"));
        }
        picked << jobs;
    }
    publish_sources();
    if (picked.isEmpty()) {
        note(QStringLiteral("Nothing ready to install"));
        return;
    }
    note(QStringLiteral("Queued %1").arg(picked.size()));
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, picked] {
        QList<InstallJob> staged;
        QStringList failed;
        for (const TuJob& job : picked) {
            const QString dest = QDir::temp().filePath(QStringLiteral("mstn-tu-") + job.id);
            try {
                staged.push_back({job.id, stage_job(job, dest)});
            } catch (const std::exception& exc) {
                failed << job.id + QLatin1Char('\t') + QString::fromUtf8(exc.what());
            }
        }
        post([self, staged, failed] {
            if (!self) return;
            for (const QString& row : failed) {
                const QString id = row.section(QLatin1Char('\t'), 0, 0);
                self->job_status_[id] = QStringLiteral("Failed");
                self->note_install(id, QStringLiteral("Failed"), 0, row.section(QLatin1Char('\t'), 1));
                if (self->jobs_.contains(id)) self->rollup(self->jobs_.value(id).source);
            }
            self->queue_->set_exe(self->util_path_);
            self->queue_->enqueue(staged);
        });
    });
}

void TrainzUtilBridge::note_install(const QString& job_id, const QString& state, int percent, const QString& line) {
    if (!jobs_.contains(job_id)) return;  // cleared/removed while a process was still reporting
    const QString key = QStringLiteral("install:") + job_id;
    QVariantMap row = install_rows_.value(key);
    if (row.isEmpty()) {
        row = {
            {QStringLiteral("taskId"), key},
            {QStringLiteral("name"), jobs_.contains(job_id) ? jobs_.value(job_id).label : job_id},
            {QStringLiteral("action"), QStringLiteral("Install")},
            {QStringLiteral("detail"), QString()},
            {QStringLiteral("log"), QString()},
        };
        install_order_ << key;
    }
    row[QStringLiteral("state")] = state;
    row[QStringLiteral("percent")] = std::clamp(percent, 0, 100);
    const QString chunk = line.trimmed();
    if (!chunk.isEmpty()) {
        const QString current = row.value(QStringLiteral("log")).toString();
        if (!current.endsWith(chunk)) row[QStringLiteral("log")] = current.isEmpty() ? chunk : current + QLatin1Char('\n') + chunk;
        row[QStringLiteral("detail")] = chunk.split(QLatin1Char('\n')).last().left(180);
    }
    install_rows_.insert(key, row);
    if (!task_busy_) {
        const int total = install_rows_.size();
        const int done = static_cast<int>(std::count_if(install_rows_.begin(), install_rows_.end(), [](const QVariantMap& r) {
            const QString s = r.value(QStringLiteral("state")).toString();
            return s == QLatin1String("Installed") || s == QLatin1String("Failed") || s == QLatin1String("Paused");
        }));
        task_summary_ = QStringLiteral("Install · %1 of %2").arg(done).arg(total);
        task_percent_ = total ? done * 100 / total : 0;
    }
    publish_tasks();
}

void TrainzUtilBridge::rollup(const QString& source_path) {
    const QList<TuJob> jobs = package_jobs(source_path);
    auto it = std::find_if(sources_.begin(), sources_.end(), [&](const Source& s) { return s.path == source_path; });
    if (jobs.isEmpty() || it == sources_.end()) return;
    int sum = 0;
    int done = 0;
    int failed = 0;
    QString active;
    for (const TuJob& job : jobs) {
        sum += job_pct_.value(job.id);
        const QString status = job_status_.value(job.id);
        if (status == QLatin1String("Installed")) ++done;
        else if (status == QLatin1String("Failed")) ++failed;
        else if (active.isEmpty()) active = status;
    }
    int avg = sum / static_cast<int>(jobs.size());
    QString status;
    if (!active.isEmpty()) status = jobs.size() > 1 ? QStringLiteral("%1/%2  %3").arg(done + 1).arg(jobs.size()).arg(active) : active;
    else if (failed) status = failed == jobs.size() ? QStringLiteral("Failed") : QStringLiteral("Failed %1 of %2").arg(failed).arg(jobs.size());
    else {
        status = QStringLiteral("Installed");
        avg = 100;
    }
    it->status = status;
    it->percent = std::clamp(avg, 0, 100);
    publish_sources();
}

void TrainzUtilBridge::publish_tasks() {
    QVariantList rows = batch_rows_;
    for (const QString& key : install_order_) rows << install_rows_.value(key);
    emit tasksReady(rows);
    emit changed();
}

void TrainzUtilBridge::scanLibrary() {
    page_ = QStringLiteral("library");
    crumb_ = QStringLiteral("Reading Content Manager…");
    emit changed();
    refreshLauncher();
}

void TrainzUtilBridge::filterLibrary(const QString& text) {
    library_->filter(text);
    note_library();
}

void TrainzUtilBridge::sortLibrary(const QString& key) {
    library_->sort_by(key);
    note_library();
}

int TrainzUtilBridge::rowIndex(const QString& kuid) const { return library_->index_of(kuid); }
bool TrainzUtilBridge::libraryHas(const QString& kuid) const { return library_->contains(kuid); }

bool TrainzUtilBridge::can_query() const { return launcher_ok_ && QFileInfo(util_path_).isFile(); }

bool TrainzUtilBridge::ready() {
    if (!QFileInfo(util_path_).isFile()) {
        note(QStringLiteral("Pick TrainzUtil.exe with Browse"));
        return false;
    }
    if (!launcher_ok_) {
        note(launcher_text_.isEmpty() ? QStringLiteral("Open the Trainz Launcher first") : launcher_text_);
        return false;
    }
    return true;
}

void TrainzUtilBridge::sync_details() {
    if (page_ != QLatin1String("library")) return;
    const QStringList kuids = library_->selected_kuids();
    if (kuids.isEmpty()) {
        if (detail_from_picks_) {
            detail_from_picks_ = false;
            focus_kuid_.clear();
            clear_detail();
        }
        return;
    }
    detail_from_picks_ = true;
    const QString focus = kuids.contains(focus_kuid_) ? focus_kuid_ : kuids.first();
    publish_cards(kuids, focus, !dep_cache_.contains(focus));
}

void TrainzUtilBridge::focusAsset(const QString& kuid) {
    if (kuid.isEmpty()) return;
    const QStringList picked = library_->selected_kuids();
    if (picked.size() > 1) {
        if (!picked.contains(kuid)) return;
        detail_from_picks_ = true;
        publish_cards(picked, kuid, !dep_cache_.contains(kuid));
        return;
    }
    detail_from_picks_ = picked.contains(kuid);
    publish_cards({kuid}, kuid, !dep_cache_.contains(kuid));
}

void TrainzUtilBridge::openDependencyList(const QString& kuid, const QString& pick) {
    const QVariantList deps = dep_cache_.value(kuid).deps;
    if (deps.isEmpty()) return;
    QStringList kuids;
    for (const QVariant& dep : deps) kuids << dep.toMap().value(QStringLiteral("kuid")).toString();
    library_->set_scope(kuids, QStringLiteral("Dependencies of %1").arg(library_->name_for(kuid)));
    if (!pick.isEmpty() && library_->index_of(pick) >= 0) clickPick(pick, 0);
    note_library();
}

void TrainzUtilBridge::closeScope() {
    library_->pop_scope();
    note_library();
}

void TrainzUtilBridge::publish_cards(const QStringList& kuids, const QString& focus, bool fetch) {
    const QStringList shown = kuids.mid(0, 40);
    if (kuids.size() > 40 && !detail_cap_noted_) {
        note(QStringLiteral("Showing the first 40"));
        detail_cap_noted_ = true;
    } else if (kuids.size() <= 40) {
        detail_cap_noted_ = false;
    }
    QVariantList cards;
    QVariantMap chosen;
    for (const QString& kuid : shown) {
        QString text;
        if (kuid == focus && fetch) text = can_query() ? QStringLiteral("Reading dependencies…") : QStringLiteral("Open the Trainz Launcher to list dependencies");
        else text = dep_cache_.value(kuid).note;
        const QVariantMap card = library_->card(kuid, text);
        if (kuid == focus) chosen = card;
        cards << card;
    }
    if (chosen.isEmpty()) {
        clear_detail();
        return;
    }
    if (focus != focus_kuid_) load_cover(focus);
    focus_kuid_ = focus;
    detail_cards_ = cards;
    detail_on_ = true;
    detail_kuid_ = focus;
    detail_title_ = chosen.value(QStringLiteral("title")).toString();
    detail_deps_ = fetch ? QVariantList() : dep_cache_.value(focus).deps;
    detail_status_.clear();
    for (const QString& bit : chosen.value(QStringLiteral("statusText")).toString().split(QStringLiteral(" · "), Qt::SkipEmptyParts)) detail_status_ << bit;
    emit changed();
    if (fetch && can_query()) fetch_deps(focus);
}

void TrainzUtilBridge::fetch_deps(const QString& kuid) {
    const QString exe = util_path_;
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, kuid] {
        const QString raw = run_tu(exe, {QStringLiteral("list-dependencies"), QStringLiteral("direct"), kuid}, 90000);
        const QString config = run_tu(exe, {QStringLiteral("printconfig"), kuid}, 40000);
        const QString all = run_tu(exe, {QStringLiteral("list-dependencies"), QStringLiteral("all"), kuid}, 90000);
        post([self, kuid, raw, config, all] {
            if (!self) return;
            QString text;
            QVariantList deps;
            if (blocked(raw) || blocked(config)) {
                text = QStringLiteral("Open the Trainz Launcher first");
            } else {
                const QString credits = config_credits(config);
                if (!credits.isEmpty()) self->library_->set_credits(kuid, credits);
                for (const QString& dep : dependency_kuids(tidy_trainzutil(raw), kuid))
                    deps << QVariantMap{{QStringLiteral("name"), self->library_->name_for(dep)}, {QStringLiteral("kuid"), dep}};
                if (deps.isEmpty()) text = QStringLiteral("No direct dependencies");
            }
            QString total;
            if (!blocked(all)) {
                // ponytail: "all" output assumed to be parseable like "direct"; falls back to direct deps if empty. Sizes are archive sizes from the library index.
                QStringList closure = dependency_kuids(tidy_trainzutil(all), kuid);
                if (closure.isEmpty()) for (const QVariant& dep : deps) closure << dep.toMap().value(QStringLiteral("kuid")).toString();
                closure.removeDuplicates();
                qint64 sum = self->library_->size_of(kuid);
                for (const QString& dep : closure) sum += self->library_->size_of(dep);
                if (sum > 0) total = format_bytes(sum) + QStringLiteral(" (") + QString::number(closure.size() + 1) + QStringLiteral(")");
            }
            self->dep_cache_.insert(kuid, {text, deps, total});
            if (kuid != self->focus_kuid_) return;
            QStringList kuids = {kuid};
            if (self->detail_from_picks_) {
                kuids = self->library_->selected_kuids();
                if (!kuids.contains(kuid)) kuids.prepend(kuid);
            }
            self->publish_cards(kuids, kuid, false);
        });
    });
}

void TrainzUtilBridge::load_cover(const QString& kuid) {
    const int gen = ++cover_gen_;
    cover_url_.clear();
    cover_busy_ = static_cast<bool>(index_);
    const std::shared_ptr<const ContentIndex> index = index_;
    if (!index) return;
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, gen, kuid, index] {
        const QString path = asset_cover_path(*index, kuid);
        post([self, gen, kuid, path] {
            if (!self || gen != self->cover_gen_ || kuid != self->focus_kuid_) return;
            self->cover_url_ = path.isEmpty() ? QString() : QUrl::fromLocalFile(path).toString();
            self->cover_busy_ = false;
            emit self->changed();
        });
    });
}

void TrainzUtilBridge::clear_detail() {
    detail_on_ = false;
    focus_kuid_.clear();
    detail_kuid_.clear();
    detail_title_.clear();
    detail_deps_.clear();
    detail_status_.clear();
    detail_cards_.clear();
    cover_url_.clear();
    cover_busy_ = false;
    emit changed();
}

void TrainzUtilBridge::set_detail(const QVariantMap& card, const QStringList& status) {
    detail_on_ = true;
    detail_kuid_ = card.value(QStringLiteral("kuid")).toString();
    detail_title_ = card.value(QStringLiteral("title")).toString();
    detail_deps_.clear();
    detail_status_.clear();
    for (const QString& bit : status) {
        if (!bit.isEmpty()) detail_status_ << bit;
    }
    QVariantMap row = card;
    row[QStringLiteral("statusText")] = status.join(QStringLiteral(" · "));
    detail_cards_ = {row};
    focus_kuid_ = detail_kuid_;
    cover_url_.clear();
    cover_busy_ = false;
    emit changed();
}

void TrainzUtilBridge::clickPick(const QString& kuid, int modifiers) {
    library_->click_pick(kuid, modifiers & Qt::ShiftModifier, modifiers & Qt::ControlModifier);
    focusAsset(kuid);
}

void TrainzUtilBridge::beginDragPick(const QString& kuid) { library_->begin_drag_pick(kuid); }
void TrainzUtilBridge::dragPick(const QString& kuid) { library_->drag_pick(kuid); }
void TrainzUtilBridge::endDragPick() { library_->end_drag_pick(); }
void TrainzUtilBridge::pickVisible(bool on) { library_->set_visible_picked(on); }

void TrainzUtilBridge::stopQueue() {
    queue_->stop();
    for (Source& source : sources_) {
        if (source.percent < 100) source.status = QStringLiteral("Waiting");
    }
    publish_sources();
}

void TrainzUtilBridge::removeSource(const QString& source_id) {
    auto it = std::find_if(sources_.begin(), sources_.end(), [&](const Source& s) { return s.id == source_id; });
    if (it == sources_.end()) return;
    const QString path = it->path;
    sources_.erase(it);
    for (auto job = jobs_.begin(); job != jobs_.end();) {
        if (job->source == path) {
            const QString key = job.key();
            job_order_.removeAll(key);
            job_pct_.remove(key);
            job_status_.remove(key);
            install_rows_.remove(QStringLiteral("install:") + key);
            install_order_.removeAll(QStringLiteral("install:") + key);
            job = jobs_.erase(job);
        } else {
            ++job;
        }
    }
    publish_sources();
    if (selected_source_ == source_id) {
        selected_source_.clear();
        view_stack_.clear();
        show_jobs(QStringLiteral("Drop a zip or CDP"), {});
    }
}

void TrainzUtilBridge::selectSource(const QString& source_id) {
    for (Source& source : sources_) source.checked = source.id == source_id;
    publish_sources();
    show_source(source_id);
}

void TrainzUtilBridge::setSourcesChecked(bool on) {
    for (Source& source : sources_) source.checked = on;
    publish_sources();
}

QVariantList TrainzUtilBridge::classifyLog(const QString& text) const { return classify_trainz_log(text); }

void TrainzUtilBridge::closeReport() {
    report_text_.clear();
    emit changed();
}

void TrainzUtilBridge::copyText(const QString& text) {
    if (text.trimmed().isEmpty()) {
        note(QStringLiteral("Nothing to copy"));
        return;
    }
    QGuiApplication::clipboard()->setText(text);
    note(QStringLiteral("Copied"));
}

// ---- Encrypt

void TrainzUtilBridge::addScripts() {
    const QStringList paths = QFileDialog::getOpenFileNames(nullptr, QStringLiteral("Add scripts"), {}, QStringLiteral("GameScript (*.gs)"));
    if (!paths.isEmpty()) add_script_paths(paths);
}

void TrainzUtilBridge::add_script_paths(const QStringList& paths) {
    const QStringList found = collect_script_files(paths);
    if (found.isEmpty()) {
        note(QStringLiteral("No .gs files in that drop"));
        return;
    }
    for (const QString& path : found) {
        const bool known = std::any_of(scripts_.begin(), scripts_.end(), [&](const QVariant& row) { return row.toMap().value(QStringLiteral("scriptId")) == path; });
        if (known) continue;
        scripts_ << QVariantMap{
            {QStringLiteral("scriptId"), path},
            {QStringLiteral("name"), QFileInfo(path).fileName()},
            {QStringLiteral("folder"), QDir::toNativeSeparators(QFileInfo(path).absolutePath())},
            {QStringLiteral("status"), QStringLiteral("Ready")},
            {QStringLiteral("tone"), QStringLiteral("wait")},
        };
    }
    showPage(QStringLiteral("encrypt"));
}

void TrainzUtilBridge::publish_scripts() { emit scriptsReady(scripts_); }

void TrainzUtilBridge::clearScripts() {
    scripts_.clear();
    publish_scripts();
}

void TrainzUtilBridge::removeScript(const QString& script_id) {
    scripts_.removeIf([&](const QVariant& row) { return row.toMap().value(QStringLiteral("scriptId")) == script_id; });
    publish_scripts();
}

void TrainzUtilBridge::encryptScripts() {
    if (encrypting_) return;
    if (!QFileInfo(util_path_).isFile()) {
        note(QStringLiteral("Pick TrainzUtil.exe with Browse"));
        return;
    }
    if (scripts_.isEmpty()) {
        note(QStringLiteral("Drop .gs files first"));
        return;
    }
    encrypting_ = true;
    QStringList sources;
    for (QVariant& value : scripts_) {
        QVariantMap row = value.toMap();
        row[QStringLiteral("status")] = QStringLiteral("Encrypting…");
        row[QStringLiteral("tone")] = QStringLiteral("run");
        sources << row.value(QStringLiteral("scriptId")).toString();
        value = row;
    }
    publish_scripts();
    const QString exe = util_path_;
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, sources] {
        const qint64 started = QDateTime::currentSecsSinceEpoch();
        const QString batch = QDir::temp().filePath(QStringLiteral("mstn-gs-encrypt.txt"));
        QString body;
        for (const QString& src : sources) body += QStringLiteral("\"encrypt\" \"%1\"\n").arg(QDir::toNativeSeparators(src));
        QFile file(batch);
        QHash<QString, QPair<bool, QString>> results;
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            for (const QString& src : sources) results.insert(src, {false, QStringLiteral("Could not write the batch")});
        } else {
            file.write(body.toUtf8());
            file.close();
            const QString text = run_tu(exe, {QStringLiteral("@") + batch}, std::max(180000, 20000 * static_cast<int>(sources.size())));
            QFile::remove(batch);
            const QHash<QString, QString> errors = encrypt_error_map(text);
            for (const QString& src : sources) {
                const QString gse = QFileInfo(src).absolutePath() + QLatin1Char('/') + QFileInfo(src).completeBaseName() + QStringLiteral(".gse");
                const QString err = errors.value(QDir::toNativeSeparators(src).toLower());
                const bool fresh = QFileInfo(gse).isFile() && QFileInfo(gse).lastModified().toSecsSinceEpoch() >= started - 2;
                if (!err.isEmpty()) results.insert(src, {false, err});
                else if (fresh) results.insert(src, {true, QFileInfo(gse).fileName()});
                else results.insert(src, {false, text.contains(QLatin1String("timed out")) ? QStringLiteral("TrainzUtil timed out") : QStringLiteral("No .gse written")});
            }
        }
        post([self, results] {
            if (!self) return;
            int done = 0;
            int failed = 0;
            for (QVariant& value : self->scripts_) {
                QVariantMap row = value.toMap();
                const QString id = row.value(QStringLiteral("scriptId")).toString();
                if (!results.contains(id)) continue;
                const auto [ok, msg] = results.value(id);
                row[QStringLiteral("tone")] = ok ? QStringLiteral("ok") : QStringLiteral("bad");
                row[QStringLiteral("status")] = msg;
                ok ? ++done : ++failed;
                value = row;
            }
            self->encrypting_ = false;
            self->publish_scripts();
            self->note(failed ? QStringLiteral("%1 encrypted · %2 failed").arg(done).arg(failed) : QStringLiteral("%1 encrypted beside the .gs files").arg(done));
        });
    });
}

// ---- Asset actions

QStringList TrainzUtilBridge::action_kuids() {
    const QStringList kuids = library_->selected_kuids();
    if (!kuids.isEmpty()) return kuids;
    if (detail_on_ && !detail_kuid_.isEmpty()) return {detail_kuid_};
    note(QStringLiteral("Select an asset"));
    return {};
}

void TrainzUtilBridge::run_action(const QString& command, const QString& label) {
    if (task_busy_) {
        note(QStringLiteral("Wait for the current task"));
        return;
    }
    if (!ready()) return;
    QStringList kuids = action_kuids();
    if (kuids.isEmpty()) return;
    if (kuids.size() > 40) {
        kuids = kuids.mid(0, 40);
        note(QStringLiteral("Running the first 40"));
    }
    const int gen = ++task_gen_;
    task_busy_ = true;
    QVariantList rows;
    for (const QString& kuid : kuids) {
        rows << QVariantMap{
            {QStringLiteral("taskId"), command + QLatin1Char(':') + kuid},
            {QStringLiteral("kuid"), kuid},
            {QStringLiteral("name"), library_->name_for(kuid)},
            {QStringLiteral("action"), label},
            {QStringLiteral("state"), QStringLiteral("Queued")},
            {QStringLiteral("detail"), QStringLiteral("Queued")},
            {QStringLiteral("log"), QStringLiteral("Queued")},
            {QStringLiteral("percent"), 0},
        };
    }
    batch_rows_ = rows;
    task_summary_ = QStringLiteral("%1 · 0 of %2").arg(label).arg(rows.size());
    task_percent_ = 0;
    publish_tasks();
    const QString exe = util_path_;
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, gen, command, label, rows]() mutable {
        auto step = [&](const QString& summary, int percent, bool busy) {
            post([self, gen, rows, summary, percent, busy] {
                if (!self || gen != self->task_gen_) return;
                self->task_busy_ = busy;
                self->batch_rows_ = rows;
                self->task_summary_ = summary;
                self->task_percent_ = std::clamp(percent, 0, 100);
                self->publish_tasks();
            });
        };
        const int total = static_cast<int>(rows.size());
        int failed = 0;
        for (int i = 0; i < total; ++i) {
            QVariantMap row = rows[i].toMap();
            row[QStringLiteral("state")] = QStringLiteral("Running");
            row[QStringLiteral("percent")] = 40;
            row[QStringLiteral("detail")] = QStringLiteral("Running…");
            row[QStringLiteral("log")] = QStringLiteral("Running…");
            rows[i] = row;
            const QString summary = QStringLiteral("%1 · %2 of %3").arg(label).arg(i + 1).arg(total);
            const int pct = static_cast<int>((i + 0.4) / total * 100);
            step(summary, pct, true);
            QStringList collected;
            const QString raw = stream_tu(exe, {command, row.value(QStringLiteral("kuid")).toString()}, 180000, [&](const QString& line) {
                collected << line;
                const QString shown = classify_trainz_line(line).second;
                row[QStringLiteral("log")] = collected.join(QLatin1Char('\n'));
                if (!shown.isEmpty()) row[QStringLiteral("detail")] = shown.left(180);
                row[QStringLiteral("percent")] = std::min(90, 45 + static_cast<int>(collected.size()));
                rows[i] = row;
                step(summary, pct, true);
            });
            const auto [ok, detail] = task_outcome(raw);
            if (!raw.isEmpty()) row[QStringLiteral("log")] = raw;
            row[QStringLiteral("state")] = ok ? QStringLiteral("Done") : QStringLiteral("Failed");
            row[QStringLiteral("detail")] = detail;
            row[QStringLiteral("percent")] = 100;
            rows[i] = row;
            if (!ok) ++failed;
            if (!ok && detail == QLatin1String("Open the Trainz Launcher first")) {
                for (int j = i + 1; j < total; ++j) {
                    QVariantMap rest = rows[j].toMap();
                    rest[QStringLiteral("state")] = QStringLiteral("Stopped");
                    rows[j] = rest;
                }
                step(detail, (i + 1) * 100 / total, false);
                return;
            }
        }
        QString summary = QStringLiteral("%1 · %2 done").arg(label).arg(total - failed);
        if (failed) summary += QStringLiteral(" · %1 failed").arg(failed);
        step(summary, 100, false);
    });
}

void TrainzUtilBridge::openForEditing() { run_action(QStringLiteral("edit"), QStringLiteral("Open for editing")); }
void TrainzUtilBridge::submitEdit() { run_action(QStringLiteral("commit"), QStringLiteral("Submit edit")); }
void TrainzUtilBridge::validateAssets() { run_action(QStringLiteral("validate"), QStringLiteral("Validate")); }

void TrainzUtilBridge::inspect(const QString& kind) {
    QStringList kuids = library_->selected_kuids();
    if (kuids.isEmpty()) {
        note(QStringLiteral("Select at least one asset"));
        return;
    }
    if (!ready()) return;
    if (kuids.size() > 30) {
        kuids = kuids.mid(0, 30);
        note(QStringLiteral("Showing the first 30 selected"));
    }
    QHash<QString, QString> names;
    for (const QString& kuid : kuids) names.insert(kuid, library_->name_for(kuid));
    const QString exe = util_path_;
    report_text_ = QStringLiteral("Reading…");
    emit changed();
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, kind, kuids, names] {
        QStringList chunks;
        for (const QString& kuid : kuids) {
            const QStringList cmd = kind == QLatin1String("validate") ? QStringList{QStringLiteral("validate"), kuid}
                : kind == QLatin1String("dependencies") ? QStringList{QStringLiteral("list-dependencies"), QStringLiteral("direct"), kuid}
                                                        : QStringList{QStringLiteral("status"), kuid};
            const QString raw = run_tu(exe, cmd, 90000);
            if (blocked(raw)) {
                chunks << QStringLiteral("Open the Trainz Launcher first");
                break;
            }
            QString body = tidy_trainzutil(raw);
            if (kind == QLatin1String("status")) {
                const QString credits = config_credits(run_tu(exe, {QStringLiteral("printconfig"), kuid}, 40000));
                post([self, kuid, credits] {
                    if (self && !credits.isEmpty()) self->library_->set_credits(kuid, credits);
                });
                const QString errors = tidy_trainzutil(run_tu(exe, {QStringLiteral("validate"), kuid}, 90000));
                QStringList head;
                if (!credits.isEmpty()) head << credits;
                head << decode_status(raw);
                body = head.join(QStringLiteral(" · "));
                if (!errors.isEmpty()) body += QLatin1Char('\n') + errors;
            }
            chunks << names.value(kuid) + QStringLiteral("  ") + kuid + QLatin1Char('\n') + body;
        }
        const QString text = chunks.join(QStringLiteral("\n\n"));
        post([self, text] {
            if (!self) return;
            self->report_text_ = text;
            emit self->changed();
        });
    });
}

void TrainzUtilBridge::inspectStatus() { inspect(QStringLiteral("status")); }
void TrainzUtilBridge::inspectErrors() { inspect(QStringLiteral("validate")); }
void TrainzUtilBridge::inspectDepends() { inspect(QStringLiteral("dependencies")); }

void TrainzUtilBridge::measurePacked() {
    const QStringList kuids = library_->selected_kuids();
    if (kuids.isEmpty()) {
        note(QStringLiteral("Select at least one asset"));
        return;
    }
    if (!ready()) return;
    QHash<QString, QString> names;
    for (const QString& kuid : kuids) names.insert(kuid, library_->name_for(kuid));
    const QString exe = util_path_;
    note(QStringLiteral("Measuring packed size…"));
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, kuids, names] {
        QTemporaryDir folder;
        QStringList lines;
        QHash<QString, QString> sizes;
        if (kuids.size() > 15) {
            const QString dest = folder.filePath(QStringLiteral("selection.cdp"));
            const QString raw = create_cdp(exe, dest, kuids);
            lines << tidy_trainzutil(raw) << QStringLiteral("Packed size of %1 assets: %2").arg(kuids.size()).arg(format_bytes(QFileInfo(dest).size()));
        } else {
            qint64 total = 0;
            for (const QString& kuid : kuids) {
                const QString dest = folder.filePath(QStringLiteral("one.cdp"));
                QFile::remove(dest);
                const QString raw = create_cdp(exe, dest, {kuid});
                if (blocked(raw)) {
                    lines << QStringLiteral("Open the Trainz Launcher first");
                    break;
                }
                const qint64 size = QFileInfo(dest).size();
                total += size;
                sizes.insert(kuid, format_bytes(size));
                lines << names.value(kuid) + QStringLiteral("  ") + format_bytes(size);
            }
            lines << QStringLiteral("Total packed ") + format_bytes(total);
        }
        const QString text = lines.join(QLatin1Char('\n'));
        post([self, sizes, text] {
            if (!self) return;
            for (auto it = sizes.begin(); it != sizes.end(); ++it) self->library_->set_size(it.key(), it.value());
            self->report(text);
        });
    });
}

void TrainzUtilBridge::export_selected(bool separate) {
    if (task_busy_) {
        note(QStringLiteral("Wait for the current task"));
        return;
    }
    const QStringList kuids = library_->selected_kuids();
    if (kuids.isEmpty()) {
        note(QStringLiteral("Select at least one asset"));
        return;
    }
    if (!ready()) return;
    QString dest;
    if (separate) {
        dest = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Folder for one CDP per asset"), QDir::homePath());
    } else {
        dest = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Export CDP"), QDir::home().filePath(QStringLiteral("selection.cdp")), QStringLiteral("Content package (*.cdp)"));
        if (!dest.isEmpty() && !dest.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive)) dest = QFileInfo(dest).path() + QLatin1Char('/') + QFileInfo(dest).completeBaseName() + QStringLiteral(".cdp");
    }
    if (dest.isEmpty()) return;
    QHash<QString, QString> names;
    for (const QString& kuid : kuids) names.insert(kuid, library_->name_for(kuid));
    const QString label = separate ? QStringLiteral("Each CDP") : QStringLiteral("Export");
    const int gen = ++task_gen_;
    task_busy_ = true;
    QVariantList rows;
    if (separate) {
        for (const QString& kuid : kuids) {
            rows << QVariantMap{
                {QStringLiteral("taskId"), QStringLiteral("cdp:") + kuid},
                {QStringLiteral("kuid"), kuid},
                {QStringLiteral("name"), names.value(kuid)},
                {QStringLiteral("action"), label},
                {QStringLiteral("state"), QStringLiteral("Queued")},
                {QStringLiteral("detail"), QStringLiteral("Queued")},
                {QStringLiteral("log"), QStringLiteral("Queued")},
                {QStringLiteral("percent"), 0},
            };
        }
    } else {
        rows << QVariantMap{
            {QStringLiteral("taskId"), QStringLiteral("cdp:one")},
            {QStringLiteral("name"), QFileInfo(dest).fileName()},
            {QStringLiteral("action"), label},
            {QStringLiteral("state"), QStringLiteral("Queued")},
            {QStringLiteral("detail"), QStringLiteral("%1 assets").arg(kuids.size())},
            {QStringLiteral("log"), QStringLiteral("Queued")},
            {QStringLiteral("percent"), 0},
        };
    }
    batch_rows_ = rows;
    task_summary_ = QStringLiteral("%1 · 0 of %2").arg(label).arg(rows.size());
    task_percent_ = 0;
    publish_tasks();
    const QString exe = util_path_;
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, kuids, names, separate, dest, gen, label, rows]() mutable {
        auto step = [&](const QString& summary, int percent, bool busy) {
            post([self, gen, rows, summary, percent, busy] {
                if (!self || gen != self->task_gen_) return;
                self->task_busy_ = busy;
                self->batch_rows_ = rows;
                self->task_summary_ = summary;
                self->task_percent_ = std::clamp(percent, 0, 100);
                self->publish_tasks();
            });
        };
        const int total = static_cast<int>(rows.size());
        int failed = 0;
        auto mark = [&](int i, bool ok, const QString& raw, const QString& path) {
            QVariantMap row = rows[i].toMap();
            const qint64 size = QFileInfo(path).size();
            const auto [util_ok, util_detail] = task_outcome(raw);
            const bool wrote = ok && util_ok && size > 0;
            row[QStringLiteral("state")] = wrote ? QStringLiteral("Done") : QStringLiteral("Failed");
            row[QStringLiteral("percent")] = 100;
            row[QStringLiteral("log")] = raw;
            row[QStringLiteral("detail")] = wrote ? QStringLiteral("Wrote %1 (%2)").arg(QFileInfo(path).fileName(), format_bytes(size)) : util_detail;
            rows[i] = row;
            if (!wrote) ++failed;
            return wrote;
        };
        if (separate) {
            for (int i = 0; i < total; ++i) {
                QVariantMap row = rows[i].toMap();
                const QString path = dest + QLatin1Char('/') + cdp_stem(names.value(row.value(QStringLiteral("kuid")).toString()), row.value(QStringLiteral("kuid")).toString()) + QStringLiteral(".cdp");
                row[QStringLiteral("state")] = QStringLiteral("Running");
                row[QStringLiteral("percent")] = 40;
                row[QStringLiteral("detail")] = QFileInfo(path).fileName();
                rows[i] = row;
                step(QStringLiteral("%1 · %2 of %3").arg(label).arg(i + 1).arg(total), static_cast<int>((i + 0.4) / total * 100), true);
                const QString raw = create_cdp(exe, path, {row.value(QStringLiteral("kuid")).toString()});
                mark(i, !blocked(raw), raw, path);
                if (blocked(raw)) {
                    for (int j = i + 1; j < total; ++j) {
                        QVariantMap rest = rows[j].toMap();
                        rest[QStringLiteral("state")] = QStringLiteral("Stopped");
                        rows[j] = rest;
                    }
                    step(QStringLiteral("Open the Trainz Launcher first"), (i + 1) * 100 / total, false);
                    return;
                }
            }
        } else {
            QVariantMap row = rows[0].toMap();
            row[QStringLiteral("state")] = QStringLiteral("Running");
            row[QStringLiteral("percent")] = 40;
            row[QStringLiteral("detail")] = QStringLiteral("createCDP × %1").arg(kuids.size());
            rows[0] = row;
            step(QStringLiteral("%1 · 1 of 1").arg(label), 40, true);
            const QString raw = create_cdp(exe, dest, kuids);
            mark(0, !blocked(raw), raw, dest);
        }
        QString summary = QStringLiteral("%1 · %2 done").arg(label).arg(total - failed);
        if (failed) summary += QStringLiteral(" · %1 failed").arg(failed);
        step(summary, 100, false);
        post([self, summary] {
            if (!self) return;
            self->report(summary);
            post_status(summary);
        });
    });
}

void TrainzUtilBridge::exportTogether() { export_selected(false); }
void TrainzUtilBridge::exportEach() { export_selected(true); }

void TrainzUtilBridge::openEngine(const QString& kuid) {
    const QString chosen = kuid.trimmed().isEmpty() ? library_->tuner_kuid() : kuid.trimmed();
    if (chosen.isEmpty()) {
        note(QStringLiteral("Select an engine spec"));
        return;
    }
    if (!ready()) return;
    const QString flags = library_->flags_for(chosen);
    const QString name = library_->name_for(chosen);
    const QString editing = data_dir_.isEmpty() ? QString() : data_dir_ + QStringLiteral("/editing");
    const QString exe = util_path_;
    note(QStringLiteral("Opening engine spec…"));
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, chosen, flags, name, editing] {
        QString text;
        if (flags.contains(QLatin1Char('E')) && !editing.isEmpty()) {
            const QString path = config_in_editing(editing, chosen);
            if (!path.isEmpty()) text = QString::fromUtf8(read_bytes(path));
        }
        QString fail;
        if (!looks_like_enginespec(text.toStdString())) {
            const QString raw = run_tu(exe, {QStringLiteral("printconfig"), chosen}, 60000);
            if (blocked(raw)) fail = QStringLiteral("Open the Trainz Launcher first");
            else text = tidy_trainzutil(raw);
        }
        if (fail.isEmpty() && !looks_like_enginespec(text.toStdString())) fail = name + QStringLiteral(" is not an engine spec");
        post([self, chosen, text, name, fail] {
            if (!self) return;
            if (!fail.isEmpty()) {
                self->note(fail);
                return;
            }
            emit self->engineRequested(chosen, text, name);
        });
    });
}

void TrainzUtilBridge::previewAsset(const QString& kuid) {
    QString chosen = kuid.trimmed();
    if (chosen.isEmpty()) chosen = detail_kuid_;
    if (chosen.isEmpty()) chosen = library_->selected_kuids().value(0);
    if (chosen.isEmpty()) {
        note(QStringLiteral("Select an asset to preview"));
        return;
    }
    const std::shared_ptr<const ContentIndex> index = index_;
    if (!index) {
        note(QStringLiteral("Scan the library first"));
        return;
    }
    if (preview_pct_ >= 0) return;  // one preview at a time
    preview_pct_ = 0;
    report_text_ = QStringLiteral("Reading ") + chosen;
    emit changed();
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, chosen, index] {
        const IndexSource source = index_source(*index);
        const QList<PreviewNode> nodes = resolve_preview(chosen, source.read_config, source.locate, 8, 400, [self](const QString& stage, int pct) {
            post([self, stage, pct] {
                if (!self || self->preview_pct_ < 0) return;
                self->preview_pct_ = qMax(self->preview_pct_, qMin(pct, 95));  // never steps back as the tree grows
                self->report_text_ = stage;
                emit self->changed();
            });
        });
        const QString text = preview_text(nodes) + QStringLiteral("\n\nSending %1 meshes to Mesh Studio").arg(preview_scene(nodes).paths.size());
        const PreviewScene scene = preview_scene(nodes);
        post([self, text, scene] {
            if (!self) return;
            self->preview_pct_ = -1;
            self->report_text_ = text;
            emit self->changed();
            if (!scene.paths.isEmpty()) emit self->sceneRequested(scene.paths, scene.labels, scene.yaws);
        });
    });
}

void TrainzUtilBridge::commit_enginespec(const QString& kuid, const QString& text) {
    if (!ready()) return;
    const QString exe = util_path_;
    const QString data = data_dir_;
    note(QStringLiteral("Saving the engine spec into Trainz…"));
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, exe, data, kuid, text] {
        QString result;
        const QString opened = run_tu(exe, {QStringLiteral("edit"), kuid}, 120000);
        const QString path = data.isEmpty() ? QString() : config_in_editing(data + QStringLiteral("/editing"), kuid);
        if (blocked(opened)) {
            result = QStringLiteral("Open the Trainz Launcher first");
        } else if (path.isEmpty()) {
            result = tidy_trainzutil(opened);
            if (result.isEmpty()) result = QStringLiteral("Trainz did not open an editing folder for this asset");
        } else {
            QString body = text;
            if (!body.endsWith(QLatin1Char('\n'))) body += QLatin1Char('\n');
            write_bytes(path, body.toUtf8());
            const QString committed = tidy_trainzutil(run_tu(exe, {QStringLiteral("commit"), kuid}, 180000));
            const QString low = committed.toLower();
            result = low.contains(QLatin1String("error")) && !low.contains(QLatin1String("0 errors"))
                ? (committed.isEmpty() ? QStringLiteral("Commit failed") : committed)
                : QStringLiteral("บันทึกเข้าเกมแล้ว — ") + kuid;
        }
        post([self, result] {
            if (self) self->report(result);
        });
    });
}

void TrainzUtilBridge::editConfig() {
    const QString kuid = (focus_kuid_.isEmpty() ? detail_kuid_ : focus_kuid_).trimmed();
    if (kuid.isEmpty() || !index_) {
        note(index_ ? QStringLiteral("Select an asset first") : QStringLiteral("Content folders are still being read"));
        return;
    }
    QString path;
    const QString folder = index_->editing_folder.value(kuid);
    if (!folder.isEmpty()) {
        const QString file_path = folder + QStringLiteral("/config.txt");
        QFile file(file_path);
        if (file.open(QIODevice::ReadOnly)) {
            emit configRequested(QString::fromUtf8(file.readAll()), file_path);
            return;
        }
    }
    const QString text = index_source(*index_).read_config(kuid);
    if (text.isEmpty()) {
        note(QStringLiteral("No config.txt for this asset"));
        return;
    }
    emit configRequested(text, QString());
}

void TrainzUtilBridge::openPackages() {
    const QString kuid = (focus_kuid_.isEmpty() ? detail_kuid_ : focus_kuid_).trimmed();
    const std::shared_ptr<const ContentIndex> index = index_;
    if (kuid.isEmpty() || !index) {
        emit packagesRequested({});
        if (!index) note(QStringLiteral("Content folders are still being read"));
        return;
    }
    QPointer<TrainzUtilBridge> self(this);
    spawn([self, kuid, index] {
        const QString folder = asset_browse_dir(*index, kuid);
        post([self, folder] {
            if (!self) return;
            if (folder.isEmpty()) self->note(QStringLiteral("No files for this asset"));
            emit self->packagesRequested(folder);
        });
    });
}

// ---- Backups

void TrainzUtilBridge::publish_backups() {
    const QString needle = backup_query_.trimmed();
    QVariantList payload;
    if (data_dir_.isEmpty()) {
        backup_summary_ = data_ready_ ? QStringLiteral("Trainz data folder was not found") : QStringLiteral("Reading the Trainz data folder…");
    } else if (!QFileInfo(data_dir_ + QStringLiteral("/backups")).isDir()) {
        backup_summary_ = QStringLiteral("No backups folder · ") + QDir::toNativeSeparators(data_dir_ + QStringLiteral("/backups"));
    } else {
        const QList<AssetBackup> rows = find_asset_backups(data_dir_, needle);
        QSet<QString> days;
        for (const AssetBackup& row : rows) {
            days.insert(row.day_key);
            QStringList detail;
            if (!row.kuid.isEmpty()) detail << row.kuid;
            if (row.size) detail << format_bytes(row.size);
            if (!row.when.isEmpty()) detail << row.when;
            payload << QVariantMap{
                {QStringLiteral("day"), row.day},
                {QStringLiteral("dayKey"), row.day_key},
                {QStringLiteral("mtime"), row.mtime},
                {QStringLiteral("title"), row.name},
                {QStringLiteral("kind"), row.kind},
                {QStringLiteral("detail"), detail.join(QStringLiteral(" · "))},
                {QStringLiteral("path"), row.path},
            };
        }
        const QString root = QDir::toNativeSeparators(data_dir_ + QStringLiteral("/backups"));
        const QString shown = rows.size() == 1 ? QStringLiteral("1 backup") : QStringLiteral("%1 backups").arg(rows.size());
        if (!rows.isEmpty()) backup_summary_ = shown + (days.isEmpty() ? QString() : QStringLiteral(" · %1 days").arg(days.size())) + QStringLiteral(" · ") + root;
        else if (!needle.isEmpty()) backup_summary_ = QStringLiteral("No backups for ") + needle;
        else backup_summary_ = QStringLiteral("No backups · ") + root;
    }
    emit backupsReady(payload);
    emit changed();
}

void TrainzUtilBridge::findBackups(const QString& query) {
    backup_query_ = query;
    if (page_ != QLatin1String("backups")) {
        showPage(QStringLiteral("backups"));
        return;
    }
    publish_backups();
}

void TrainzUtilBridge::findSelectedBackups() {
    backup_query_ = detail_kuid_;
    if (page_ != QLatin1String("backups")) {
        showPage(QStringLiteral("backups"));
        return;
    }
    publish_backups();
}

void TrainzUtilBridge::showBackup(const QString& path) {
    if (!QFileInfo::exists(path)) {
        note(QStringLiteral("That backup is no longer there"));
        return;
    }
    const QHash<QString, QString> info = describe_backup(path);
    backup_pick_ = path;
    QVariantMap card;
    for (auto it = info.begin(); it != info.end(); ++it) card.insert(it.key(), it.value());
    set_detail(card, {info.value(QStringLiteral("status")), info.value(QStringLiteral("installed"))});
}

void TrainzUtilBridge::openBackup(const QString& path) {
    const QFileInfo info(path);
    if (!info.exists()) {
        note(QStringLiteral("That backup is no longer there"));
        return;
    }
    if (info.isDir()) {
        QDesktopServices::openUrl(QUrl::fromLocalFile(path));
        return;
    }
#ifdef Q_OS_WIN
    QProcess::startDetached(QStringLiteral("explorer"), {QStringLiteral("/select,") + QDir::toNativeSeparators(path)});
#else
    QDesktopServices::openUrl(QUrl::fromLocalFile(info.path()));
#endif
}

// ---- Plumbing

void TrainzUtilBridge::publish_sources() {
    QVariantList rows;
    for (const Source& source : sources_) {
        const qint64 bytes = QFileInfo(source.path).size();
        rows.push_back(QVariantMap{
            {QStringLiteral("sourceId"), source.id},
            {QStringLiteral("name"), source.name},
            {QStringLiteral("kind"), source.kind},
            {QStringLiteral("size"), bytes > 0 ? format_bytes(bytes) : QString()},
            {QStringLiteral("status"), source.status},
            {QStringLiteral("percent"), source.percent},
            {QStringLiteral("checked"), source.checked},
        });
    }
    emit sourcesReady(rows);
}

TrainzUtilBridge::~TrainzUtilBridge() { stop_scan(); }

void TrainzUtilBridge::stop_scan() {
    if (scan_state_) scan_state_->alive.store(false);
    const qint64 pid = scan_state_ ? scan_state_->pid.load() : 0;
#ifdef Q_OS_WIN
    if (pid > 0) {
        HANDLE handle = OpenProcess(PROCESS_TERMINATE, FALSE, static_cast<DWORD>(pid));
        if (handle) {
            TerminateProcess(handle, 1);
            CloseHandle(handle);
        }
    }
#else
    Q_UNUSED(pid);
#endif
    if (scan_thread_) {
        scan_thread_->wait(3000);
        scan_thread_->deleteLater();
        scan_thread_ = nullptr;
    }
}

void TrainzUtilBridge::open_data_folder() {
    QDesktopServices::openUrl(QUrl::fromLocalFile(data_dir_));
}

void TrainzUtilBridge::on_data_folder(const QString& folder) {
    const bool fresh = !folder.isEmpty() && QFileInfo(folder).isDir();
    if (fresh) data_dir_ = folder;
    data_ready_ = true;
    if (fresh || !index_) scan_content();
    if (page_ == QLatin1String("backups")) publish_backups();
    if (!want_data_) return;
    want_data_ = false;
    if (QFileInfo(data_dir_).isDir()) {
        open_data_folder();
        return;
    }
    library_summary_ = QStringLiteral("Trainz data folder was not found");
    emit changed();
}

void TrainzUtilBridge::on_library_scan(bool ok, const QString& launcher_text, const QList<LibraryAsset>& rows) {
    scanning_ = false;
    fill_library_ = false;
    launcher_ok_ = ok;
    launcher_text_ = launcher_text;
    if (ok) {
        library_->replace(rows);
        note_library();
        const int faulty = static_cast<int>(std::count_if(rows.begin(), rows.end(), [](const LibraryAsset& r) { return r.faulty; }));
        publish_load(ui_tr(QStringLiteral("%1 installed · %2 faulty.%3")).arg(rows.size()).arg(faulty)
                         .arg(fill_dates_ || fill_meta_ ? ui_tr(QStringLiteral(" Dates, sizes, and author names are still loading from the content folders.")) : QString()));
    } else {
        if (library_->count() == 0) library_summary_ = launcher_text;
        else note_library();
        status_text_ = launcher_text;
        publish_load(launcher_text);
    }
    if (want_data_) {
        want_data_ = false;
        if (QFileInfo(data_dir_).isDir()) open_data_folder();
        else library_summary_ = QStringLiteral("Trainz data folder was not found");
    }
    if (scan_thread_ && scan_thread_->isFinished()) {
        scan_thread_->deleteLater();
        scan_thread_ = nullptr;
    }
    emit changed();
}

// ---------------------------------------------------------------- Page

TrainzUtilPage::TrainzUtilPage(QWidget* parent, bool start_probe) : QWidget(parent) {
    load_material_icons();
    library_ = new LibraryList(this);
    queue_ = new InstallQueue(this);
    bridge_ = new TrainzUtilBridge(library_, queue_, this);
    connect(bridge_, &TrainzUtilBridge::homeRequested, this, &TrainzUtilPage::homeRequested);
    connect(bridge_, &TrainzUtilBridge::engineRequested, this, &TrainzUtilPage::engineRequested);
    connect(bridge_, &TrainzUtilBridge::sceneRequested, this, &TrainzUtilPage::sceneRequested);
    connect(bridge_, &TrainzUtilBridge::packagesRequested, this, &TrainzUtilPage::packagesRequested);
    connect(bridge_, &TrainzUtilBridge::configRequested, this, &TrainzUtilPage::configRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setSource(res_url(qml_file()));
    if (start_probe) bridge_->refreshLauncher();
}

QString TrainzUtilPage::choose_kuid(const QString& filter) {
    QWidget* host = window();
    QDialog dialog(host);
    dialog.setWindowFlag(Qt::Window, true);
    dialog.setWindowModality(Qt::ApplicationModal);
    dialog.setWindowTitle(QStringLiteral("Choose asset"));
    dialog.resize(520, 560);
    auto* layout = new QVBoxLayout(&dialog);
    auto* hint = new QLabel(&dialog);
    hint->setWordWrap(true);
    auto* search = new QLineEdit(&dialog);
    search->setPlaceholderText(QStringLiteral("Name or KUID"));
    auto* list = new QListWidget(&dialog);
    layout->addWidget(hint);
    layout->addWidget(search);
    layout->addWidget(list, 1);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dialog);
    layout->addWidget(buttons);
    QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    QObject::connect(list, &QListWidget::itemDoubleClicked, &dialog, &QDialog::accept);
    const QStringList codes = filter.split(QLatin1Char(','), Qt::SkipEmptyParts);
    auto refill = [this, codes, hint, search, list] {
        list->clear();
        static const QList<LibraryAsset> kEmpty;
        const QList<LibraryAsset>& rows = library_ == nullptr ? kEmpty : library_->all();
        const bool loading = bridge_ && bridge_->busy() && rows.isEmpty();
        hint->setText(rows.isEmpty()
                          ? (loading ? QStringLiteral("Reading Content Manager. The list fills when TrainzUtil answers.")
                                     : QStringLiteral("The library is empty. Open the Trainz Launcher with Advanced debug tools, then refresh TrainzUtil."))
                          : QStringLiteral("Installed assets. The list starts on the kind this tag expects."));
        const QString needle = search->text().trimmed();
        int shown = 0;
        for (const LibraryAsset& asset : rows) {
            if (!codes.isEmpty()) {
                bool match = false;
                for (const QString& code : codes)
                    if (asset.category.compare(code.trimmed(), Qt::CaseInsensitive) == 0) match = true;
                if (!match && needle.isEmpty()) continue;
            }
            if (!needle.isEmpty() && !asset.name.contains(needle, Qt::CaseInsensitive) && !asset.kuid.contains(needle, Qt::CaseInsensitive)) continue;
            auto* item = new QListWidgetItem(asset.name + QStringLiteral("    ") + asset.kuid, list);
            item->setData(Qt::UserRole, asset.kuid);
            if (++shown >= 400) break;
        }
    };
    refill();
    int loaded = library_ == nullptr ? 0 : library_->total();
    if (bridge_) {
        QObject::connect(bridge_, &TrainzUtilBridge::changed, &dialog, [this, refill, loaded]() mutable {
            const int now = library_ == nullptr ? 0 : library_->total();
            if (now == loaded && now > 0) return;
            loaded = now;
            refill();
        });
    }
    QObject::connect(search, &QLineEdit::textChanged, &dialog, refill);
    if (dialog.exec() != QDialog::Accepted || list->currentItem() == nullptr) return {};
    return list->currentItem()->data(Qt::UserRole).toString();
}

void TrainzUtilPage::open_archive(const QString& path) {
    library_->add(asset_from_tzarc(path));
    bridge_->note_library();
}

void TrainzUtilPage::commit_enginespec(const QString& kuid, const QString& text) { bridge_->commit_enginespec(kuid, text); }

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
