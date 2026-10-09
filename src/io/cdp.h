#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct CdpAssetEntry {
    std::string kuid;
    std::string username;
    std::string kind;
    std::vector<std::string> files;
    std::vector<uint64_t> sizes;
};

std::vector<std::string> list_cdp_kuids(const uint8_t* data, size_t size);
std::vector<CdpAssetEntry> list_cdp_assets(const uint8_t* data, size_t size);
std::vector<uint8_t> read_cdp_file(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& rel_path);
std::string asset_config_text(const uint8_t* data, size_t size, const std::string& asset_kuid);
std::vector<uint8_t> replace_asset_config(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& text);
std::vector<uint8_t> replace_cdp_file(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& rel_path,
    const uint8_t* replacement, size_t replacement_size);
std::vector<uint8_t> remove_cdp_file(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& rel_path);
std::vector<uint8_t> remove_cdp_asset(
    const uint8_t* data, size_t size, const std::string& asset_kuid);
