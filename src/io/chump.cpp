#include "chump.h"

#include "bin.h"
#include "kuid.h"

#include <cstdio>
#include <deque>
#include <regex>
#include <sstream>

static std::string utf8_lossy(const uint8_t* data, size_t size) {
    std::string out;
    out.reserve(size);
    for (size_t i = 0; i < size;) {
        uint8_t c = data[i];
        size_t need = 1;
        if ((c & 0x80) == 0) need = 1;
        else if ((c & 0xE0) == 0xC0) need = 2;
        else if ((c & 0xF0) == 0xE0) need = 3;
        else if ((c & 0xF8) == 0xF0) need = 4;
        else {
            out.append("\xEF\xBF\xBD");
            ++i;
            continue;
        }
        if (i + need > size) {
            out.append("\xEF\xBF\xBD");
            break;
        }
        bool ok = true;
        for (size_t k = 1; k < need; ++k) {
            if ((data[i + k] & 0xC0) != 0x80) ok = false;
        }
        if (!ok) {
            out.append("\xEF\xBF\xBD");
            ++i;
            continue;
        }
        out.append(reinterpret_cast<const char*>(data + i), need);
        i += need;
    }
    return out;
}

static ChumpTag read_tag(const uint8_t* data, size_t limit, size_t& pos) {
    if (pos + 5 > limit) throw std::runtime_error("truncated chump tag");
    uint32_t pair_len = rd_u32(data + pos);
    pos += 4;
    size_t pair_end = pos + pair_len;
    if (pair_end > limit) pair_end = limit;
    uint8_t name_size = data[pos++];
    if (name_size < 1 || pos + name_size > pair_end) throw std::runtime_error("bad chump tag name");
    std::string name = utf8_lossy(data + pos, name_size - 1);
    pos += name_size;
    if (pos >= pair_end) {
        ChumpTag tag;
        tag.name = name;
        tag.type = ChumpType::Null;
        pos = pair_end;
        return tag;
    }
    auto type = static_cast<ChumpType>(data[pos++]);
    const uint8_t* payload = data + pos;
    size_t payload_len = pair_end - pos;
    ChumpTag tag;
    tag.name = name;
    tag.type = type;
    if (type == ChumpType::Soup) {
        size_t cpos = 0;
        while (cpos < payload_len) tag.children.push_back(read_tag(payload, payload_len, cpos));
    } else if (type == ChumpType::Int) {
        for (size_t i = 0; i + 4 <= payload_len; i += 4) tag.ints.push_back(rd_i32(payload + i));
    } else if (type == ChumpType::Float) {
        for (size_t i = 0; i + 4 <= payload_len; i += 4) tag.floats.push_back(rd_f32(payload + i));
    } else if (type == ChumpType::Text) {
        size_t n = 0;
        while (n < payload_len && payload[n] != 0) ++n;
        tag.text = utf8_lossy(payload, n);
    } else if (type == ChumpType::Null) {
        tag.type = ChumpType::Null;
    } else if (type == ChumpType::Kuid) {
        if (payload_len < 8) throw std::runtime_error("kuid tag too short");
        tag.raw.assign(payload, payload + 8);
    } else {
        tag.raw.assign(payload, payload + payload_len);
    }
    pos = pair_end;
    return tag;
}

ChumpFile read_chump(const uint8_t* data, size_t size) {
    need(size, 16, "not a chump (missing ACS$)");
    if (std::memcmp(data, "ACS$", 4) != 0) throw std::runtime_error("not a chump (missing ACS$)");
    ChumpFile file;
    file.version = rd_u32(data + 4);
    file.reserved = rd_u32(data + 8);
    uint32_t length = rd_u32(data + 12);
    size_t end = 16 + length;
    if (end > size) end = size;
    size_t pos = 16;
    while (pos < end) file.root.push_back(read_tag(data, end, pos));
    return file;
}

static void encode_tag(const ChumpTag& tag, std::vector<uint8_t>& out) {
    std::string name_b = tag.name;
    name_b.push_back('\0');
    if (name_b.size() > 255) throw std::runtime_error("tag name too long");
    std::vector<uint8_t> payload;
    if (tag.type == ChumpType::Soup) {
        for (const ChumpTag& child : tag.children) encode_tag(child, payload);
    } else if (tag.type == ChumpType::Int) {
        for (int32_t value : tag.ints) wr_i32(payload, value);
    } else if (tag.type == ChumpType::Float) {
        for (float value : tag.floats) wr_f32(payload, value);
    } else if (tag.type == ChumpType::Text) {
        payload.insert(payload.end(), tag.text.begin(), tag.text.end());
        payload.push_back(0);
    } else if (tag.type == ChumpType::Null) {
    } else if (tag.type == ChumpType::Kuid) {
        if (tag.raw.size() < 8) throw std::runtime_error("kuid tag too short");
        payload.insert(payload.end(), tag.raw.begin(), tag.raw.begin() + 8);
    } else {
        payload.insert(payload.end(), tag.raw.begin(), tag.raw.end());
    }
    uint32_t pair_len = static_cast<uint32_t>(name_b.size() + 2 + payload.size());
    wr_u32(out, pair_len);
    out.push_back(static_cast<uint8_t>(name_b.size()));
    out.insert(out.end(), name_b.begin(), name_b.end());
    out.push_back(static_cast<uint8_t>(tag.type));
    out.insert(out.end(), payload.begin(), payload.end());
}

std::vector<uint8_t> encode_chump(const ChumpFile& file) {
    std::vector<uint8_t> body;
    for (const ChumpTag& tag : file.root) encode_tag(tag, body);
    std::vector<uint8_t> out;
    out.insert(out.end(), {'A', 'C', 'S', '$'});
    wr_u32(out, file.version);
    wr_u32(out, file.reserved);
    wr_u32(out, static_cast<uint32_t>(body.size()));
    out.insert(out.end(), body.begin(), body.end());
    return out;
}

const ChumpTag* find_tag(const std::vector<ChumpTag>& tags, const std::string& name) {
    for (const ChumpTag& tag : tags) {
        if (tag.name == name) return &tag;
    }
    return nullptr;
}

static std::string pad_name(const std::string& indent, const std::string& name) {
    const std::string left = indent + name;
    const int spaces = 40 - static_cast<int>(left.size());
    if (spaces < 2) return left + "  ";
    return left + std::string(static_cast<size_t>(spaces), ' ');
}

static std::string float_token(float value) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%g", static_cast<double>(value));
    std::string text = buf;
    const auto lower = text;
    if (text.find('.') == std::string::npos && lower.find('e') == std::string::npos && lower.find('E') == std::string::npos) text += ".0";
    return text;
}

static void write_text_tag(std::vector<std::string>& lines, const ChumpTag& tag, int depth) {
    const std::string indent(static_cast<size_t>(depth) * 2, ' ');
    if (tag.type == ChumpType::Null || tag.type == ChumpType::Raw) return;
    if (tag.type == ChumpType::Soup) {
        lines.push_back(indent + tag.name);
        lines.push_back(indent + "{");
        for (const ChumpTag& child : tag.children) write_text_tag(lines, child, depth + 1);
        lines.push_back(indent + "}");
        return;
    }
    const std::string prefix = pad_name(indent, tag.name);
    if (tag.type == ChumpType::Text) {
        lines.push_back(prefix + "\"" + tag.text + "\"");
        return;
    }
    if (tag.type == ChumpType::Int) {
        std::string joined;
        for (size_t i = 0; i < tag.ints.size(); ++i) {
            if (i) joined += ',';
            joined += std::to_string(tag.ints[i]);
        }
        lines.push_back(prefix + joined);
        return;
    }
    if (tag.type == ChumpType::Float) {
        std::string joined;
        for (size_t i = 0; i < tag.floats.size(); ++i) {
            if (i) joined += ',';
            joined += float_token(tag.floats[i]);
        }
        lines.push_back(prefix + joined);
        return;
    }
    if (tag.type == ChumpType::Kuid && tag.raw.size() >= 8) lines.push_back(prefix + bytes_to_kuid(tag.raw.data(), tag.raw.size()));
}

std::string chump_to_text(const ChumpFile& file) {
    std::vector<std::string> lines;
    for (size_t i = 0; i < file.root.size(); ++i) {
        if (file.root[i].type == ChumpType::Soup && i > 0) lines.emplace_back();
        write_text_tag(lines, file.root[i], 0);
    }
    std::string out;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (i) out += '\n';
        out += lines[i];
    }
    while (!out.empty() && (out.back() == '\n' || out.back() == '\r' || out.back() == ' ')) out.pop_back();
    out += '\n';
    return out;
}

static bool token_int(const std::string& text) {
    static const std::regex re(R"(^[-+]?\d+$)");
    return std::regex_match(text, re);
}

static bool token_float(const std::string& text) {
    static const std::regex re(R"(^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$)");
    return std::regex_match(text, re);
}

static std::string trim_copy(std::string text) {
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t' || text.front() == '\r')) text.erase(text.begin());
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t' || text.back() == '\r')) text.pop_back();
    return text;
}

static bool name_only(const std::string& text) {
    if (text.empty()) return false;
    for (char c : text) {
        const bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-';
        if (!ok) return false;
    }
    return true;
}

static void push_value(std::deque<ChumpTag>& list, const std::string& name, const std::string& value) {
    ChumpTag tag;
    tag.name = name;
    const auto lower = value.size() >= 5 ? value.substr(0, 5) : value;
    std::string head = lower;
    for (char& c : head) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    if (head.rfind("<kuid", 0) == 0) {
        const auto raw = parse_kuid_string(value);
        if (!raw) throw std::runtime_error("bad kuid: " + value);
        tag.type = ChumpType::Kuid;
        tag.raw = *raw;
        list.push_back(std::move(tag));
        return;
    }
    if (value.find(',') != std::string::npos) {
        std::vector<std::string> parts;
        std::stringstream stream(value);
        std::string part;
        while (std::getline(stream, part, ',')) {
            part = trim_copy(part);
            if (!part.empty()) parts.push_back(part);
        }
        bool all_int = !parts.empty();
        bool all_float = !parts.empty();
        for (const std::string& one : parts) {
            all_int = all_int && token_int(one);
            all_float = all_float && token_float(one);
        }
        if (all_int) {
            tag.type = ChumpType::Int;
            for (const std::string& one : parts) tag.ints.push_back(std::stoi(one));
            list.push_back(std::move(tag));
            return;
        }
        if (all_float) {
            tag.type = ChumpType::Float;
            for (const std::string& one : parts) tag.floats.push_back(std::stof(one));
            list.push_back(std::move(tag));
            return;
        }
    }
    if (token_float(value)) {
        tag.type = ChumpType::Float;
        tag.floats.push_back(std::stof(value));
        list.push_back(std::move(tag));
        return;
    }
    if (token_int(value)) {
        tag.type = ChumpType::Int;
        tag.ints.push_back(std::stoi(value));
        list.push_back(std::move(tag));
        return;
    }
    tag.type = ChumpType::Text;
    tag.text = value;
    list.push_back(std::move(tag));
}

static void copy_level(const std::deque<ChumpTag>& from, std::vector<ChumpTag>& into) {
    for (const ChumpTag& tag : from) {
        ChumpTag copy = tag;
        copy.children.clear();
        copy_level(std::deque<ChumpTag>(tag.children.begin(), tag.children.end()), copy.children);
        into.push_back(std::move(copy));
    }
}

ChumpFile text_to_chump(const std::string& text) {
    std::deque<std::deque<ChumpTag>> levels;
    levels.emplace_back();
    std::vector<std::deque<ChumpTag>*> stack{&levels.back()};
    std::string pending;
    std::string multiline_name;
    std::string multiline_value;
    std::stringstream stream(text);
    std::string line;
    while (std::getline(stream, line)) {
        if (!multiline_name.empty()) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            const std::string trimmed = trim_copy(line);
            const bool closes = !trimmed.empty() && trimmed.back() == '"';
            std::string part = line;
            if (closes) {
                const size_t quote = part.find_last_of('"');
                part.erase(quote);
            }
            multiline_value += '\n';
            multiline_value += part;
            if (closes) {
                push_value(*stack.back(), multiline_name, multiline_value);
                multiline_name.clear();
                multiline_value.clear();
            }
            continue;
        }
        line = trim_copy(line);
        if (line.empty()) continue;
        if (line == "}") {
            if (stack.size() <= 1) throw std::runtime_error("extra '}' in chump text");
            auto* kids = stack.back();
            stack.pop_back();
            stack.back()->back().children.assign(kids->begin(), kids->end());
            pending.clear();
            continue;
        }
        if (line == "{") {
            if (pending.empty()) throw std::runtime_error("unexpected '{' in chump text");
            levels.emplace_back();
            ChumpTag soup;
            soup.name = pending;
            soup.type = ChumpType::Soup;
            stack.back()->push_back(std::move(soup));
            stack.push_back(&levels.back());
            pending.clear();
            continue;
        }
        if (line.size() > 2 && line.ends_with(" {")) {
            levels.emplace_back();
            ChumpTag soup;
            soup.name = trim_copy(line.substr(0, line.size() - 2));
            soup.type = ChumpType::Soup;
            stack.back()->push_back(std::move(soup));
            stack.push_back(&levels.back());
            pending.clear();
            continue;
        }
        if (name_only(line)) {
            pending = line;
            continue;
        }
        const auto gap = line.find_first_of(" \t");
        if (gap == std::string::npos) throw std::runtime_error("bad chump line");
        const std::string name = line.substr(0, gap);
        std::string value = trim_copy(line.substr(gap + 1));
        if (!value.empty() && value.front() == '"' && (value.size() == 1 || value.back() != '"')) {
            multiline_name = name;
            multiline_value = value.substr(1);
            pending.clear();
            continue;
        }
        if (value.size() >= 2 && value.front() == '"' && value.back() == '"') value = value.substr(1, value.size() - 2);
        push_value(*stack.back(), name, value);
        pending.clear();
    }
    if (!multiline_name.empty()) throw std::runtime_error("unclosed quote in chump text");
    if (stack.size() != 1) throw std::runtime_error("unclosed '{' in chump text");
    ChumpFile file;
    copy_level(levels.front(), file.root);
    return file;
}
