#include "io/lm_txt.h"

#include <algorithm>
#include <cmath>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace {

std::string fmt_g(double v) {
    std::ostringstream out;
    out.setf(std::ios::fmtflags(0), std::ios::floatfield);
    out.precision(8);
    out << v;
    return out.str();
}

}  // namespace

LmFile parse_lm_txt(const std::string& text) {
    LmFile lm;
    const std::regex version_re(R"(version\s+(\S+))", std::regex::icase);
    const std::regex kv_re(R"((offset|calcPoint|multiplier|animationCutOff|renderCutOff|attachmentCutOff)\s*=\s*([^;]+);)", std::regex::icase);
    const std::regex mesh_re(R"lm(mesh\s*\(\s*"([^"]+)"\s*\)\s*\{\s*name\s*=\s*"([^"]+)"\s*;?\s*\})lm", std::regex::icase);
    std::smatch match;
    if (std::regex_search(text, match, version_re)) lm.version = match[1].str();
    for (std::sregex_iterator it(text.begin(), text.end(), kv_re), end; it != end; ++it) {
        std::string key = (*it)[1].str();
        for (char& c : key) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        const std::string raw = (*it)[2].str();
        if (key == "calcpoint") {
            lm.calc_point = raw;
            const auto a = lm.calc_point.find_first_not_of(" \t");
            const auto b = lm.calc_point.find_last_not_of(" \t");
            if (a != std::string::npos) lm.calc_point = lm.calc_point.substr(a, b - a + 1);
            continue;
        }
        try {
            const double val = std::stod(raw);
            if (key == "offset") lm.offset = val;
            else if (key == "multiplier") lm.multiplier = val;
            else if (key == "animationcutoff") lm.animation_cutoff = val;
            else if (key == "rendercutoff") lm.render_cutoff = val;
            else if (key == "attachmentcutoff") lm.attachment_cutoff = val;
        } catch (const std::exception&) {
        }
    }
    for (std::sregex_iterator it(text.begin(), text.end(), mesh_re), end; it != end; ++it)
        lm.meshes.push_back({std::stod((*it)[1].str()), (*it)[2].str()});
    std::sort(lm.meshes.begin(), lm.meshes.end(), [](const LmMesh& a, const LmMesh& b) { return a.width < b.width; });
    return lm;
}

std::string format_lm_txt(const LmFile& lm) {
    if (lm.meshes.empty()) throw std::runtime_error("LM needs at least one mesh");
    std::vector<LmMesh> meshes = lm.meshes;
    std::sort(meshes.begin(), meshes.end(), [](const LmMesh& a, const LmMesh& b) { return a.width < b.width; });
    std::ostringstream out;
    out << "version " << lm.version << '\n';
    out << "offset = " << fmt_g(lm.offset) << ";\n";
    out << "calcPoint = " << lm.calc_point << ";\n";
    out << "multiplier = " << fmt_g(lm.multiplier) << ";\n";
    out << "animationCutOff = " << fmt_g(lm.animation_cutoff) << ";\n";
    out << "renderCutOff = " << fmt_g(lm.render_cutoff) << ";\n";
    out << "attachmentCutOff = " << fmt_g(lm.attachment_cutoff) << ";\n\n";
    for (const LmMesh& mesh : meshes) {
        out << "mesh(\"" << fmt_g(mesh.width) << "\")\n{\n  name=\"" << mesh.name << "\";\n}\n";
    }
    return out.str();
}

void check_lm_txt_logic() {
    const LmFile lm = parse_lm_txt("version 1.0\noffset = 0.02;\ncalcPoint = near;\nmesh(\"0.2\") { name=\"far.im\"; }\nmesh(\"1\") { name=\"near.im\"; }\n");
    if (lm.calc_point != "near" || std::abs(lm.offset - 0.02) > 1e-9) throw std::runtime_error("lm parse");
    if (lm.meshes.size() != 2 || lm.meshes[0].name != "far.im") throw std::runtime_error("lm sort");
    const std::string text = format_lm_txt(lm);
    if (text.find("name=\"far.im\"") == std::string::npos || text.find("calcPoint = near;") == std::string::npos) throw std::runtime_error("lm format");
}
