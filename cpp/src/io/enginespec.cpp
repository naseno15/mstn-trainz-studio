#include "enginespec.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <tuple>

namespace {

bool is_number(const std::string& token) {
    if (token.empty()) return false;
    char* end = nullptr;
    std::strtod(token.c_str(), &end);
    return end != token.c_str() && end && *end == '\0';
}

double as_number(const std::string& token) { return std::strtod(token.c_str(), nullptr); }

std::string trim(std::string text) {
    size_t begin = 0;
    while (begin < text.size() && std::isspace(static_cast<unsigned char>(text[begin]))) ++begin;
    size_t end = text.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1]))) --end;
    return text.substr(begin, end - begin);
}

struct Node {
    bool is_map = false;
    bool is_num = false;
    double num = 0;
    std::string text;
    std::map<std::string, Node> kids;
};

std::pair<std::string, std::string> split_kv(const std::string& line) {
    const std::string body = trim(line);
    const auto gap = body.find_first_of(" \t");
    if (gap == std::string::npos) return {body, {}};
    return {body.substr(0, gap), trim(body.substr(gap + 1))};
}

std::pair<Node, size_t> parse_block(const std::vector<std::string>& lines, size_t idx) {
    Node node;
    node.is_map = true;
    ++idx;
    while (idx < lines.size()) {
        const std::string token = trim(lines[idx]);
        if (token == "}") return {node, idx + 1};
        if (token.empty() || token == "{") {
            ++idx;
            continue;
        }
        auto [key, rest] = split_kv(lines[idx]);
        if (rest == "{") {
            auto nested = parse_block(lines, idx);
            node.kids[key] = nested.first;
            idx = nested.second;
            continue;
        }
        if (rest.empty()) {
            const std::string next = idx + 1 < lines.size() ? trim(lines[idx + 1]) : "";
            if (next == "{") {
                auto nested = parse_block(lines, idx + 1);
                node.kids[key] = nested.first;
                idx = nested.second;
                continue;
            }
            ++idx;
            continue;
        }
        if (!rest.empty() && rest.front() == '"') {
            std::string value = rest.substr(1);
            if (!value.empty() && value.back() == '"') value.pop_back();
            Node child;
            child.text = value;
            node.kids[key] = child;
            ++idx;
            continue;
        }
        const std::string word = split_kv(rest).first.empty() ? rest : split_kv(rest).first;
        Node child;
        if (is_number(word)) {
            child.is_num = true;
            child.num = as_number(word);
        }
        child.text = word;
        node.kids[key] = child;
        ++idx;
    }
    return {node, idx};
}

Node parse_root(const std::string& text) {
    std::vector<std::string> lines;
    std::string line;
    for (size_t i = 0; i <= text.size(); ++i) {
        if (i == text.size() || text[i] == '\n') {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            lines.push_back(line);
            line.clear();
        } else {
            line.push_back(text[i]);
        }
    }
    Node root;
    root.is_map = true;
    for (size_t idx = 0; idx < lines.size();) {
        const std::string stripped = trim(lines[idx]);
        if (stripped.empty() || stripped == "{") {
            ++idx;
            continue;
        }
        if (stripped.size() > 1 && stripped.back() == '{') {
            const std::string key = trim(stripped.substr(0, stripped.size() - 1));
            auto nested = parse_block(lines, idx);
            root.kids[key] = nested.first;
            idx = nested.second;
            continue;
        }
        auto [key, rest] = split_kv(lines[idx]);
        if (rest == "{") {
            auto nested = parse_block(lines, idx);
            root.kids[key] = nested.first;
            idx = nested.second;
            continue;
        }
        if (rest.empty()) {
            const std::string next = idx + 1 < lines.size() ? trim(lines[idx + 1]) : "";
            if (next == "{") {
                auto nested = parse_block(lines, idx + 1);
                root.kids[key] = nested.first;
                idx = nested.second;
                continue;
            }
            ++idx;
            continue;
        }
        if (!rest.empty() && rest.front() == '"') {
            std::string value = rest.substr(1);
            if (!value.empty() && value.back() == '"') value.pop_back();
            Node child;
            child.text = value;
            root.kids[key] = child;
            ++idx;
            continue;
        }
        Node child;
        const std::string word = split_kv(rest).first;
        if (is_number(word)) {
            child.is_num = true;
            child.num = as_number(word);
        }
        child.text = word;
        root.kids[key] = child;
        ++idx;
    }
    return root;
}

double round1(double value) { return std::round(value * 10.0) / 10.0; }

std::string fmt1(double value) {
    const double rounded = round1(value);
    if (std::abs(rounded - std::round(rounded)) < 1e-9) return std::to_string(static_cast<int>(std::llround(rounded)));
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.1f", rounded);
    return buf;
}

std::pair<double, double> round_point(double meters_per_second, double kilonewtons) {
    return {round1(meters_per_second * 3.6) / 3.6, round1(kilonewtons)};
}

void read_throttle(const Node& node, EngineSpec& spec) {
    for (const auto& [notch_key, block] : node.kids) {
        char* end = nullptr;
        const long notch = std::strtol(notch_key.c_str(), &end, 10);
        if (end == notch_key.c_str() || !block.is_map) continue;
        std::vector<std::pair<double, double>> points;
        for (const auto& [speed_key, force] : block.kids) {
            if (!is_number(speed_key) || !force.is_num) continue;
            points.push_back(round_point(as_number(speed_key), force.num));
        }
        std::sort(points.begin(), points.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        spec.throttle[static_cast<int>(notch)] = points;
    }
}

void read_block(const Node& node, std::map<std::string, double>& out) {
    for (const auto& [key, value] : node.kids) {
        if (value.is_num) out[key] = value.num;
        else if (is_number(value.text)) out[key] = as_number(value.text);
    }
}

const char* kBlocks[] = {"flowsize", "volume", "pressure", "mass", "motor", "throttle-power"};

bool known_block(const std::string& key) {
    for (const char* name : kBlocks) {
        if (key == name) return true;
    }
    return false;
}

std::string fmt_pad(const std::string& key, const std::string& value, int width) {
    std::string line = key;
    if (static_cast<int>(line.size()) < width) line.append(static_cast<size_t>(width - line.size()), ' ');
    line += value;
    return line;
}

void write_block(std::string& out, const std::string& name, const std::map<std::string, std::string>& rows, int indent) {
    const std::string pad(static_cast<size_t>(indent) * 2, ' ');
    out += pad + name + "\n" + pad + "{\n";
    for (const auto& [key, value] : rows) out += pad + "  " + fmt_pad(key, value, 38) + "\n";
    out += pad + "}\n\n";
}

}  // namespace

std::map<std::string, double>& EngineSpec::block(const std::string& name) { return blocks[name]; }

const std::map<std::string, double>* EngineSpec::find_block(const std::string& name) const {
    const auto it = blocks.find(name);
    return it == blocks.end() ? nullptr : &it->second;
}

EngineSpec parse_enginespec(const std::string& text) {
    const Node root = parse_root(text);
    EngineSpec spec;
    for (const auto& [key, value] : root.kids) {
        if (key == "throttle-power" && value.is_map) read_throttle(value, spec);
        else if (known_block(key) && value.is_map) read_block(value, spec.blocks[key]);
        else if (!value.is_map) spec.header[key] = value.text;
    }
    return spec;
}

std::string write_enginespec(const EngineSpec& spec) {
    std::string out = "\n";
    const char* order[] = {
        "username", "category-region", "category-era", "kind", "author", "license", "trainz-build", "category-class",
        "description", "flowsize", "volume", "pressure", "mass", "motor", "throttle-power", "kuid",
    };
    std::map<std::string, bool> seen;
    const auto write_key = [&](const std::string& key) {
        seen[key] = true;
        if (key == "throttle-power") {
            std::map<std::string, std::string> notches;
            for (const auto& [notch, points] : spec.throttle) {
                std::map<std::string, std::string> rows;
                for (const auto& point : points) rows[fmt1(point.first)] = fmt1(point.second);
                std::string body;
                write_block(body, std::to_string(notch), rows, 1);
                notches[std::to_string(notch)] = body;
            }
            out += "throttle-power\n{\n";
            for (const auto& [notch, body] : notches) out += body;
            out += "}\n\n";
            return;
        }
        const auto block = spec.blocks.find(key);
        if (block != spec.blocks.end()) {
            std::map<std::string, std::string> rows;
            for (const auto& [name, value] : block->second) rows[name] = fmt_native(value);
            write_block(out, key, rows, 0);
            return;
        }
        const auto header = spec.header.find(key);
        if (header == spec.header.end()) return;
        const std::string& value = header->second;
        if (value.find(' ') != std::string::npos) out += fmt_pad(key, "\"" + value + "\"", 40) + "\n\n";
        else out += fmt_pad(key, value, 40) + "\n\n";
    };
    for (const char* key : order) write_key(key);
    for (const auto& [key, _] : spec.header) {
        if (!seen[key]) write_key(key);
    }
    for (const auto& [key, _] : spec.blocks) {
        if (!seen[key]) write_key(key);
    }
    if (out.empty() || out.back() != '\n') out += '\n';
    return out;
}

bool looks_like_enginespec(const std::string& text) {
    const EngineSpec spec = parse_enginespec(text);
    const auto kind = spec.header.find("kind");
    if (kind != spec.header.end()) {
        std::string low = kind->second;
        for (char& c : low) {
            if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
        }
        if (low == "enginespec") return true;
    }
    return !spec.throttle.empty();
}

bool edit_throttle_point(EngineSpec& spec, int notch, int index, int column, const std::string& text) {
    auto it = spec.throttle.find(notch);
    if (it == spec.throttle.end() || index < 0 || index >= static_cast<int>(it->second.size())) return false;
    std::string token = trim(text);
    const auto comma = token.find(',');
    if (comma != std::string::npos) token.erase(comma, 1);
    if (!is_number(token)) return false;
    const double value = as_number(token);
    auto [speed, force] = it->second[static_cast<size_t>(index)];
    if (column == 0) std::tie(speed, force) = round_point(std::max(0.0, value / 3.6), force);
    else std::tie(speed, force) = round_point(speed, std::max(0.0, value));
    it->second[static_cast<size_t>(index)] = {speed, force};
    std::sort(it->second.begin(), it->second.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    return true;
}

void add_throttle_point(EngineSpec& spec, int notch) {
    auto& points = spec.throttle[notch];
    const double speed = points.empty() ? 0.0 : points.back().first + 2.0;
    const double force = points.empty() ? 0.0 : points.back().second;
    points.push_back(round_point(speed, force));
}

void delete_throttle_point(EngineSpec& spec, int notch, int index) {
    auto it = spec.throttle.find(notch);
    if (it == spec.throttle.end() || index < 0 || index >= static_cast<int>(it->second.size())) return;
    it->second.erase(it->second.begin() + index);
}

std::string fmt_kmh(double meters_per_second) { return fmt1(meters_per_second * 3.6); }
std::string fmt_kn(double kilonewtons) { return fmt1(kilonewtons); }

std::string fmt_native(double value) {
    if (std::abs(value) < 1e-15) return "0";
    if (std::abs(value - std::round(value)) < 1e-9) return std::to_string(static_cast<long long>(std::llround(value)));
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.8f", value);
    std::string text = buf;
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return text.empty() ? "0" : text;
}

std::string fmt_bar(double native) {
    const double bar = native * 1000.0;
    if (std::abs(bar) < 1e-12) return "0";
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.3f", bar);
    std::string text = buf;
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return text.empty() ? "0" : text;
}

std::string fmt_kpa(double native) {
    const double kpa = native * 1000.0 * 100.0;
    if (std::abs(kpa) < 1e-9) return "0";
    if (std::abs(kpa - std::round(kpa)) < 0.05) return std::to_string(static_cast<long long>(std::llround(kpa)));
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.1f", kpa);
    return buf;
}

double native_from_bar(double bar) { return bar / 1000.0; }
double native_from_kpa(double kpa) { return kpa / 100.0 / 1000.0; }
