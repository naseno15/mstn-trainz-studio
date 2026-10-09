#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

struct TexIssue {
    std::string level;
    std::string message;
};

struct TextureReport {
    std::string path;
    std::vector<std::pair<std::string, std::string>> keys;
    std::vector<TexIssue> issues;
    int width = 0;
    int height = 0;
    bool ok() const;
    std::string summary() const;
};

std::string texture_stem(const std::string& name);
std::pair<std::string, std::string> material_family(const std::string& stem);
std::string pbr_set_label(const std::vector<std::string>& roles);
std::vector<std::string> parse_texture_keys_order();
std::string format_texture_txt(const std::vector<std::pair<std::string, std::string>>& keys);
std::vector<std::pair<std::string, std::string>> parse_texture_txt(const std::string& text);
std::vector<std::pair<std::string, std::string>> keys_for_image(const std::string& primary, const std::string& alpha, const std::string& tile, const std::string& compression);
std::pair<int, int> image_size_header(const uint8_t* data, size_t size, const std::string& suffix);
TextureReport check_texture_txt(const std::string& path, const std::string& text, int primary_w, int primary_h, bool primary_found);
std::string format_texture_report(const TextureReport& report);
void check_texture_txt_logic();
