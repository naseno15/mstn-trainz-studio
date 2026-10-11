#include "io/acs_tree.h"

#include <QHash>
#include <QSet>

namespace {

struct Parser {
    const QString& s;
    int i = 0;
    bool ok = true;
    QString error;

    void skip_inline() {
        while (i < s.size() && (s[i] == QLatin1Char(' ') || s[i] == QLatin1Char('\t') || s[i] == QLatin1Char('\r'))) ++i;
    }
    void skip_ws() {
        while (i < s.size() && s[i].isSpace()) ++i;
    }

    bool take_string(QString& out) {
        ++i;
        while (i < s.size()) {
            if (s[i] == QLatin1Char('\\') && i + 1 < s.size()) {
                out += s[i + 1];
                i += 2;
                continue;
            }
            if (s[i] == QLatin1Char('"')) {
                ++i;
                return true;
            }
            out += s[i++];
        }
        ok = false;
        error = QStringLiteral("A quote was left open");
        return false;
    }

    void take_line(AcsNode& node) {
        int end = i;
        while (end < s.size() && s[end] != QLatin1Char('\n')) ++end;
        int begin = i;
        while (begin < end && s[begin].isSpace()) ++begin;
        int trim = end;
        while (trim > begin && (s[trim - 1] == QLatin1Char(' ') || s[trim - 1] == QLatin1Char('\t') || s[trim - 1] == QLatin1Char('\r'))) --trim;
        node.begin = begin;
        node.end = trim;
        node.value = s.mid(begin, trim - begin);
        i = end;
    }

    void take_kids(AcsNode& box) {
        while (ok && i < s.size()) {
            skip_ws();
            if (i >= s.size()) break;
            if (s[i] == QLatin1Char('}')) {
                ++i;
                return;
            }
            box.kids.append(take_tag());
        }
        ok = false;
        if (error.isEmpty()) error = QStringLiteral("A { was left open");
    }

    AcsNode take_tag() {
        AcsNode node;
        const int start = i;
        while (i < s.size() && !s[i].isSpace() && s[i] != QLatin1Char('{') && s[i] != QLatin1Char('}')) ++i;
        node.name = s.mid(start, i - start);
        skip_inline();
        if (i < s.size() && s[i] == QLatin1Char('{')) {
            node.box = true;
            ++i;
            take_kids(node);
            return node;
        }
        if (i < s.size() && s[i] == QLatin1Char('"')) {
            node.quoted = true;
            node.begin = i;
            take_string(node.value);
            node.end = i;
            return node;
        }
        if (i < s.size() && s[i] != QLatin1Char('\n')) {
            take_line(node);
            return node;
        }
        const int line = i;
        skip_ws();
        if (i < s.size() && s[i] == QLatin1Char('{')) {
            node.box = true;
            ++i;
            take_kids(node);
            return node;
        }
        i = line;
        node.begin = line;
        node.end = line;
        return node;
    }
};

const QHash<QString, QString>& kuid_filters() {
    static const QHash<QString, QString> map = {
        {QStringLiteral("interior"), QStringLiteral("INTR,INT")},
        {QStringLiteral("enginespec"), QStringLiteral("ESPC")},
        {QStringLiteral("enginesound"), QStringLiteral("ESND")},
        {QStringLiteral("hornsound"), QStringLiteral("HORN")},
        {QStringLiteral("pantograph"), QStringLiteral("PANT")},
        {QStringLiteral("mesh-asset"), QStringLiteral("MESH,MOBJ")},
        {QStringLiteral("default-mesh"), QStringLiteral("MESH,MOBJ")},
        {QStringLiteral("bogey"), QStringLiteral("BOGY,BOG,BOGEY")},
        {QStringLiteral("product-kuid"), QStringLiteral("PROD")},
        {QStringLiteral("texture-kuid"), QStringLiteral("TX,TEX,TXGRP")},
        {QStringLiteral("sound-asset"), QStringLiteral("ESND,HORN,SND,SNDS")},
        {QStringLiteral("preview-mesh-kuid"), QStringLiteral("MESH,MOBJ")},
        {QStringLiteral("track-sound"), QStringLiteral("TSND,SND")},
    };
    return map;
}

const QSet<QString>& bool_tags() {
    static const QSet<QString> set = {
        QStringLiteral("engine"), QStringLiteral("tender"), QStringLiteral("auto-create"), QStringLiteral("reversed"),
        QStringLiteral("direct-drive"), QStringLiteral("istrack"), QStringLiteral("isroad"), QStringLiteral("istunnel"),
        QStringLiteral("home"), QStringLiteral("repeater"), QStringLiteral("always-controlled"), QStringLiteral("trackside"),
        QStringLiteral("nostartdelay"), QStringLiteral("surveyor-only"), QStringLiteral("directional"),
        QStringLiteral("rotation-permitted"), QStringLiteral("sideplay-permitted"), QStringLiteral("use-coupler-sounds"),
        QStringLiteral("does-cast-shadows"), QStringLiteral("should-respond-to-clicks"), QStringLiteral("critical-animation"),
        QStringLiteral("double-blocking"), QStringLiteral("enable-shadows-in-cab"), QStringLiteral("cabin-visible-from-outside"),
        QStringLiteral("outside-visible-from-cabin"),
    };
    return set;
}

const QSet<QString>& file_tags() {
    static const QSet<QString> set = {
        QStringLiteral("mesh"), QStringLiteral("anim"), QStringLiteral("texture"), QStringLiteral("script"),
        QStringLiteral("image"), QStringLiteral("collision-mesh"), QStringLiteral("night-mesh-base"),
        QStringLiteral("fonts-path"), QStringLiteral("interior-light-texture"),
    };
    return set;
}

bool numeric_token(const QString& value) {
    if (value.isEmpty()) return false;
    for (const QChar ch : value) {
        if (ch.isDigit() || ch == QLatin1Char('.') || ch == QLatin1Char('-') || ch == QLatin1Char(',') || ch == QLatin1Char(' ')) continue;
        return false;
    }
    return true;
}

const QHash<QString, QString>& number_units() {
    static const QHash<QString, QString> map = {
        {QStringLiteral("mass"), QStringLiteral("kg")},
        {QStringLiteral("max-coupler-gap"), QStringLiteral("m")},
        {QStringLiteral("max-tractive-effort"), QStringLiteral("N")},
        {QStringLiteral("smoke_slowlife"), QStringLiteral("s")},
        {QStringLiteral("smoke_fastlife"), QStringLiteral("s")},
        {QStringLiteral("smoke_fastspeed"), QStringLiteral("m/s")},
        {QStringLiteral("smoke_height"), QStringLiteral("m")},
        {QStringLiteral("smoke_shade"), QStringLiteral("0–1")},
        {QStringLiteral("suspension-pitch-limit"), QStringLiteral("deg")},
        {QStringLiteral("suspension-roll-limit"), QStringLiteral("deg")},
        {QStringLiteral("mesh-table-lod-transition-distances"), QStringLiteral("m")},
        {QStringLiteral("maximum-lod-distance"), QStringLiteral("m")},
        {QStringLiteral("visibility-radius"), QStringLiteral("m")},
        {QStringLiteral("height-range"), QStringLiteral("m")},
        {QStringLiteral("tunnel-roof-height"), QStringLiteral("m")},
        {QStringLiteral("animdist"), QStringLiteral("m")},
        {QStringLiteral("axle-offsets"), QStringLiteral("m")},
        {QStringLiteral("distance"), QStringLiteral("m")},
        {QStringLiteral("light_color"), QStringLiteral("RGB")},
        {QStringLiteral("ditch_color"), QStringLiteral("RGB")},
        {QStringLiteral("interior-light-color"), QStringLiteral("RGB")},
        {QStringLiteral("high_beam_value"), QStringLiteral("×")},
        {QStringLiteral("low_beam_value"), QStringLiteral("×")},
        {QStringLiteral("flash_scale"), QStringLiteral("×")},
        {QStringLiteral("cabin_muffle"), QStringLiteral("×")},
        {QStringLiteral("cabinsway"), QStringLiteral("×")},
        {QStringLiteral("preview-scale"), QStringLiteral("×")},
        {QStringLiteral("opacity"), QStringLiteral("0–1")},
        {QStringLiteral("angles"), QStringLiteral("rad")},
        {QStringLiteral("traffic-speed"), QStringLiteral("m/s")},
        {QStringLiteral("carrate"), QStringLiteral("×")},
        {QStringLiteral("mousespeed"), QStringLiteral("×")},
        {QStringLiteral("fonts"), QStringLiteral("×")},
    };
    return map;
}

template <int N>
QStringList menu_table(const char* const (&rows)[N][2]) {
    QStringList out;
    for (int i = 0; i < N; ++i) out << QLatin1String(rows[i][0]) + QLatin1Char('|') + QLatin1String(rows[i][1]);
    return out;
}

QStringList kind_menu() {
    static const char* names[] = {
        "traincar", "bogey", "interior", "engine", "enginesound", "hornsound", "mesh", "texture", "texture-group",
        "library", "scenery", "trackside", "mosignal", "mojunction", "mocrossing", "mospeedboard", "track", "fixedtrack",
        "industry", "buildable", "product", "product-category", "pantograph", "groundtexture", "water2", "turntable",
        "map", "profile", "region", "behavior", "html-asset", "sound", "tracksound",
    };
    QStringList out;
    for (const char* name : names) out << QString::fromLatin1(name) + QLatin1Char('|') + QString::fromLatin1(name);
    return out;
}

QStringList region_menu() {
    static const char* rows[][2] = {
        {"AT", "Austria"}, {"AU", "Australia"}, {"BE", "Belgium"}, {"BR", "Brazil"}, {"CA", "Canada"}, {"CH", "Switzerland"},
        {"CN", "China"}, {"CZ", "Czechia"}, {"DE", "Germany"}, {"DK", "Denmark"}, {"EG", "Egypt"}, {"ES", "Spain"},
        {"EU", "Europe"}, {"FI", "Finland"}, {"FR", "France"}, {"GR", "Greece"}, {"HU", "Hungary"}, {"ID", "Indonesia"},
        {"IE", "Ireland"}, {"IN", "India"}, {"IT", "Italy"}, {"JP", "Japan"}, {"KR", "Korea"}, {"MX", "Mexico"},
        {"MY", "Malaysia"}, {"NL", "Netherlands"}, {"NO", "Norway"}, {"NZ", "New Zealand"}, {"PH", "Philippines"},
        {"PL", "Poland"}, {"PT", "Portugal"}, {"RO", "Romania"}, {"RU", "Russia"}, {"SE", "Sweden"}, {"SG", "Singapore"},
        {"TH", "Thailand"}, {"TR", "Turkey"}, {"TW", "Taiwan"}, {"UA", "Ukraine"}, {"UK", "United Kingdom"},
        {"US", "United States"}, {"VN", "Vietnam"}, {"WW", "Worldwide"},         {"ZA", "South Africa"},
    };
    return menu_table(rows);
}

QStringList class_menu() {
    static const char* rows[][2] = {
        {"AL", "Locomotive"}, {"BC", "Boxcar"}, {"BG", "Bogey"}, {"BK", "Bulk"}, {"BR", "Bridge"}, {"CC", "Caboose"},
        {"CH", "Coach"}, {"CN", "Container"}, {"CV", "Covered hopper"}, {"FA", "Flatcar"}, {"GC", "Gondola"},
        {"HP", "Hopper"}, {"IN", "Industry"}, {"LB", "Building"}, {"LC", "Locomotive"}, {"LV", "Livestock"},
        {"RF", "Refrigerator"}, {"TK", "Tank"}, {"TM", "Track maintenance"}, {"XF", "Diesel railcar"}, {"XP", "Passenger"},
        {"ZA", "Scenery"}, {"ZB", "Bogey"}, {"ZI", "Interior"}, {"ZL", "Library"}, {"ZM", "Mesh"}, {"ZS", "Engine sound"},
        {"ZT", "Texture"}, {"ZX", "Engine spec"}, {"WA", "Signal"}, {"WX", "Junction"}, {"ESPC", "Engine spec"},
        {"ESND", "Engine sound"}, {"HORN", "Horn"}, {"MESH", "Mesh"}, {"INTR", "Interior"}, {"BOGY", "Bogey"},
        {"SLIB", "Script library"}, {"SCEN", "Scenery"}, {"PROD", "Product"}, {"PANT", "Pantograph"}, {"TV", "Train vehicle"},
        {"TX", "Texture"},
    };
    return menu_table(rows);
}

bool same_code(const QString& left, const QString& right) {
    if (left.compare(right, Qt::CaseInsensitive) == 0) return true;
    bool left_ok = false;
    bool right_ok = false;
    const double a = left.toDouble(&left_ok);
    const double b = right.toDouble(&right_ok);
    return left_ok && right_ok && qAbs(a - b) < 0.001;
}

QString menu_labels(const QString& raw, const QStringList& pairs) {
    QStringList codes;
    QStringList names;
    for (const QString& pair : pairs) {
        const int bar = pair.indexOf(QLatin1Char('|'));
        if (bar <= 0) continue;
        codes << pair.left(bar);
        names << pair.mid(bar + 1);
    }
    QStringList labels;
    for (const QString& code : raw.split(QLatin1Char(';'), Qt::SkipEmptyParts)) {
        const QString key = code.trimmed();
        int found = -1;
        for (int i = 0; i < codes.size(); ++i)
            if (same_code(codes[i], key)) found = i;
        labels << (found < 0 ? key : names[found]);
    }
    return labels.join(QStringLiteral(", "));
}

// The value stored in config.txt is the trainz-build tag, not the installer build (117655 and the like).
// Several installer builds share one tag. Pairs below are the products that ship that tag.
QStringList build_menu() {
    static const char* rows[][2] = {
        {"1.3", "Trainz 1.3"},
        {"1.5", "Ultimate Trainz Collection"},
        {"1.6", "UTC SP1"},
        {"2.0", "TRS2004"},
        {"2.1", "TRS2004 SP1"},
        {"2.2", "TRS2004 SP2"},
        {"2.3", "TRS2004 SP3"},
        {"2.4", "TRS2004 SP4"},
        {"2.5", "TRS2006"},
        {"2.6", "TRS2006 SP1"},
        {"2.7", "Trainz Classics 1 and 2"},
        {"2.8", "Trainz Classics 3"},
        {"2.9", "TS2009"},
        {"3.0", "TS2009 SP1"},
        {"3.1", "TS2009 SP2 / SP3"},
        {"3.2", "TS2010 / SP1"},
        {"3.3", "TS2010 SP2 / SP3, TS2009 SP4"},
        {"3.4", "TS2010 SP4"},
        {"3.5", "TS12"},
        {"3.6", "TS12 / Trainz Mac"},
        {"3.7", "TS12 SP1"},
        {"3.8", "Trainz Mac 2"},
        {"3.9", "T:ANE Community Edition"},
        {"4.0", "T:ANE"},
        {"4.1", "T:ANE SP1"},
        {"4.2", "T:ANE SP2"},
        {"4.3", "T:ANE SP3"},
        {"4.5", "TRS19"},
        {"4.6", "TRS19 SP1"},
        {"4.7", "TRS19 SP2 / Trainz Plus"},
        {"4.8", "TRS19 SP3"},
        {"4.9", "TRS19 SP4"},
        {"5.0", "TRS19 SP5 / TRS22 early"},
        {"5.1", "TRS22"},
        {"5.2", "TRS22 SP1"},
        {"5.3", "TRS22 SP2 / Trainz Plus"},
        {"5.4", "TRS22 SP3"},
        {"5.5", "TRS22 SP4"},
        {"5.6", "TRS22 SP5 / SP6, Trainz Plus"},
        {"5.7", "Trainz Plus beta"},
    };
    return menu_table(rows);
}

bool digits_only(const QString& name) {
    if (name.isEmpty()) return false;
    for (const QChar ch : name)
        if (!ch.isDigit()) return false;
    return true;
}

}  // namespace

AcsFile parse_acs(const QString& text) {
    Parser parser{text};
    AcsFile file;
    file.root.box = true;
    while (parser.ok && parser.i < text.size()) {
        parser.skip_ws();
        if (parser.i >= text.size()) break;
        if (text[parser.i] == QLatin1Char('}')) {
            parser.ok = false;
            parser.error = QStringLiteral("A } has no matching {");
            break;
        }
        file.root.kids.append(parser.take_tag());
    }
    file.ok = parser.ok;
    file.error = parser.error;
    return file;
}

const AcsNode* acs_at(const AcsNode& root, const QList<int>& path) {
    const AcsNode* node = &root;
    for (int index : path) {
        if (index < 0 || index >= node->kids.size()) return nullptr;
        node = &node->kids[index];
    }
    return node;
}

QStringList acs_parents(const AcsNode& root, const QList<int>& path) {
    QStringList names;
    const AcsNode* node = &root;
    for (int index : path) {
        if (index < 0 || index >= node->kids.size()) break;
        node = &node->kids[index];
        if (!node->name.isEmpty()) names << node->name;
    }
    return names;
}

AcsHint acs_hint(const QStringList& parents, const QString& name, const QString& value, bool box) {
    AcsHint hint;
    if (box) {
        hint.editor = QStringLiteral("container");
        return hint;
    }
    const QString parent = parents.isEmpty() ? QString() : parents.last();
    const bool in_effect = parents.size() >= 2 && parents[parents.size() - 2] == QLatin1String("effects");
    const bool in_mesh = parents.contains(QLatin1String("mesh-table")) && parent != QLatin1String("mesh-table") && parent != QLatin1String("effects") && !in_effect;
    if (in_effect && name == QLatin1String("kind")) {
        hint.editor = QStringLiteral("enum");
        hint.options = {QStringLiteral("texture-replacement"), QStringLiteral("corona"), QStringLiteral("attachment"), QStringLiteral("name"), QStringLiteral("animation")};
        return hint;
    }
    if (in_mesh && name == QLatin1String("kind")) {
        hint.editor = QStringLiteral("enum");
        hint.options = {QStringLiteral("lever"), QStringLiteral("animated-lever"), QStringLiteral("needle"), QStringLiteral("pulllever"), QStringLiteral("pullrope"), QStringLiteral("light"), QStringLiteral("collision-proxy")};
        return hint;
    }
    if (parent == QLatin1String("kuid-table") || parent == QLatin1String("obsolete-table")) {
        hint.editor = digits_only(name) ? QStringLiteral("alias") : QStringLiteral("kuid");
        return hint;
    }
    if (parent == QLatin1String("script-include-table")) {
        hint.editor = QStringLiteral("kuid");
        hint.filter = QStringLiteral("SLIB");
        return hint;
    }
    if (kuid_filters().contains(name) || value.startsWith(QLatin1String("<kuid"))) {
        hint.editor = QStringLiteral("kuid");
        hint.filter = kuid_filters().value(name);
        return hint;
    }
    if (bool_tags().contains(name) && (value.isEmpty() || value == QLatin1String("0") || value == QLatin1String("1"))) {
        hint.editor = QStringLiteral("bool");
        return hint;
    }
    if (file_tags().contains(name)) {
        hint.editor = QStringLiteral("file");
        return hint;
    }
    if (parents.isEmpty() && (name == QLatin1String("kind") || name == QLatin1String("category-class") || name == QLatin1String("category-region") || name == QLatin1String("trainz-build"))) {
        hint.editor = QStringLiteral("menu");
        hint.multi = name == QLatin1String("category-region");
        hint.options = name == QLatin1String("kind") ? kind_menu() : name == QLatin1String("category-class") ? class_menu() : name == QLatin1String("trainz-build") ? build_menu() : region_menu();
        return hint;
    }
    if (numeric_token(value) && name != QLatin1String("username") && name != QLatin1String("description")) {
        hint.editor = QStringLiteral("number");
        hint.unit = number_units().value(name);
        return hint;
    }
    hint.editor = QStringLiteral("text");
    return hint;
}

QString acs_menu_text(const QString& raw, const QStringList& pairs) { return menu_labels(raw, pairs); }

QString acs_format(const QString& editor, const QString& raw, bool quoted) {
    QString text = raw.trimmed();
    if (editor == QLatin1String("bool"))
        return (text == QLatin1String("1") || text.compare(QLatin1String("true"), Qt::CaseInsensitive) == 0 || text.compare(QLatin1String("on"), Qt::CaseInsensitive) == 0) ? QStringLiteral("1") : QStringLiteral("0");
    if (editor == QLatin1String("kuid")) {
        if (text.startsWith(QLatin1Char('<'))) return text;
        if (text.startsWith(QLatin1String("kuid"), Qt::CaseInsensitive)) return QLatin1Char('<') + text + QLatin1Char('>');
        return text;
    }
    if (editor == QLatin1String("number") || editor == QLatin1String("alias")) return text;
    if (text.size() >= 2 && text.startsWith(QLatin1Char('"')) && text.endsWith(QLatin1Char('"'))) text = text.mid(1, text.size() - 2);
    const bool numeric_menu = editor == QLatin1String("menu") && numeric_token(text);
    const bool wrap = !numeric_menu && (quoted || editor == QLatin1String("text") || editor == QLatin1String("file") || editor == QLatin1String("enum") || editor == QLatin1String("menu"));
    if (!wrap) return text;
    text.replace(QLatin1String("\\"), QLatin1String("\\\\"));
    text.replace(QLatin1String("\""), QLatin1String("\\\""));
    return QLatin1Char('"') + text + QLatin1Char('"');
}
