#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct CdpAssetEntry {
    std::string kuid;
    std::string username;
    std::string kind;
    std::vector<std::string> files;
};

std::vector<std::string> list_cdp_kuids(const uint8_t* data, size_t size);
std::vector<CdpAssetEntry> list_cdp_assets(const uint8_t* data, size_t size);
std::vector<uint8_t> read_cdp_file(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& rel_path);
