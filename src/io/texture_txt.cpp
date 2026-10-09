#include "io/texture_txt.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <stdexcept>

namespace {

const char* k_suffixes[] = {".texture.txt", ".texture", ".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds", ".hdr", ".txt"};
const char* k_roles[][2] = {
    {"_albedo", "albedo"}, {"_normal", "normal"}, {"_parameter", "parameter"}, {"_param", "parameter"},
    {"-albedo", "albedo"}, {"-normal", "normal"}, {"-parameter", "parameter"}, {".albedo", "albedo"},
    {".normal", "normal"}, {".parameter", "parameter"},
};
const char* k_order[] = {"Primary", "Alpha", "Compression", "NormalMapHint", "ModifyMap", "AlphaHint", "Tile", "UsageHint", "MipAlgorithm", "nonpoweroftwo"};
const char* k_known[] = {"Primary", "Alpha", "Compression", "NormalMapHint", "ModifyMap", "AlphaHint", "Tile", "UsageHint", "MipAlgorithm", "nonpoweroftwo"};

std::string lower_copy(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

bool ends_with(const std::string& s, const char* suf) {
    const size_t n = std::strlen(suf);
    return s.size() >= n && s.compare(s.size() - n, n, suf) == 0;
}

bool is_pot(int n) { return n > 0 && (n & (n - 1)) == 0; }

const char* allowed(const std::string& key, const std::string& value) {
    if (key == "Compression") return value == "none" || value == "dxt1" || value == "dxt3" || value == "dxt5" ? nullptr : "Compression";
    if (key == "NormalMapHint") return value == "none" || value == "normalmap" ? nullptr : "NormalMapHint";
    if (key == "ModifyMap") return value == "none" || value == "flipgreen" ? nullptr : "ModifyMap";
    if (key == "AlphaHint") return value == "opaque" || value == "semitransparent" || value == "masked" ? nullptr : "AlphaHint";
    if (key == "Tile") return value == "s" || value == "t" || value == "st" || value == "none" ? nullptr : "Tile";
    if (key == "UsageHint") return value == "albedo" || value == "normal" || value == "parameter" ? nullptr : "UsageHint";
    if (key == "MipAlgorithm") return value == "weight-by-alpha" || value == "no-weight-by-alpha" || value == "heavy-alpha" ? nullptr : "MipAlgorithm";
    return nullptr;
}

std::string key_of(const std::vector<std::pair<std::string, std::string>>& keys, const std::string& name) {
    for (const auto& row : keys)
        if (row.first == name) return row.second;
    return {};
}

}  // namespace

bool TextureReport::ok() const {
    for (const TexIssue& issue : issues)
        if (issue.level == "error") return false;
    return true;
}

std::string TextureReport::summary() const {
    int errors = 0;
    int warns = 0;
    for (const TexIssue& issue : issues) {
        if (issue.level == "error") ++errors;
        if (issue.level == "warn") ++warns;
    }
    if (errors) return "FAIL " + std::to_string(errors) + "e/" + std::to_string(warns) + "w";
    if (warns) return "OK* " + std::to_string(warns) + "w";
    return "OK";
}

std::string texture_stem(const std::string& name) {
    std::string s = name;
    const auto slash = s.find_last_of("/\\");
    if (slash != std::string::npos) s = s.substr(slash + 1);
    for (int pass = 0; pass < 4; ++pass) {
        const std::string low = lower_copy(s);
        bool matched = false;
        for (const char* suf : k_suffixes) {
            if (!ends_with(low, suf)) continue;
            s.resize(s.size() - std::strlen(suf));
            matched = true;
            break;
        }
        if (!matched) break;
    }
    return lower_copy(s);
}

std::pair<std::string, std::string> material_family(const std::string& stem) {
    const std::string s = texture_stem(stem);
    for (const auto& row : k_roles) {
        if (!ends_with(s, row[0])) continue;
        std::string fam = s.substr(0, s.size() - std::strlen(row[0]));
        if (fam.empty()) fam = s;
        return {fam, row[1]};
    }
    return {s, {}};
}

std::string pbr_set_label(const std::vector<std::string>& roles) {
    bool albedo = false;
    bool normal = false;
    bool parameter = false;
    bool any = false;
    for (const std::string& role : roles) {
        if (role == "albedo") albedo = any = true;
        if (role == "normal") normal = any = true;
        if (role == "parameter") parameter = any = true;
    }
    if (!any) return "plain";
    std::string missing;
    if (!albedo) missing += "albedo";
    if (!normal) missing += std::string(missing.empty() ? "" : "+") + "normal";
    if (!parameter) missing += std::string(missing.empty() ? "" : "+") + "parameter";
    if (missing.empty()) return "PBR";
    return "need " + missing;
}

std::string format_texture_txt(const std::vector<std::pair<std::string, std::string>>& keys) {
    std::ostringstream out;
    std::vector<std::string> seen;
    auto emit = [&](const std::string& key, const std::string& val) {
        if (val.empty()) return;
        out << key << '=' << val << '\n';
        seen.push_back(key);
    };
    for (const char* key : k_order) {
        for (const auto& row : keys)
            if (row.first == key) emit(row.first, row.second);
    }
    for (const auto& row : keys) {
        if (std::find(seen.begin(), seen.end(), row.first) != seen.end()) continue;
        emit(row.first, row.second);
    }
    return out.str();
}

std::vector<std::pair<std::string, std::string>> parse_texture_txt(const std::string& text) {
    std::vector<std::pair<std::string, std::string>> keys;
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const auto start = line.find_first_not_of(" \t");
        if (start == std::string::npos) continue;
        if (line[start] == '#' || (line[start] == '/' && start + 1 < line.size() && line[start + 1] == '/')) continue;
        const auto eq = line.find('=', start);
        if (eq == std::string::npos) continue;
        std::string key = line.substr(start, eq - start);
        std::string val = line.substr(eq + 1);
        auto trim = [](std::string& s) {
            const auto a = s.find_first_not_of(" \t");
            const auto b = s.find_last_not_of(" \t\r");
            s = a == std::string::npos ? std::string() : s.substr(a, b - a + 1);
        };
        trim(key);
        trim(val);
        keys.emplace_back(key, val);
    }
    return keys;
}

std::vector<std::pair<std::string, std::string>> keys_for_image(const std::string& primary, const std::string& alpha, const std::string& tile, const std::string& compression) {
    const auto fam = material_family(primary);
    std::vector<std::pair<std::string, std::string>> keys{{"Primary", primary}};
    if (!alpha.empty()) keys.emplace_back("Alpha", alpha);
    if (!compression.empty()) keys.emplace_back("Compression", compression);
    if (fam.second == "normal") keys.emplace_back("NormalMapHint", "normalmap");
    if (!tile.empty()) keys.emplace_back("Tile", tile);
    if (!fam.second.empty()) keys.emplace_back("UsageHint", fam.second);
    else if (fam.second == "normal") keys.emplace_back("UsageHint", "normal");
    return keys;
}

std::pair<int, int> image_size_header(const uint8_t* data, size_t size, const std::string& suffix) {
    if (data == nullptr || size < 24) return {0, 0};
    if (size >= 24 && std::memcmp(data, "\x89PNG\r\n\x1a\n", 8) == 0 && std::memcmp(data + 12, "IHDR", 4) == 0) {
        const int w = (data[16] << 24) | (data[17] << 16) | (data[18] << 8) | data[19];
        const int h = (data[20] << 24) | (data[21] << 16) | (data[22] << 8) | data[23];
        return {w, h};
    }
    if (data[0] == 'B' && data[1] == 'M' && size >= 26) {
        auto s32 = [&](size_t i) { return int(data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24)); };
        return {std::abs(s32(18)), std::abs(s32(22))};
    }
    const std::string low = lower_copy(suffix);
    if (ends_with(low, ".tga") && size >= 18) {
        const int w = data[12] | (data[13] << 8);
        const int h = data[14] | (data[15] << 8);
        if (w && h) return {w, h};
    }
    if (data[0] == 0xFF && data[1] == 0xD8) {
        size_t i = 2;
        while (i + 9 < size) {
            if (data[i] != 0xFF) {
                ++i;
                continue;
            }
            const uint8_t marker = data[i + 1];
            if (marker == 0xC0 || marker == 0xC1 || marker == 0xC2) {
                const int h = (data[i + 5] << 8) | data[i + 6];
                const int w = (data[i + 7] << 8) | data[i + 8];
                return {w, h};
            }
            if (marker == 0xD9) break;
            if (marker == 0xD8 || marker == 0x01 || (marker >= 0xD0 && marker <= 0xD7)) {
                i += 2;
                continue;
            }
            const int seglen = (data[i + 2] << 8) | data[i + 3];
            i += 2 + static_cast<size_t>(seglen);
        }
    }
    return {0, 0};
}

TextureReport check_texture_txt(const std::string& path, const std::string& text, int primary_w, int primary_h, bool primary_found) {
    TextureReport report;
    report.path = path;
    int line_no = 0;
    std::istringstream raw(text);
    std::string line;
    while (std::getline(raw, line)) {
        ++line_no;
        if (line.find(" =") != std::string::npos || line.find("= ") != std::string::npos)
            report.issues.push_back({"warn", "line " + std::to_string(line_no) + ": whitespace around '='"});
    }
    report.keys = parse_texture_txt(text);
    for (const auto& row : report.keys) {
        bool known = false;
        for (const char* key : k_known)
            if (row.first == key) known = true;
        if (!known) report.issues.push_back({"warn", "unknown key '" + row.first + "'"});
        if (const char* bad = allowed(row.first, row.second))
            report.issues.push_back({"error", std::string(bad) + "=" + row.second + " is not a Trainz value"});
    }
    const std::string primary = key_of(report.keys, "Primary");
    if (primary.empty()) report.issues.push_back({"error", "missing Primary="});
    else if (!primary_found) report.issues.push_back({"error", "Primary image missing: " + primary});
    else {
        report.width = primary_w;
        report.height = primary_h;
        const bool npot = key_of(report.keys, "nonpoweroftwo") == "1";
        if (primary_w > 0 && primary_h > 0 && !npot && (!is_pot(primary_w) || !is_pot(primary_h)))
            report.issues.push_back({"error", "Primary size " + std::to_string(primary_w) + "x" + std::to_string(primary_h) + " not power-of-two"});
    }
    return report;
}

std::string format_texture_report(const TextureReport& report) {
    std::ostringstream out;
    out << report.summary() << "  " << report.path << '\n';
    for (const auto& row : report.keys) out << "  " << row.first << '=' << row.second << '\n';
    for (const TexIssue& issue : report.issues) out << "  " << issue.level << ": " << issue.message << '\n';
    return out.str();
}

void check_texture_txt_logic() {
    if (texture_stem("body_albedo.texture.txt") != "body_albedo") throw std::runtime_error("stem");
    const auto fam = material_family("body_side_albedo.tga");
    if (fam.first != "body_side" || fam.second != "albedo") throw std::runtime_error("family");
    const auto keys = keys_for_image("body_normal.tga", "", "st", "");
    const std::string text = format_texture_txt(keys);
    if (text.find("Primary=body_normal.tga\n") == std::string::npos) throw std::runtime_error("primary");
    if (text.find("UsageHint=normal\n") == std::string::npos) throw std::runtime_error("usage");
    if (text.find("NormalMapHint=normalmap\n") == std::string::npos) throw std::runtime_error("normal");
    const auto parsed = parse_texture_txt("Primary = x.tga\nTile=st\n");
    if (parsed.size() != 2 || parsed[0].second != "x.tga") throw std::runtime_error("parse");
    const uint8_t png[] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 0, 0, 0, 13, 'I', 'H', 'D', 'R', 0, 0, 1, 0, 0, 0, 0, 128};
    const auto sz = image_size_header(png, sizeof(png), ".png");
    if (sz.first != 256 || sz.second != 128) throw std::runtime_error("png size");
    if (pbr_set_label({"albedo", "normal"}) != "need parameter") throw std::runtime_error("pbr label");
}
