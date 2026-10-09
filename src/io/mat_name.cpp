#include "io/mat_name.h"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <sstream>
#include <stdexcept>

namespace {

const char* k_effects[] = {"pbrmetal", "pbrmetalmasked", "pbrmetaldetail", "pbrmetalspec", "onetex", "glass", "clutter", "foliage"};

std::string lower_copy(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

int edit_distance(const std::string& a, const std::string& b) {
    std::vector<int> row(b.size() + 1);
    for (size_t j = 0; j <= b.size(); ++j) row[j] = static_cast<int>(j);
    for (size_t i = 1; i <= a.size(); ++i) {
        int prev = static_cast<int>(i - 1);
        row[0] = static_cast<int>(i);
        for (size_t j = 1; j <= b.size(); ++j) {
            const int cur = row[j];
            const int cost = a[i - 1] == b[j - 1] ? 0 : 1;
            row[j] = std::min(std::min(row[j] + 1, row[j - 1] + 1), prev + cost);
            prev = cur;
        }
    }
    return row[b.size()];
}

std::string closest_effect(const std::string& key, double cutoff) {
    std::string best;
    int best_d = 99;
    for (const char* effect : k_effects) {
        const int d = edit_distance(key, effect);
        const double score = 1.0 - double(d) / std::max<size_t>(key.size(), std::strlen(effect));
        if (score >= cutoff && d < best_d) {
            best_d = d;
            best = effect;
        }
    }
    return best;
}

std::string normalize_effect(std::string key) {
    key = lower_copy(key);
    key.erase(std::remove(key.begin(), key.end(), ' '), key.end());
    key.erase(std::remove(key.begin(), key.end(), '-'), key.end());
    if (key == "stdonetex" || key == "m.onetex" || key == "one_tex" || key == "onetext") return "onetex";
    if (key == "m.pbrmetal" || key == "pbr" || key == "metal") return "pbrmetal";
    for (const char* effect : k_effects)
        if (key == effect) return effect;
    return closest_effect(key, 0.72);
}

bool is_name_char(unsigned char c) { return std::isalnum(c) || c == '_' || c == '-' || c == '.'; }

}  // namespace

MatNameIssue check_mat_name(const std::string& name) {
    const auto trim_start = name.find_first_not_of(" \t");
    const std::string raw = trim_start == std::string::npos ? std::string() : name.substr(trim_start);
    if (raw.empty()) return {"", "empty", "", "empty material name"};
    const auto dup = raw.rfind('.');
    if (dup != std::string::npos && raw.size() - dup == 4) {
        bool digits = true;
        for (size_t i = dup + 1; i < raw.size(); ++i) digits = digits && std::isdigit(static_cast<unsigned char>(raw[i]));
        if (digits) {
            const MatNameIssue inner = check_mat_name(raw.substr(0, dup));
            const std::string suggested = inner.kind == "ok" ? raw.substr(0, dup) : (inner.suggested.empty() ? raw.substr(0, dup) : inner.suggested);
            return {raw, "blender_dup", suggested, "Blender duplicate suffix"};
        }
    }
    const auto m = raw.rfind(".m.");
    if (m != std::string::npos && m > 0) {
        const std::string stem = raw.substr(0, m);
        const std::string effect_raw = raw.substr(m + 3);
        const std::string effect = normalize_effect(effect_raw);
        if (effect.empty()) {
            const std::string guess = closest_effect(lower_copy(effect_raw), 0.55);
            const std::string tip = guess.empty() ? "pbrmetal" : guess;
            return {raw, "bad_effect", stem + ".m." + tip, "unknown effect '" + effect_raw + "'"};
        }
        const std::string canon = stem + ".m." + effect;
        if (canon != raw) return {raw, "bad_effect", canon, "normalize effect"};
        return {raw, "ok", "", "ok"};
    }
    std::string stem;
    for (char c : raw) {
        const unsigned char u = static_cast<unsigned char>(c);
        stem.push_back(std::isalnum(u) || c == '_' || c == '-' ? c : '_');
    }
    while (!stem.empty() && stem.front() == '_') stem.erase(stem.begin());
    while (!stem.empty() && stem.back() == '_') stem.pop_back();
    if (stem.empty()) stem = "material";
    return {raw, "missing_suffix", stem + ".m.pbrmetal", "missing .m."};
}

std::vector<std::string> list_material_names(const uint8_t* data, size_t size) {
    std::vector<std::string> names;
    auto add = [&](std::string name) {
        if (name.size() < 3 || name.size() > 96) return;
        if (std::find(names.begin(), names.end(), name) != names.end()) return;
        names.push_back(std::move(name));
    };
    std::string token;
    for (size_t i = 0; i < size; ++i) {
        const unsigned char c = data[i];
        if (is_name_char(c)) {
            token.push_back(static_cast<char>(c));
            continue;
        }
        if (token.find(".m.") != std::string::npos) add(token);
        token.clear();
    }
    if (token.find(".m.") != std::string::npos) add(token);
    const std::string text(reinterpret_cast<const char*>(data), size);
    const std::string marker = "Material::";
    for (size_t at = 0; (at = text.find(marker, at)) != std::string::npos; at += marker.size()) {
        size_t end = at + marker.size();
        while (end < text.size() && is_name_char(static_cast<unsigned char>(text[end]))) ++end;
        add(text.substr(at + marker.size(), end - (at + marker.size())));
    }
    return names;
}

std::string format_mat_report(const std::string& path, const std::vector<MatNameIssue>& issues) {
    std::ostringstream out;
    out << path << '\n';
    if (issues.empty()) out << "  no material names\n";
    for (const MatNameIssue& issue : issues) {
        out << "  " << issue.kind << "  " << issue.name;
        if (!issue.suggested.empty()) out << "  ->  " << issue.suggested;
        out << "  (" << issue.detail << ")\n";
    }
    return out.str();
}

void check_mat_name_logic() {
    const MatNameIssue ok = check_mat_name("body.m.pbrmetal");
    if (ok.kind != "ok") throw std::runtime_error("mat ok");
    const MatNameIssue miss = check_mat_name("body");
    if (miss.suggested != "body.m.pbrmetal") throw std::runtime_error("mat missing");
    const MatNameIssue typo = check_mat_name("lamp.m.pbrmetl");
    if (typo.suggested != "lamp.m.pbrmetal") throw std::runtime_error("mat typo");
    const char sample[] = "Material::glass.m.onetex\0body.m.pbrmetal";
    const auto names = list_material_names(reinterpret_cast<const uint8_t*>(sample), sizeof(sample) - 1);
    if (names.size() < 2) throw std::runtime_error("mat list");
}
