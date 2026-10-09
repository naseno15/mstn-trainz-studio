#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct ZipEntry {
    std::string name;
    uint64_t local_offset = 0;
    uint64_t packed = 0;
    uint64_t size = 0;
    uint16_t method = 0;
    bool dir = false;
};

// Central directory of an in-memory zip. Throws on a broken archive.
std::vector<ZipEntry> list_zip(const uint8_t* data, size_t size);
// Stored or deflate member bytes.
std::vector<uint8_t> read_zip_entry(const uint8_t* data, size_t size, const ZipEntry& entry);
// Relative, no drive, no `..`.
bool safe_zip_name(const std::string& name);
