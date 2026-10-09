#include "trainz_meta.h"

#include "io/chump.h"
#include "io/config_id.h"
#include "io/tzarc.h"

#include <algorithm>
#include <atomic>
#include <thread>
#include <vector>

#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSet>
#include <QVariantMap>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {

const QSet<QString>& generic_categories() {
    static const QSet<QString> set = {QStringLiteral("SY"), QStringLiteral("SCEN"), QStringLiteral("TR"), QStringLiteral("TV"), QStringLiteral("CMP")};
    return set;
}

const QHash<QString, QString>& category_names() {
    static const QHash<QString, QString> map = [] {
        const char* pairs[][2] = {
            {"?ENV", "Environment"}, {"?EW", "Water"}, {"?WA", "Signal"}, {"?WM", "Trackmark"}, {"?WS", "Sign"},
            {"?WT", "Trigger"}, {"?WX", "Junction"}, {"#CCARLIB", "Library"}, {"#CCARSCENERY", "Scenery"},
            {"#CCARVEHICLE", "Vehicle"}, {"#ENGINESPEC", "Engine Spec"}, {"#FXCLT", "Clutter"}, {"#HOUSES", "Houses"},
            {"ACC", "Roadside"}, {"ACHC", "Achievement Category"}, {"ACHG", "Achievement Group"}, {"ACT", "Activity"},
            {"ACTV", "Active"}, {"AGRP", "Asset Group"}, {"AIR", "Aircraft"}, {"ANTX", "Livestock"}, {"AQUA", "Water"},
            {"AU", "Australia"}, {"BD", "Building"}, {"BDB", "Buildable"}, {"BKL", "Bulk"}, {"BLD", "Building"},
            {"BOG", "Bogey"}, {"BOGEY", "Bogey"}, {"BOGY", "Bogey"}, {"BR", "Bridge"}, {"BRDG", "Bridge"},
            {"BRG", "Bridge"}, {"BRIDGE", "Bridge"}, {"BRSH", "Ground Brush"}, {"CA", "Canada"}, {"CAB", "Caboose"},
            {"CLUT", "Clutter"}, {"CMP", "Component"}, {"CN", "Consist"}, {"COM", "Commercial"}, {"CON", "Container"},
            {"CONT", "Container"}, {"CROS", "Crossing"}, {"CS", "Control Set"}, {"CY", "Commodity"}, {"DE", "Germany"},
            {"DIES", "Diesel"}, {"DR", "Driver"}, {"ELEC", "Electric"}, {"ENG", "Engine"}, {"ENV", "Environment"},
            {"ESND", "Engine Sound"}, {"ESPC", "Engine Spec"}, {"EU", "Europe"}, {"FA", "Fauna"}, {"FIXD", "Fixed Track"},
            {"FL", "Flora"}, {"FLAT", "Flatcar"}, {"FNC", "Fence"}, {"FR", "France"}, {"FRT", "Freight"},
            {"FXP", "Effect"}, {"GEN", "General"}, {"GMNU", "Gameplay Menu"}, {"GRND", "Ground"}, {"GRSS", "Grass"},
            {"HOPP", "Hopper"}, {"HORN", "Horn"}, {"HT", "HTML"}, {"IND", "Industry"}, {"INDS", "Industry"},
            {"INT", "Interior"}, {"INTR", "Interior"}, {"IT", "Interlocking Tower"}, {"JP", "Japan"}, {"KR", "Korea"},
            {"LIQ", "Liquid"}, {"LND", "Land"}, {"LOC", "Locomotive"}, {"LOCO", "Locomotive"}, {"MAIL", "Mail"},
            {"MESH", "Mesh"}, {"MNT", "Maintenance"}, {"MOBJ", "Mesh Object"}, {"NACT", "Inactive"}, {"NEV", "General"},
            {"NL", "Netherlands"}, {"NZ", "New Zealand"}, {"OTHR", "Other"}, {"PANT", "Pantograph"}, {"PASS", "Passenger"},
            {"PAX", "Passenger"}, {"PL", "Poland"}, {"PP", "People"}, {"PRDC", "Product Category"}, {"PROD", "Product"},
            {"PWAY", "Permanent Way"}, {"PWL", "Power Line"}, {"RACK", "Rack"}, {"RCR", "Railcar"}, {"RD", "Road"},
            {"REEF", "Refrigerator"}, {"REGN", "Region"}, {"RES", "Residential"}, {"RLS", "Rails"}, {"ROAD", "Road"},
            {"ROLL", "Rolling Stock"}, {"RRD", "Railroad"}, {"RT", "Route"}, {"RU", "Rule"}, {"SCEN", "Scenery"},
            {"SCRP", "Script"}, {"SD", "Sound"}, {"SEA", "Sea"}, {"SEAT", "Coach"}, {"SIG", "Signal"}, {"SIGN", "Signal"},
            {"SIN", "Sign"}, {"SKYS", "Sky"}, {"SLIB", "Script Library"}, {"SND", "Sound"}, {"SNDS", "Sound Set"},
            {"SPC", "Special"}, {"SPLN", "Spline"}, {"SQ", "Script"}, {"SS", "Session"}, {"STA", "Station"},
            {"STEA", "Steam"}, {"STEAM", "Steam"}, {"STEM", "Steam"}, {"SVLT", "Servlet"}, {"SWT", "Scenery with Track"},
            {"SY", "Scenery"}, {"TANK", "Tank"}, {"TCB", "Track Circuit"}, {"TDR", "Tender"}, {"TEND", "Tender"},
            {"TEX", "Texture"}, {"TH", "Thailand"}, {"TK", "Track"}, {"TNIC", "Controller"}, {"TNIP", "Plugin"},
            {"TNIR", "Resource"}, {"TO", "Trackside"}, {"TR", "Train"}, {"TRACK", "Track"}, {"TRCK", "Track"},
            {"TSND", "Track Sound"}, {"TUN", "Tunnel"}, {"TUNL", "Tunnel"}, {"TUNNEL", "Tunnel"}, {"TURF", "Turf"},
            {"TURN", "Turntable"}, {"TUT", "Tutorial"}, {"TV", "Train Vehicle"}, {"TX", "Texture"},
            {"TXGRP", "Texture Group"}, {"UK", "United Kingdom"}, {"US", "United States"}, {"UTL", "Utility"},
            {"VE", "Vehicle"}, {"VEH", "Vehicle"}, {"VEHC", "Vehicle"}, {"WAYP", "Waypoint"}, {"WW", "Worldwide"},
        };
        QHash<QString, QString> out;
        for (const auto& pair : pairs) out.insert(QLatin1String(pair[0]), QLatin1String(pair[1]));
        return out;
    }();
    return map;
}

QString category_name(const QString& token) {
    const QString key = token.toUpper();
    const QString name = category_names().value(key);
    if (!name.isEmpty()) return name;
    if (key.startsWith(QLatin1Char('#'))) return category_names().value(key.mid(1), token.mid(1));
    return token;
}

QString after_null(const QString& line) {
    static const QRegularExpression re(QStringLiteral(R"(<NULL>\s*:)"));
    const QRegularExpressionMatch m = re.match(line);
    return m.hasMatch() ? line.mid(m.capturedEnd()) : line;
}

QString strip_quotes(QString text) {
    text = text.trimmed();
    while (text.startsWith(QLatin1Char('"'))) text.remove(0, 1);
    while (text.endsWith(QLatin1Char('"'))) text.chop(1);
    return text;
}

QByteArray read_all(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    return file.readAll();
}

std::vector<uint8_t> tzarc_config(const QString& path) {
    const QByteArray bytes = read_all(path);
    if (bytes.isEmpty()) return {};
    try {
        return read_tzarc_config(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
    } catch (const std::exception&) {
        return {};
    }
}

struct DirEntry {
    QString name;
    bool dir = false;
    qint64 mtime_ns = 0;
    qint64 size = 0;
};

std::vector<DirEntry> list_dir(const QString& folder) {
    std::vector<DirEntry> out;
#ifdef Q_OS_WIN
    const std::wstring pattern = QDir::toNativeSeparators(folder + QStringLiteral("/*")).toStdWString();
    WIN32_FIND_DATAW fd;
    HANDLE handle = FindFirstFileExW(pattern.c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, nullptr, FIND_FIRST_EX_LARGE_FETCH);
    if (handle == INVALID_HANDLE_VALUE) return out;
    do {
        DirEntry entry;
        entry.name = QString::fromWCharArray(fd.cFileName);
        if (entry.name == QLatin1String(".") || entry.name == QLatin1String("..")) continue;
        entry.dir = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
        if (entry.dir && (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) continue;
        const qint64 ticks = (static_cast<qint64>(fd.ftLastWriteTime.dwHighDateTime) << 32) | fd.ftLastWriteTime.dwLowDateTime;
        entry.mtime_ns = (ticks - 116444736000000000LL) * 100;
        entry.size = (static_cast<qint64>(fd.nFileSizeHigh) << 32) | fd.nFileSizeLow;
        out.push_back(std::move(entry));
    } while (FindNextFileW(handle, &fd));
    FindClose(handle);
#else
    for (const QFileInfo& info : QDir(folder).entryInfoList(QDir::Files | QDir::Dirs | QDir::NoDotAndDotDot | QDir::NoSymLinks)) {
        DirEntry entry;
        entry.name = info.fileName();
        entry.dir = info.isDir();
        entry.mtime_ns = info.lastModified().toMSecsSinceEpoch() * 1000000LL;
        entry.size = info.size();
        out.push_back(std::move(entry));
    }
#endif
    return out;
}

template <class T, class F>
std::vector<T> parallel_map(const QStringList& items, F fn) {
    std::vector<T> out(static_cast<size_t>(items.size()));
    std::atomic<int> next{0};
    const int cores = std::max(1, static_cast<int>(std::thread::hardware_concurrency()));
    const int workers = std::min(cores, static_cast<int>(items.size()));
    auto run = [&] {
        for (int i = next++; i < items.size(); i = next++) out[static_cast<size_t>(i)] = fn(items[i]);
    };
    if (workers <= 1) {
        run();
        return out;
    }
    std::vector<std::thread> pool;
    for (int i = 0; i < workers; ++i) pool.emplace_back(run);
    for (std::thread& thread : pool) thread.join();
    return out;
}

QHash<QString, ArchiveHit> scan_archive_folder(const QString& folder) {
    QStringList buckets;
    for (const DirEntry& entry : list_dir(folder)) {
        if (entry.dir) buckets << folder + QLatin1Char('/') + entry.name;
    }
    const auto parts = parallel_map<QHash<QString, ArchiveHit>>(buckets, [](const QString& bucket) {
        QHash<QString, ArchiveHit> found;
        for (const DirEntry& entry : list_dir(bucket)) {
            if (entry.dir || !entry.name.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) continue;
            const QString kuid = kuid_from_archive_name(entry.name);
            if (kuid.isEmpty()) continue;
            found.insert(kuid, {bucket + QLatin1Char('/') + entry.name, entry.mtime_ns, entry.size});
        }
        return found;
    });
    QHash<QString, ArchiveHit> out;
    for (const auto& part : parts) out.insert(part);
    return out;
}

QString own_kuid(const QString& config_path) {
    static const QRegularExpression re(QStringLiteral(R"((?im)^\s*kuid\s+(<kuid2?:-?\d+:-?\d+(?::-?\d+)?>))"));
    const QRegularExpressionMatch m = re.match(QString::fromUtf8(read_all(config_path)));
    return m.hasMatch() ? m.captured(1) : QString();
}

QString safe_name(const QString& kuid) {
    QString safe = kuid;
    safe.replace(QRegularExpression(QStringLiteral("[^0-9A-Za-z]+")), QStringLiteral("_"));
    while (safe.startsWith(QLatin1Char('_'))) safe.remove(0, 1);
    while (safe.endsWith(QLatin1Char('_'))) safe.chop(1);
    return safe.isEmpty() ? QStringLiteral("asset") : safe;
}

QString cache_dir(const QString& leaf) {
    const QString dir = QDir::homePath() + QStringLiteral("/.cache/trainz_studio/") + leaf;
    QDir().mkpath(dir);
    return dir;
}

QString archive_key(const QString& archive) {
    const QFileInfo info(archive);
    return archive + QLatin1Char(':') + QString::number(info.lastModified().toSecsSinceEpoch()) + QLatin1Char(':') + QString::number(info.size());
}

const QStringList& cover_defaults() {
    static const QStringList names = {
        QStringLiteral("$screenshot$.jpg"), QStringLiteral("$screenshot$.jpeg"), QStringLiteral("$screenshot$.png"),
        QStringLiteral("thumbnail.jpg"), QStringLiteral("thumbnail.jpeg"), QStringLiteral("thumbnail.png"),
        QStringLiteral("thumb.jpg"), QStringLiteral("thumb.png"), QStringLiteral("screenshot.jpg"), QStringLiteral("preview.jpg"),
    };
    return names;
}

bool image_suffix(const QString& name) {
    static const QStringList suffixes = {QStringLiteral("jpg"), QStringLiteral("jpeg"), QStringLiteral("png"), QStringLiteral("tga"), QStringLiteral("bmp"), QStringLiteral("webp")};
    return suffixes.contains(QFileInfo(name).suffix().toLower());
}

QStringList thumbnail_names(const std::vector<uint8_t>& raw) {
    QStringList names;
    if (raw.size() >= 4 && std::equal(raw.begin(), raw.begin() + 4, "ACS$")) {
        try {
            const ChumpFile file = read_chump(raw.data(), raw.size());
            for (const ChumpTag& tag : file.root) {
                if (tag.type != ChumpType::Soup || QString::fromStdString(tag.name).compare(QLatin1String("thumbnails"), Qt::CaseInsensitive) != 0) continue;
                for (const ChumpTag& inner : tag.children) {
                    if (inner.type == ChumpType::Soup) {
                        for (const ChumpTag& leaf : inner.children) {
                            if (leaf.type == ChumpType::Text && QString::fromStdString(leaf.name).compare(QLatin1String("image"), Qt::CaseInsensitive) == 0 && !leaf.text.empty())
                                names << strip_quotes(QString::fromStdString(leaf.text));
                        }
                    } else if (inner.type == ChumpType::Text && QString::fromStdString(inner.name).compare(QLatin1String("image"), Qt::CaseInsensitive) == 0 && !inner.text.empty()) {
                        names << strip_quotes(QString::fromStdString(inner.text));
                    }
                }
            }
        } catch (const std::exception&) {
        }
        return names;
    }
    const QString text = QString::fromUtf8(reinterpret_cast<const char*>(raw.data()), static_cast<qsizetype>(raw.size()));
    static const QRegularExpression start(QStringLiteral(R"((?im)^\s*thumbnails\s*\{)"));
    const QRegularExpressionMatch m = start.match(text);
    if (!m.hasMatch()) return names;
    int depth = 0;
    int end = m.capturedEnd() - 1;
    for (; end < text.size(); ++end) {
        if (text[end] == QLatin1Char('{')) ++depth;
        else if (text[end] == QLatin1Char('}') && --depth == 0) break;
    }
    const QString body = text.mid(m.capturedEnd() - 1, end - m.capturedEnd() + 2);
    static const QRegularExpression image(QStringLiteral(R"re((?im)\bimage\s+"([^"]+)")re"));
    for (auto it = image.globalMatch(body); it.hasNext();) names << it.next().captured(1).trimmed();
    return names;
}

QStringList cover_names(const std::vector<uint8_t>& config) {
    QStringList ordered;
    for (const QString& name : thumbnail_names(config)) {
        if (!ordered.contains(name)) ordered << name;
        if (QFileInfo(name).suffix().compare(QLatin1String("texture"), Qt::CaseInsensitive) != 0) continue;
        const QString stem = QFileInfo(QString(name).replace(QLatin1Char('\\'), QLatin1Char('/'))).completeBaseName();
        for (const char* ext : {".jpg", ".png", ".tga"}) {
            const QString alt = stem + QLatin1String(ext);
            if (!ordered.contains(alt)) ordered << alt;
        }
    }
    for (const QString& name : cover_defaults()) {
        if (!ordered.contains(name)) ordered << name;
    }
    return ordered;
}

QString blob_suffix(const std::vector<uint8_t>& blob, const QString& hint) {
    if (blob.size() >= 2 && blob[0] == 0xFF && blob[1] == 0xD8) return QStringLiteral(".jpg");
    if (blob.size() >= 4 && blob[0] == 0x89 && blob[1] == 'P' && blob[2] == 'N' && blob[3] == 'G') return QStringLiteral(".png");
    if (blob.size() >= 4 && blob[0] == 'G' && blob[1] == 'I' && blob[2] == 'F' && blob[3] == '8') return QStringLiteral(".gif");
    const QString suffix = QFileInfo(hint).suffix().toLower();
    if (suffix == QLatin1String("jpeg")) return QStringLiteral(".jpg");
    if (image_suffix(hint)) return QLatin1Char('.') + suffix;
    return QStringLiteral(".jpg");
}

QString cover_in_folder(const QString& folder) {
    const std::vector<uint8_t> config = [&] {
        const QByteArray bytes = read_all(folder + QStringLiteral("/config.txt"));
        return std::vector<uint8_t>(bytes.begin(), bytes.end());
    }();
    QStringList wanted;
    for (const QString& name : thumbnail_names(config) + cover_defaults()) wanted << QString(name).replace(QLatin1Char('\\'), QLatin1Char('/'));
    QSet<QString> bases;
    for (const QString& name : wanted) {
        const QString direct = folder + QLatin1Char('/') + name;
        if (QFileInfo(direct).isFile()) return direct;
        bases.insert(QFileInfo(name).fileName().toLower());
    }
    QDirIterator it(folder, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext()) {
        const QString path = it.next();
        if (bases.contains(it.fileName().toLower()) && image_suffix(path)) return path;
    }
    return {};
}

const QRegularExpression& day_dir() {
    static const QRegularExpression re(QStringLiteral(R"(^(\d{2})-(\d{2})-(\d{2})$)"));
    return re;
}

QString day_label(const QString& name) {
    const QRegularExpressionMatch m = day_dir().match(name);
    if (!m.hasMatch()) return name;
    static const char* months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    const int month = m.captured(2).toInt();
    if (month < 1 || month > 12) return name;
    return QStringLiteral("%1 %2 20%3").arg(m.captured(3).toInt()).arg(QLatin1String(months[month - 1])).arg(m.captured(1));
}

QString backup_kuid(const QString& name) {
    static const QRegularExpression re(QStringLiteral(R"(^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?)"), QRegularExpression::CaseInsensitiveOption);
    const QRegularExpressionMatch m = re.match(name.trimmed());
    if (!m.hasMatch()) return {};
    if (m.captured(1).compare(QLatin1String("kuid2"), Qt::CaseInsensitive) == 0)
        return QStringLiteral("<kuid2:%1:%2:%3>").arg(m.captured(2), m.captured(3), m.captured(4).isEmpty() ? QStringLiteral("0") : m.captured(4));
    return QStringLiteral("<kuid:%1:%2>").arg(m.captured(2), m.captured(3));
}

QStringList search_tokens(const QString& text) {
    static const QRegularExpression re(QStringLiteral("[0-9A-Za-z]+"));
    QStringList out;
    for (auto it = re.globalMatch(text); it.hasNext();) {
        const QString part = it.next().captured(0).toLower();
        if (part.size() >= 2 && part != QLatin1String("kuid") && part != QLatin1String("kuid2")) out << part;
    }
    return out;
}

}  // namespace

QString category_label(const QString& code) {
    QStringList parts;
    for (const QString& part : code.split(QLatin1Char(';'))) {
        if (!part.trimmed().isEmpty()) parts << part.trimmed();
    }
    if (parts.isEmpty()) return {};
    QStringList specific;
    for (const QString& part : parts) {
        if (!generic_categories().contains(part.toUpper())) specific << part;
    }
    QStringList names;
    QSet<QString> seen;
    for (const QString& part : specific.isEmpty() ? parts : specific) {
        const QString name = category_name(part);
        if (seen.contains(name.toLower())) continue;
        seen.insert(name.toLower());
        names << name;
    }
    return names.join(QStringLiteral(" · "));
}

bool category_is_enginespec(const QString& code) {
    for (const QString& part : code.split(QLatin1Char(';'))) {
        if (part.trimmed().toUpper() == QLatin1String("ESPC")) return true;
    }
    return false;
}

QStringList status_bits(const QString& flags, bool open_for_edit, bool locally_modified) {
    QStringList bits;
    if (open_for_edit || flags.contains(QLatin1Char('E'))) bits << QStringLiteral("Edit");
    if (flags.contains(QLatin1Char('F'))) bits << QStringLiteral("Faulty");
    if (flags.contains(QLatin1Char('M'))) bits << QStringLiteral("Missing");
    if (locally_modified || flags.contains(QLatin1Char('L'))) bits << QStringLiteral("Modified");
    if (flags.contains(QLatin1Char('O'))) bits << QStringLiteral("Obsolete");
    if (flags.contains(QLatin1Char('U'))) bits << QStringLiteral("Update");
    if (bits.isEmpty()) bits << QStringLiteral("Installed");
    return bits;
}

int status_rank(const QStringList& bits) {
    static const QStringList order = {
        QStringLiteral("Edit"), QStringLiteral("Faulty"), QStringLiteral("Missing"), QStringLiteral("Modified"),
        QStringLiteral("Obsolete"), QStringLiteral("Update"), QStringLiteral("Installed"),
    };
    for (int i = 0; i < order.size(); ++i) {
        if (bits.contains(order[i])) return i;
    }
    return static_cast<int>(order.size());
}

QString decode_status(const QString& raw) {
    static const QString known = QStringLiteral("ABCDEFGILMOPUXY");
    QString flags;
    for (const QString& part : QString(raw).replace(QLatin1Char('\n'), QLatin1Char(' ')).split(QLatin1Char(':'))) {
        QString letters;
        for (const QChar ch : part.trimmed()) {
            if (ch.isLetter()) letters += ch;
        }
        if (letters.size() < 4) continue;
        const bool all = std::all_of(letters.begin(), letters.end(), [](QChar ch) { return known.contains(ch.toUpper()); });
        if (all) {
            flags = letters;
            break;
        }
    }
    if (flags.isEmpty()) {
        const QString text = raw.trimmed().left(500);
        return text.isEmpty() ? QStringLiteral("No status") : text;
    }
    static const QHash<QChar, QString> names = {
        {QLatin1Char('A'), QStringLiteral("archived")}, {QLatin1Char('B'), QStringLiteral("builtin")},
        {QLatin1Char('C'), QStringLiteral("base content")}, {QLatin1Char('D'), QStringLiteral("on Download Station")},
        {QLatin1Char('E'), QStringLiteral("open for edit")}, {QLatin1Char('F'), QStringLiteral("faulty")},
        {QLatin1Char('G'), QStringLiteral("game component")}, {QLatin1Char('I'), QStringLiteral("installed")},
        {QLatin1Char('L'), QStringLiteral("modified locally")}, {QLatin1Char('M'), QStringLiteral("missing dependencies")},
        {QLatin1Char('O'), QStringLiteral("obsolete")}, {QLatin1Char('P'), QStringLiteral("payware")},
        {QLatin1Char('U'), QStringLiteral("update available")}, {QLatin1Char('X'), QStringLiteral("authorised")},
        {QLatin1Char('Y'), QStringLiteral("compatible")},
    };
    QStringList on;
    for (const QChar ch : flags) {
        if (ch.isUpper() && names.contains(ch)) on << names.value(ch);
    }
    if (!flags.contains(QLatin1Char('I'))) on.prepend(QStringLiteral("not installed"));
    return on.isEmpty() ? flags : on.join(QStringLiteral(", "));
}

QString tidy_trainzutil(const QString& text) {
    QStringList out;
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        const QString body = (line.contains(QLatin1String("<NULL>")) ? after_null(line) : line).trimmed();
        if (!body.isEmpty()) out << body;
    }
    return out.join(QLatin1Char('\n'));
}

QString config_credits(const QString& text) {
    static const QRegularExpression tag(QStringLiteral(R"(^(author|organisation|trainz-build)\s+(.+)$)"), QRegularExpression::CaseInsensitiveOption);
    QHash<QString, QString> found;
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        const QRegularExpressionMatch m = tag.match(after_null(line).trimmed());
        if (m.hasMatch()) found.insert(m.captured(1).toLower(), strip_quotes(m.captured(2)));
    }
    QStringList parts;
    for (const char* key : {"author", "organisation", "trainz-build"}) {
        const QString value = found.value(QLatin1String(key));
        if (!value.isEmpty()) parts << value;
    }
    return parts.join(QStringLiteral(" · "));
}

QPair<bool, QString> task_outcome(const QString& raw) {
    if (raw.contains(QLatin1String("not running"), Qt::CaseInsensitive)) return {false, QStringLiteral("Open the Trainz Launcher first")};
    const QString text = tidy_trainzutil(raw);
    static const QRegularExpression errors(QStringLiteral(R"(ok\s*\(\s*(\d+)\s+errors)"), QRegularExpression::CaseInsensitiveOption);
    const QRegularExpressionMatch m = errors.match(text);
    bool failed = m.hasMatch() && m.captured(1).toInt() > 0;
    if (!m.hasMatch() && text.contains(QLatin1String("error"), Qt::CaseInsensitive)) failed = true;
    const QStringList lines = text.split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    QString detail;
    for (const QString& line : lines) {
        if (line.toLower().startsWith(QLatin1String("ok ("))) continue;
        detail = line;
        break;
    }
    if (detail.isEmpty() && !lines.isEmpty()) detail = lines.last();
    if (detail.isEmpty()) detail = failed ? QStringLiteral("Failed") : QStringLiteral("Done");
    return {!failed, detail.left(180)};
}

QPair<QString, QString> classify_trainz_line(const QString& line) {
    const QString raw = line.trimmed();
    if (raw.isEmpty()) return {QStringLiteral("normal"), QString()};
    QChar sign;
    QString body = raw;
    const int null_at = raw.indexOf(QLatin1String("<NULL>"));
    if (null_at >= 0) {
        const QString mark = raw.left(null_at).trimmed();
        body = after_null(raw).trimmed();
        if (mark.endsWith(QLatin1Char('-')) || mark.startsWith(QLatin1Char('-'))) sign = QLatin1Char('-');
        else if (mark.endsWith(QLatin1Char('+')) || mark.startsWith(QLatin1Char('+'))) sign = QLatin1Char('+');
        else if (mark.contains(QLatin1Char('!'))) sign = QLatin1Char('!');
    } else if (raw[0] == QLatin1Char('+') || raw[0] == QLatin1Char('-') || raw[0] == QLatin1Char('!')) {
        sign = raw[0];
        body = raw.mid(1).trimmed();
    }
    const QString shown = body.isEmpty() ? raw : body;
    const QString low = body.toLower();
    if (low.startsWith(QLatin1String("ok ("))) {
        static const QRegularExpression errors(QStringLiteral(R"((\d+)\s+errors)"));
        static const QRegularExpression warnings(QStringLiteral(R"((\d+)\s+warnings)"));
        const QRegularExpressionMatch e = errors.match(low);
        const QRegularExpressionMatch w = warnings.match(low);
        if (e.hasMatch() && e.captured(1).toInt() > 0) return {QStringLiteral("error"), body};
        if (w.hasMatch() && w.captured(1).toInt() > 0) return {QStringLiteral("warn"), body};
        return {QStringLiteral("ok"), body};
    }
    if (sign == QLatin1Char('-')) return {QStringLiteral("error"), shown};
    if (sign == QLatin1Char('!')) return {QStringLiteral("warn"), shown};
    if (sign == QLatin1Char('+')) return {QStringLiteral("ok"), shown};
    if (low.contains(QLatin1String("warning")) && !low.contains(QLatin1String("0 warning"))) return {QStringLiteral("warn"), shown};
    static const QRegularExpression word(QStringLiteral(R"(\berror\b)"));
    if (word.match(low).hasMatch() && !low.contains(QLatin1String("0 error"))) return {QStringLiteral("error"), shown};
    return {QStringLiteral("normal"), shown};
}

QVariantList classify_trainz_log(const QString& text) {
    QVariantList rows;
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        if (line.trimmed().isEmpty()) continue;
        const auto [tone, shown] = classify_trainz_line(line);
        if (!shown.isEmpty()) rows << QVariantMap{{QStringLiteral("text"), shown}, {QStringLiteral("tone"), tone}};
    }
    return rows;
}

QStringList dependency_kuids(const QString& text, const QString& skip) {
    static const QRegularExpression re(QStringLiteral(R"(<kuid2?:-?\d+:-?\d+(?::-?\d+)?>)"));
    QStringList found;
    for (auto it = re.globalMatch(text); it.hasNext();) {
        const QString kuid = it.next().captured(0);
        if (kuid != skip && !found.contains(kuid)) found << kuid;
    }
    return found;
}

QString kuid_from_archive_name(const QString& name) {
    static const QRegularExpression archive(QStringLiteral(R"(^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?\.tzarc$)"), QRegularExpression::CaseInsensitiveOption);
    static const QRegularExpression folder(QStringLiteral(R"(^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?(?:\s|$))"), QRegularExpression::CaseInsensitiveOption);
    QRegularExpressionMatch m = archive.match(name.trimmed());
    if (!m.hasMatch()) m = folder.match(name.trimmed());
    if (!m.hasMatch()) return {};
    if (m.captured(1).compare(QLatin1String("kuid2"), Qt::CaseInsensitive) == 0)
        return QStringLiteral("<kuid2:%1:%2:%3>").arg(m.captured(2), m.captured(3), m.captured(4).isEmpty() ? QStringLiteral("0") : m.captured(4));
    return QStringLiteral("<kuid:%1:%2>").arg(m.captured(2), m.captured(3));
}

qint64 kuid_user_id(const QString& kuid) {
    static const QRegularExpression re(QStringLiteral(R"(^<kuid2?:(-?\d+):)"), QRegularExpression::CaseInsensitiveOption);
    const QRegularExpressionMatch m = re.match(kuid);
    return m.hasMatch() ? m.captured(1).toLongLong() : 0;
}

// ponytail: assets.tdx is undocumented. The user table is `u32 count` then `count` x
// {u32 len, name\0 (len incl. NUL), u32 ?, u32 user id}; we scan for the longest such run.
// O(file) with fast rejects; ~0.3 s on a 170 MB database.
QHash<qint64, QString> parse_kuid_owners(const QByteArray& tdx) {
    const auto* b = reinterpret_cast<const uint8_t*>(tdx.constData());
    const qsizetype size = tdx.size();
    auto u32 = [b](qsizetype p) { return quint32(b[p]) | quint32(b[p + 1]) << 8 | quint32(b[p + 2]) << 16 | quint32(b[p + 3]) << 24; };
    auto record = [&](qsizetype p) -> qsizetype {
        if (p + 4 > size) return -1;
        const quint32 n = u32(p);
        if (n < 2 || n > 100 || p + 4 + n + 8 > size || b[p + 4 + n - 1] != 0) return -1;
        for (quint32 i = 0; i + 1 < n; ++i) {
            if (b[p + 4 + i] < 32) return -1;
        }
        return p + 4 + n + 8;
    };
    qsizetype best = -1;
    quint32 best_count = 0;
    for (qsizetype p = 0; p + 8 < size; ++p) {
        const quint32 count = u32(p);
        if (count < 16 || count > 1000000 || count <= best_count || record(p + 4) < 0) continue;
        qsizetype q = p + 4;
        quint32 seen = 0;
        while (seen < count && (q = record(q)) >= 0) ++seen;
        if (seen == count) {
            best = p;
            best_count = count;
        }
    }
    QHash<qint64, QString> owners;
    if (best < 0) return owners;
    qsizetype q = best + 4;
    for (quint32 i = 0; i < best_count; ++i) {
        const quint32 n = u32(q);
        owners.insert(u32(q + 4 + n + 4), QString::fromUtf8(tdx.constData() + q + 4, n - 1));
        q += 4 + n + 8;
    }
    return owners;
}

QHash<qint64, QString> read_kuid_owners(const QString& tdx_path) {
    QFile file(tdx_path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    return parse_kuid_owners(file.readAll());
}

QString format_bytes(qint64 size) {
    if (size < 1024) return QString::number(size) + QStringLiteral(" B");
    if (size < 1024 * 1024) return QString::number(size / 1024.0, 'f', 1) + QStringLiteral(" KB");
    if (size < 1024LL * 1024 * 1024) return QString::number(size / (1024.0 * 1024.0), 'f', 1) + QStringLiteral(" MB");
    return QString::number(size / (1024.0 * 1024.0 * 1024.0), 'f', 2) + QStringLiteral(" GB");
}

QString fmt_mtime(qint64 unix_secs) {
    if (unix_secs <= 0) return {};
    return QDateTime::fromSecsSinceEpoch(unix_secs).toString(QStringLiteral("yyyy-MM-dd HH:mm"));
}

QString cdp_stem(const QString& name, const QString& kuid) {
    QString raw;
    for (const QChar ch : name) raw += (ch.isLetterOrNumber() || QStringLiteral(" ._-").contains(ch)) ? ch : QLatin1Char('_');
    while (!raw.isEmpty() && QStringLiteral(" ._").contains(raw.front())) raw.remove(0, 1);
    while (!raw.isEmpty() && QStringLiteral(" ._").contains(raw.back())) raw.chop(1);
    if (raw.isEmpty()) raw = QString(kuid).remove(QLatin1Char('<')).remove(QLatin1Char('>')).replace(QLatin1Char(':'), QLatin1Char('_'));
    return raw.left(80);
}

QHash<QString, ArchiveHit> ContentIndex::chosen() const {
    QHash<QString, ArchiveHit> out = original;
    out.insert(local);
    return out;
}

QStringList content_roots(const QString& data_dir) {
    if (!data_dir.isEmpty() && QFileInfo(data_dir).isDir()) return {data_dir};
    const QString local = QProcessEnvironment::systemEnvironment().value(QStringLiteral("LOCALAPPDATA"));
    QStringList roots;
    if (local.isEmpty()) return roots;
    const QDir n3v(local + QStringLiteral("/N3V Games"));
    for (const QFileInfo& game : n3v.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        for (const QFileInfo& build : QDir(game.filePath()).entryInfoList({QStringLiteral("build *")}, QDir::Dirs | QDir::NoDotAndDotDot)) {
            const QDir dir(build.filePath());
            if (dir.exists(QStringLiteral("local")) || dir.exists(QStringLiteral("original")) || dir.exists(QStringLiteral("editing"))) roots << build.filePath();
        }
    }
    return roots;
}

ContentIndex index_content(const QStringList& roots) {
    ContentIndex index;
    for (const QString& base : roots) {
        index.original.insert(scan_archive_folder(base + QStringLiteral("/original")));
        index.local.insert(scan_archive_folder(base + QStringLiteral("/local")));
        const QString editing = base + QStringLiteral("/editing");
        for (const DirEntry& entry : list_dir(editing)) {
            if (!entry.dir) continue;
            const QString folder = editing + QLatin1Char('/') + entry.name;
            QString kuid = kuid_from_archive_name(entry.name);
            if (!kuid.isEmpty()) index.editing_mtime.insert(kuid, entry.mtime_ns / 1000000000LL);
            else kuid = own_kuid(folder + QStringLiteral("/config.txt"));
            if (!kuid.isEmpty() && !index.editing_folder.contains(kuid)) index.editing_folder.insert(kuid, folder);
        }
    }
    return index;
}

QString meta_cache_file() { return cache_dir(QString()) + QStringLiteral("tu-archive-meta.json"); }

QHash<QString, AssetMeta> scan_archive_meta(
    const ContentIndex& index, const QString& cache_file, const std::function<void(const QString&)>& status) {
    const QHash<QString, ArchiveHit> chosen = index.chosen();
    if (status) status(QStringLiteral("%1 archives listed. Checking the author cache…").arg(chosen.size()));
    QJsonObject cache;
    {
        const QJsonDocument doc = QJsonDocument::fromJson(read_all(cache_file));
        if (doc.isObject()) cache = doc.object();
    }
    QHash<QString, AssetMeta> out;
    QStringList misses;
    for (auto it = chosen.begin(); it != chosen.end(); ++it) {
        const QJsonArray row = cache.value(it.key()).toArray();
        // [author, build, mtime] is a hit. Username, when present, is index 3.
        // Requiring 4 fields would reopen every archive written by an older cache.
        if (row.size() >= 3 && row.at(2).toInteger() == it->mtime_ns) {
            out.insert(it.key(), {row.at(0).toString(), row.at(1).toString(), row.size() >= 4 ? row.at(3).toString() : QString()});
            continue;
        }
        misses << it.key();
    }
    if (status) {
        status(misses.isEmpty() ? QStringLiteral("Author cache is current. No archives need opening.")
                                : QStringLiteral("Opening %1 archives that are new or changed.").arg(misses.size()));
    }
    if (!misses.isEmpty()) {
        const auto rows = parallel_map<AssetMeta>(misses, [&](const QString& kuid) {
            const std::vector<uint8_t> config = tzarc_config(chosen.value(kuid).path);
            const ConfigIdentity id = config_identity(config.data(), config.size());
            return AssetMeta{QString::fromStdString(id.author), QString::fromStdString(id.build), QString::fromStdString(id.username)};
        });
        for (int i = 0; i < misses.size(); ++i) {
            const AssetMeta& meta = rows[static_cast<size_t>(i)];
            out.insert(misses[i], meta);
            cache.insert(misses[i], QJsonArray{meta.author, meta.build, chosen.value(misses[i]).mtime_ns, meta.username});
        }
        QFile file(cache_file);
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(QJsonDocument(cache).toJson(QJsonDocument::Compact));
    }
    for (auto it = index.editing_folder.begin(); it != index.editing_folder.end(); ++it) {
        const QByteArray bytes = read_all(it.value() + QStringLiteral("/config.txt"));
        if (bytes.isEmpty()) continue;
        const ConfigIdentity id = config_identity(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
        out.insert(it.key(), {QString::fromStdString(id.author), QString::fromStdString(id.build), QString::fromStdString(id.username)});
    }
    return out;
}

QString asset_cover_path(const ContentIndex& index, const QString& kuid) {
    const QString folder = index.editing_folder.value(kuid);
    if (!folder.isEmpty()) {
        const QString loose = cover_in_folder(folder);
        if (!loose.isEmpty()) return loose;
    }
    const QString archive = index.chosen().value(kuid).path;
    if (archive.isEmpty()) return {};
    const QByteArray bytes = read_all(archive);
    QStringList names;
    std::vector<uint8_t> blob;
    try {
        const auto* data = reinterpret_cast<const uint8_t*>(bytes.constData());
        const size_t size = static_cast<size_t>(bytes.size());
        names = cover_names(read_tzarc_config(data, size));
        std::vector<std::string> wanted;
        for (const QString& name : names) wanted.push_back(name.toStdString());
        blob = read_tzarc_named(data, size, wanted);
    } catch (const std::exception&) {
        return {};
    }
    if (blob.size() < 32) return {};
    const QString dir = cache_dir(QStringLiteral("covers"));
    const QString dest = dir + QLatin1Char('/') + safe_name(kuid) + blob_suffix(blob, names.isEmpty() ? QString() : names.first());
    const QString stamp_path = dir + QLatin1Char('/') + safe_name(kuid) + QStringLiteral(".stamp");
    const QString key = archive_key(archive) + QLatin1Char(':') + QFileInfo(dest).fileName();
    if (QFileInfo(dest).isFile() && read_all(stamp_path) == key.toUtf8()) return dest;
    QFile out(dest);
    if (!out.open(QIODevice::WriteOnly | QIODevice::Truncate)) return {};
    out.write(reinterpret_cast<const char*>(blob.data()), static_cast<qint64>(blob.size()));
    out.close();
    QFile stamp(stamp_path);
    if (stamp.open(QIODevice::WriteOnly | QIODevice::Truncate)) stamp.write(key.toUtf8());
    return dest;
}

// Keeps what the mesh viewer reads: meshes, the images textures resolve to, and *.texture.txt.
static bool wanted_for_preview(const QString& rel) {
    static const QStringList ext = {QStringLiteral("trainzmesh"), QStringLiteral("im"), QStringLiteral("png"), QStringLiteral("tga"), QStringLiteral("jpg"), QStringLiteral("jpeg"), QStringLiteral("bmp"), QStringLiteral("tif"), QStringLiteral("tiff")};
    return rel.endsWith(QLatin1String(".texture.txt"), Qt::CaseInsensitive) || ext.contains(QFileInfo(rel).suffix().toLower());
}

QString asset_browse_dir(const ContentIndex& index, const QString& kuid, bool preview_only) {
    const QString folder = index.editing_folder.value(kuid);
    if (!folder.isEmpty() && QFileInfo(folder).isDir()) return folder;
    const QString archive = index.chosen().value(kuid).path;
    if (archive.isEmpty()) return {};
    const QString cache = cache_dir(QString::fromLatin1(preview_only ? "unpack-preview/" : "unpack/") + safe_name(kuid));
    const QString stamp_path = cache + QStringLiteral("/.stamp");
    const QString key = archive_key(archive);
    if (read_all(stamp_path) == key.toUtf8() && QDir(cache).entryList(QDir::AllEntries | QDir::NoDotAndDotDot).size() > 1) return cache;
    // Map instead of reading: only the pages of the chunks we inflate are ever touched.
    QFile file(archive);
    if (!file.open(QIODevice::ReadOnly)) return {};
    const uchar* mapped = file.map(0, file.size());
    QByteArray fallback;
    if (!mapped) {
        fallback = file.readAll();
        mapped = reinterpret_cast<const uchar*>(fallback.constData());
    }
    try {
        const auto keep = [preview_only](const std::string& name) {
            return !preview_only || wanted_for_preview(QString::fromStdString(name));
        };
        for (const auto& [name, body] : read_tzarc_select(mapped, static_cast<size_t>(file.size()), keep)) {
            const QString rel = QString::fromStdString(name).replace(QLatin1Char('\\'), QLatin1Char('/'));
            if (rel.isEmpty() || rel.startsWith(QLatin1Char('/')) || rel.contains(QLatin1String("..")) || rel.contains(QLatin1Char(':'))) continue;
            const QString dest = cache + QLatin1Char('/') + rel;
            QDir().mkpath(QFileInfo(dest).path());
            QFile out(dest);
            if (!out.open(QIODevice::WriteOnly | QIODevice::Truncate)) continue;
            out.write(reinterpret_cast<const char*>(body.data()), static_cast<qint64>(body.size()));
        }
    } catch (const std::exception&) {
        return {};
    }
    QFile stamp(stamp_path);
    if (stamp.open(QIODevice::WriteOnly | QIODevice::Truncate)) stamp.write(key.toUtf8());
    return cache;
}
QString config_in_editing(const QString& editing, const QString& kuid) {
    const QString token = kuid.trimmed();
    if (token.isEmpty()) return {};
    for (const QFileInfo& child : QDir(editing).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        const QString config = child.filePath() + QStringLiteral("/config.txt");
        if (kuid_from_archive_name(child.fileName()) == token && QFileInfo(config).isFile()) return config;
    }
    for (const QFileInfo& child : QDir(editing).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        const QString config = child.filePath() + QStringLiteral("/config.txt");
        if (QString::fromUtf8(read_all(config)).contains(token)) return config;
    }
    return {};
}

QList<AssetBackup> find_asset_backups(const QString& data_dir, const QString& query, int limit) {
    const QString root = data_dir + QStringLiteral("/backups");
    const QStringList tokens = search_tokens(query.trimmed());
    static const QRegularExpression hash_dir(QStringLiteral("^[a-z0-9]{6,16}$"));
    QList<AssetBackup> found;
    for (const QFileInfo& day : QDir(root).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        if (!day_dir().match(day.fileName()).hasMatch()) continue;
        const QString label = day_label(day.fileName());
        for (const QFileInfo& child : QDir(day.filePath()).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden)) {
            const QString name = child.fileName();
            const QString kuid = backup_kuid(name);
            const QString blob = name.toLower();
            if (!tokens.isEmpty() && !std::all_of(tokens.begin(), tokens.end(), [&](const QString& t) { return blob.contains(t); })) continue;
            if (tokens.isEmpty() && kuid.isEmpty() && !blob.contains(QLatin1String(".tzarc")) && hash_dir.match(name).hasMatch()) continue;
            AssetBackup row;
            row.day = label;
            row.day_key = day.fileName();
            row.name = name;
            row.kind = child.isDir() ? QStringLiteral("Folder") : blob.contains(QLatin1String(".tzarc")) ? QStringLiteral("tzarc") : QStringLiteral("File");
            row.path = child.absoluteFilePath();
            row.size = child.isDir() ? 0 : child.size();
            row.mtime = child.lastModified().toSecsSinceEpoch();
            row.kuid = kuid;
            row.when = child.lastModified().toString(QStringLiteral("HH:mm"));
            found << row;
        }
    }
    std::sort(found.begin(), found.end(), [](const AssetBackup& a, const AssetBackup& b) {
        if (a.day_key != b.day_key) return a.day_key > b.day_key;
        return a.mtime > b.mtime;
    });
    if (found.size() > limit) found.resize(limit);
    return found;
}

QHash<QString, QString> describe_backup(const QString& path) {
    const QFileInfo info(path);
    const QString name = info.fileName();
    const QString kind = info.isDir() ? QStringLiteral("Folder") : name.contains(QLatin1String(".tzarc"), Qt::CaseInsensitive) ? QStringLiteral("tzarc") : QStringLiteral("File");
    std::vector<uint8_t> raw;
    if (info.isDir()) {
        const QByteArray bytes = read_all(path + QStringLiteral("/config.txt"));
        raw.assign(bytes.begin(), bytes.end());
    } else if (kind == QLatin1String("tzarc")) {
        raw = tzarc_config(path);
    }
    const ConfigIdentity id = config_identity(raw.data(), raw.size());
    QString asset_kind;
    static const QRegularExpression kind_tag(QStringLiteral(R"re((?im)^kind\s+"?([^"\r\n]+)"?)re"));
    const QRegularExpressionMatch k = kind_tag.match(QString::fromUtf8(reinterpret_cast<const char*>(raw.data()), static_cast<qsizetype>(raw.size())));
    if (k.hasMatch()) asset_kind = strip_quotes(k.captured(1));
    QString display = name;
    display.remove(QRegularExpression(QStringLiteral(R"(\.tzarc.*$)"), QRegularExpression::CaseInsensitiveOption));
    display.remove(QRegularExpression(QStringLiteral(R"(_\d{6,}$)")));
    display = display.trimmed();
    if (display.isEmpty()) display = name;
    const QString parent = info.dir().dirName();
    return {
        {QStringLiteral("kuid"), backup_kuid(name)},
        {QStringLiteral("title"), id.username.empty() ? display : QString::fromStdString(id.username)},
        {QStringLiteral("category"), asset_kind.isEmpty() ? kind : asset_kind},
        {QStringLiteral("installed"), day_dir().match(parent).hasMatch() ? day_label(parent) : parent},
        {QStringLiteral("modified"), info.lastModified().toString(QStringLiteral("yyyy-MM-dd HH:mm"))},
        {QStringLiteral("size"), info.isFile() ? format_bytes(info.size()) : QStringLiteral("Folder")},
        {QStringLiteral("author"), QString::fromStdString(author_label(id.author, id.build))},
        {QStringLiteral("build"), QString::fromStdString(id.build)},
        {QStringLiteral("note"), QDir::toNativeSeparators(path)},
        {QStringLiteral("status"), kind},
    };
}

QStringList collect_script_files(const QStringList& paths) {
    QStringList found;
    QSet<QString> seen;
    auto take = [&](const QString& path) {
        const QFileInfo info(path);
        if (!info.isFile() || info.suffix().compare(QLatin1String("gs"), Qt::CaseInsensitive) != 0) return;
        const QString full = QDir::toNativeSeparators(info.absoluteFilePath());
        if (seen.contains(full.toLower())) return;
        seen.insert(full.toLower());
        found << full;
    };
    for (const QString& path : paths) {
        if (QFileInfo(path).isDir()) {
            QStringList nested;
            QDirIterator it(path, {QStringLiteral("*.gs")}, QDir::Files, QDirIterator::Subdirectories);
            while (it.hasNext()) nested << it.next();
            std::sort(nested.begin(), nested.end());
            for (const QString& item : nested) take(item);
            continue;
        }
        take(path);
    }
    return found;
}

QHash<QString, QString> encrypt_error_map(const QString& text) {
    static const QRegularExpression echo(QStringLiteral(R"re(<NULL>\s*:\s*encrypt\s+"([^"]+)")re"), QRegularExpression::CaseInsensitiveOption);
    QHash<QString, QString> found;
    QString current;
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        if (line.contains(QLatin1String("failure on line"), Qt::CaseInsensitive)) continue;
        const QRegularExpressionMatch m = echo.match(line);
        if (m.hasMatch()) {
            current = m.captured(1).replace(QLatin1Char('/'), QLatin1Char('\\')).toLower();
            if (!found.contains(current)) found.insert(current, QString());
            continue;
        }
        if (current.isEmpty() || !found.value(current).isEmpty()) continue;
        if (!line.contains(QLatin1String("- <NULL>")) && !line.trimmed().startsWith(QLatin1Char('-'))) continue;
        const QString msg = after_null(line).trimmed();
        if (!msg.isEmpty()) found[current] = msg;
    }
    return found;
}
