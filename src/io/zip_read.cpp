#include "zip_read.h"

#include "bin.h"

extern "C" {
#include "puff.h"
}

// ponytail: no Zip64 and no encryption. A >4 GB package or a locked zip throws.
// Upgrade path: read the Zip64 end record and the 0x0001 extra field.

std::vector<ZipEntry> list_zip(const uint8_t* data, size_t size) {
    need(size, 22, "not a zip");
    size_t eocd = std::string::npos;
    const size_t floor = size > 22 + 65535 ? size - 22 - 65535 : 0;
    for (size_t pos = size - 22 + 1; pos-- > floor;) {
        if (rd_u32(data + pos) == 0x06054b50) {
            eocd = pos;
            break;
        }
    }
    if (eocd == std::string::npos) throw std::runtime_error("not a zip");
    const uint16_t count = rd_u16(data + eocd + 10);
    const uint32_t dir_at = rd_u32(data + eocd + 16);
    if (dir_at == 0xFFFFFFFFu || count == 0xFFFF) throw std::runtime_error("zip64 is not supported");
    std::vector<ZipEntry> out;
    size_t pos = dir_at;
    for (uint16_t i = 0; i < count; ++i) {
        need(size, pos + 46, "zip directory truncated");
        if (rd_u32(data + pos) != 0x02014b50) throw std::runtime_error("zip directory broken");
        ZipEntry entry;
        entry.method = rd_u16(data + pos + 10);
        entry.packed = rd_u32(data + pos + 20);
        entry.size = rd_u32(data + pos + 24);
        const uint16_t name_len = rd_u16(data + pos + 28);
        const uint16_t extra_len = rd_u16(data + pos + 30);
        const uint16_t note_len = rd_u16(data + pos + 32);
        entry.local_offset = rd_u32(data + pos + 42);
        need(size, pos + 46 + name_len, "zip name truncated");
        entry.name.assign(reinterpret_cast<const char*>(data + pos + 46), name_len);
        for (char& c : entry.name) {
            if (c == '\\') c = '/';
        }
        entry.dir = !entry.name.empty() && entry.name.back() == '/';
        out.push_back(std::move(entry));
        pos += 46 + name_len + extra_len + note_len;
    }
    return out;
}

std::vector<uint8_t> read_zip_entry(const uint8_t* data, size_t size, const ZipEntry& entry) {
    const size_t at = static_cast<size_t>(entry.local_offset);
    need(size, at + 30, "zip entry truncated");
    if (rd_u32(data + at) != 0x04034b50) throw std::runtime_error("zip entry broken");
    const size_t body = at + 30 + rd_u16(data + at + 26) + rd_u16(data + at + 28);
    need(size, body + entry.packed, "zip entry truncated");
    if (entry.method == 0) return std::vector<uint8_t>(data + body, data + body + entry.packed);
    if (entry.method != 8) throw std::runtime_error("zip method not supported");
    std::vector<uint8_t> out(static_cast<size_t>(entry.size));
    unsigned long dest_len = static_cast<unsigned long>(entry.size);
    unsigned long source_len = static_cast<unsigned long>(entry.packed);
    if (puff(out.data(), &dest_len, data + body, &source_len) != 0) throw std::runtime_error("zip inflate failed");
    out.resize(dest_len);
    return out;
}

bool safe_zip_name(const std::string& name) {
    if (name.empty() || name[0] == '/' || name[0] == '\\') return false;
    if (name.size() > 1 && name[1] == ':') return false;
    size_t start = 0;
    while (start <= name.size()) {
        size_t end = name.find_first_of("/\\", start);
        if (end == std::string::npos) end = name.size();
        if (name.compare(start, end - start, "..") == 0 && end - start == 2) return false;
        start = end + 1;
    }
    return true;
}
