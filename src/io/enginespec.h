#pragma once

#include <map>
#include <string>
#include <utility>
#include <vector>

struct EngineSpec {
    std::map<std::string, std::string> header;
    std::map<std::string, std::map<std::string, double>> blocks;
    std::map<int, std::vector<std::pair<double, double>>> throttle;
    std::string path;

    std::map<std::string, double>& block(const std::string& name);
    const std::map<std::string, double>* find_block(const std::string& name) const;
};

EngineSpec parse_enginespec(const std::string& text);
std::string write_enginespec(const EngineSpec& spec);
bool looks_like_enginespec(const std::string& text);
bool edit_throttle_point(EngineSpec& spec, int notch, int index, int column, const std::string& text);
void add_throttle_point(EngineSpec& spec, int notch);
void delete_throttle_point(EngineSpec& spec, int notch, int index);
std::string fmt_kmh(double meters_per_second);
std::string fmt_kn(double kilonewtons);
std::string fmt_native(double value);
std::string fmt_bar(double native);
std::string fmt_kpa(double native);
double native_from_bar(double bar);
double native_from_kpa(double kpa);
