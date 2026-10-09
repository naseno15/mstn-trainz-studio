#include "icons.h"
#include "res_path.h"

#include <QFileInfo>
#include <QFontDatabase>
#include <QUrl>
#include <QDir>

namespace {

struct Glyph {
    const char* name;
    char16_t code;
};

const Glyph kGlyphs[] = {
    {"home", 0xe88a},
    {"save", 0xe161},
    {"save_as", 0xeb60},
    {"undo", 0xe166},
    {"redo", 0xe15a},
    {"folder_open", 0xe2c8},
    {"refresh", 0xe5d5},
    {"close", 0xe5cd},
    {"delete", 0xe872},
    {"arrow_back", 0xe5c4},
    {"archive", 0xe149},
    {"unarchive", 0xe169},
    {"content_copy", 0xe14d},
    {"inventory_2", 0xe1a1},
    {"folder_zip", 0xeb2c},
    {"fullscreen", 0xe5d0},
    {"open_in_new", 0xe89e},
    {"swap_horiz", 0xe8d4},
    {"delete_sweep", 0xe16c},
    {"view_in_ar", 0xef4f},
    {"layers", 0xe53b},
    {"graphic_eq", 0xe1b8},
    {"tune", 0xe429},
    {"texture", 0xe421},
    {"upload_file", 0xe9fc},
    {"search", 0xe8b6},
    {"edit", 0xe3c9},
    {"publish", 0xe255},
    {"fact_check", 0xf0c5},
    {"chevron_left", 0xe5cb},
    {"chevron_right", 0xe5cc},
    {"history", 0xe889},
    {"file_open", 0xeaf3},
    {"clear", 0xe14c},
};

QString font_file() {
return res_icon_font();
}

}  // namespace

void load_material_icons() {
    const QString path = QFileInfo(font_file()).absoluteFilePath();
    if (!QFileInfo::exists(path)) return;
    QFontDatabase::addApplicationFont(path);
}

QString material_icon_family() { return QStringLiteral("Material Icons"); }

QString material_icon_url() {
    const QString path = QFileInfo(font_file()).absoluteFilePath();
    if (!QFileInfo::exists(path)) return {};
    return res_url(path).toString();
}

QString material_glyph(const char* name) {
    for (const Glyph& glyph : kGlyphs) {
        if (qstrcmp(glyph.name, name) == 0) return QString(QChar(glyph.code));
    }
    return {};
}
