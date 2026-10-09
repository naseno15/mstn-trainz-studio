#pragma once

#include <string>
#include <vector>

struct LmMesh {
    double width = 1;
    std::string name;
};

struct LmFile {
    std::string version = "1.0";
    double offset = 0.01;
    std::string calc_point = "center";
    double multiplier = 1;
    double animation_cutoff = 0;
    double render_cutoff = 0;
    double attachment_cutoff = 0.06;
    std::vector<LmMesh> meshes;
};

LmFile parse_lm_txt(const std::string& text);
std::string format_lm_txt(const LmFile& lm);
void check_lm_txt_logic();
