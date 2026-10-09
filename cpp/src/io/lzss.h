#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

std::vector<uint8_t> lzss_decompress(const uint8_t* data, size_t size, uint32_t uncompressed_size);
std::vector<uint8_t> decode_binary_blob(const uint8_t* data, size_t size);
std::string decode_asset_text(const uint8_t* data, size_t size);
