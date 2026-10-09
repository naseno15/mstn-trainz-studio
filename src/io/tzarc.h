#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <vector>

std::vector<uint8_t> read_tzarc_config(const uint8_t* data, size_t size);
// First entry whose path, or else base name, matches a name in order. Empty when none.
std::vector<std::pair<std::string, std::vector<uint8_t>>> read_tzarc_all(const uint8_t* data, size_t size);
// Only the entries `wanted` accepts; v2 inflates just the chunks they span, on all cores.
std::vector<std::pair<std::string, std::vector<uint8_t>>> read_tzarc_select(const uint8_t* data, size_t size, const std::function<bool(const std::string&)>& wanted);
std::vector<uint8_t> read_tzarc_named(const uint8_t* data, size_t size, const std::vector<std::string>& names);
