#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct MatNameIssue {
    std::string name;
    std::string kind;
    std::string suggested;
    std::string detail;
    bool needs_fix() const { return kind != "ok" && !suggested.empty() && suggested != name; }
};

MatNameIssue check_mat_name(const std::string& name);
std::vector<std::string> list_material_names(const uint8_t* data, size_t size);
std::string format_mat_report(const std::string& path, const std::vector<MatNameIssue>& issues);
void check_mat_name_logic();
