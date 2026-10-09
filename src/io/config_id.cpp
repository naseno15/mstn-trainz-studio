#include "config_id.h"

#include "chump.h"
#include "kuid.h"
#include "lzss.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace {

std::string trim(std::string text) {
    size_t begin = 0;
    while (begin < text.size() && std::isspace(static_cast<unsigned char>(text[begin]))) ++begin;
    size_t end = text.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1]))) --end;
    return text.substr(begin, end - begin);
}

std::string strip_quotes(std::string text) {
    text = trim(text);
    while (!text.empty() && text.front() == '"') text.erase(text.begin());
    while (!text.empty() && text.back() == '"') text.pop_back();
    return text;
}

std::string lower_copy(std::string text) {
    for (char& c : text) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return text;
}

bool starts_key(const std::string& body, const char* key, std::string& rest) {
    const std::string low = lower_copy(body);
    const size_t n = std::strlen(key);
    if (low.compare(0, n, key) != 0) return false;
    if (body.size() == n) {
        rest.clear();
        return true;
    }
    if (!std::isspace(static_cast<unsigned char>(body[n]))) return false;
    rest = strip_quotes(body.substr(n));
    return true;
}

std::string credit_body(const std::string& line) {
    const auto pos = line.find("<NULL>");
    if (pos == std::string::npos) return trim(line);
    size_t i = pos + 6;
    while (i < line.size() && std::isspace(static_cast<unsigned char>(line[i]))) ++i;
    if (i < line.size() && line[i] == ':') ++i;
    return trim(line.substr(i));
}

std::string fmt_float(float value) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6g", static_cast<double>(value));
    std::string text = buf;
    if (text.find('.') == std::string::npos && text.find('e') == std::string::npos && text.find('E') == std::string::npos) {
        text += ".0";
    }
    return text;
}

std::string find_kuid(const std::string& text) {
    const auto at = lower_copy(text).find("<kuid");
    if (at == std::string::npos) return {};
    const auto end = text.find('>', at);
    if (end == std::string::npos) return {};
    return text.substr(at, end - at + 1);
}

void read_text_config(const std::string& text, ConfigIdentity& out) {
    std::string line;
    for (size_t i = 0; i <= text.size(); ++i) {
        if (i == text.size() || text[i] == '\n') {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            const std::string body = credit_body(line);
            std::string rest;
            if (starts_key(body, "author", rest)) out.author = rest;
            else if (starts_key(body, "trainz-build", rest)) out.build = rest;
            else if (starts_key(trim(line), "username", rest)) out.username = rest;
            line.clear();
        } else {
            line.push_back(text[i]);
        }
    }
    out.kuid = find_kuid(text);
}

std::string tag_text(const ChumpTag& tag) {
    if (tag.type == ChumpType::Text) return strip_quotes(tag.text);
    if (tag.type == ChumpType::Int) {
        std::string out;
        for (size_t i = 0; i < tag.ints.size(); ++i) {
            if (i) out += ',';
            out += std::to_string(tag.ints[i]);
        }
        return out;
    }
    if (tag.type == ChumpType::Float && !tag.floats.empty()) return fmt_float(tag.floats[0]);
    if (tag.type == ChumpType::Kuid) return bytes_to_kuid(tag.raw.data(), tag.raw.size());
    return {};
}

}  // namespace

ConfigIdentity config_identity(const uint8_t* data, size_t size) {
    ConfigIdentity out;
    if (data == nullptr || size == 0) return out;
    if (size >= 4 && std::memcmp(data, "ACS$", 4) == 0) {
        if (size < 16) return out;
        const ChumpFile file = read_chump(data, size);
        for (const ChumpTag& tag : file.root) {
            const std::string name = lower_copy(tag.name);
            if (tag.type == ChumpType::Soup) continue;
            if (name == "author" && out.author.empty()) out.author = tag_text(tag);
            else if (name == "trainz-build" && out.build.empty()) out.build = tag_text(tag);
            else if (name == "username" && out.username.empty()) out.username = tag_text(tag);
            else if (name == "kuid" && out.kuid.empty()) out.kuid = tag_text(tag);
        }
        return out;
    }
    read_text_config(decode_asset_text(data, size), out);
    return out;
}

std::string author_label(const std::string& author, const std::string& build) {
    const std::string name = trim(author);
    const std::string ver = trim(build);
    if (name.empty() || (!ver.empty() && name == ver)) return {};
    size_t dot = name.find('.');
    if (dot != std::string::npos && dot > 0 && dot + 1 < name.size()) {
        bool digits = true;
        for (size_t i = 0; i < name.size(); ++i) {
            if (i == dot) continue;
            if (!std::isdigit(static_cast<unsigned char>(name[i]))) digits = false;
        }
        if (digits && name.find('.', dot + 1) == std::string::npos) return {};
    }
    return name;
}

LibraryRow library_row_from_config(const uint8_t* data, size_t size) {
    const ConfigIdentity id = config_identity(data, size);
    LibraryRow row;
    row.name = id.username;
    row.kuid = id.kuid;
    row.author = author_label(id.author, id.build);
    row.build = id.build;
    return row;
}
