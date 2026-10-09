#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

std::vector<uint8_t> pack_kuid(int32_t creator, int32_t content, std::optional<int> version);
void unpack_kuid(const uint8_t* raw, size_t size, int32_t& creator, int32_t& content, int& version);
std::string bytes_to_kuid(const uint8_t* raw, size_t size);
std::optional<std::vector<uint8_t>> parse_kuid_string(const std::string& text);
int kuid_hash(const uint8_t* raw, size_t size);
std::string hash_folder(const uint8_t* raw, size_t size);
