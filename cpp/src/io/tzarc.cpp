#include "tzarc.h"

#include "bin.h"

extern "C" {
#include "puff.h"
}

#include <cstring>

namespace {

struct Entry {
    std::string name;
    uint64_t size = 0;
    uint64_t offset = 0;
};

std::vector<uint8_t> inflate_zlib(const uint8_t* data, size_t size, uint64_t cap) {
    if (size < 6 || cap == 0 || cap > 64ull * 1024ull * 1024ull) throw std::runtime_error("tzarc v2 zlib error");
    std::vector<uint8_t> out(static_cast<size_t>(cap));
    unsigned long destlen = static_cast<unsigned long>(cap);
    unsigned long sourcelen = static_cast<unsigned long>(size - 2);
    int rc = puff(out.data(), &destlen, data + 2, &sourcelen);
    if (rc != 0) throw std::runtime_error("tzarc v2 zlib error");
    out.resize(destlen);
    return out;
}

std::vector<uint8_t> inflate_v2(const uint8_t* data, size_t size) {
    need(size, 20, "tzarc v2 header truncated");
    uint64_t unc = rd_u64(data + 8);
    uint32_t nchunk = rd_u32(data + 16);
    if (nchunk < 1 || nchunk > 1000000) throw std::runtime_error("tzarc v2 bad chunk count");
    size_t off = 20 + 2 * static_cast<size_t>(nchunk);
    std::vector<uint8_t> inner;
    for (uint32_t i = 0; i < nchunk; ++i) {
        uint16_t csize = rd_u16(data + 20 + 2 * i);
        size_t take = static_cast<size_t>(csize) + 1;
        if (off + take > size) throw std::runtime_error("tzarc v2 truncated chunk");
        std::vector<uint8_t> part = inflate_zlib(data + off, take, unc - inner.size());
        off += take;
        inner.insert(inner.end(), part.begin(), part.end());
    }
    if (inner.size() != unc) throw std::runtime_error("tzarc v2 size mismatch");
    return inner;
}

std::vector<Entry> parse_directory(const uint8_t* data, size_t size, bool be) {
    need(size, 4, "tzarc directory truncated");
    uint32_t count = be ? rd_u32be(data) : rd_u32(data);
    if (count > 1000000) throw std::runtime_error("tzarc file count ridiculous");
    size_t off = 4;
    std::vector<std::pair<std::string, uint64_t>> rows;
    for (uint32_t i = 0; i < count; ++i) {
        if (off >= size) throw std::runtime_error("truncated tzarc directory");
        uint8_t nlen = data[off++];
        if (off + nlen + 8 > size) throw std::runtime_error("truncated tzarc directory");
        std::string name(reinterpret_cast<const char*>(data + off), nlen);
        off += nlen;
        uint64_t file_size = be ? rd_u64be(data + off) : rd_u64(data + off);
        off += 8;
        rows.emplace_back(name, file_size);
    }
    if (off + 4 > size) throw std::runtime_error("truncated tzarc pad");
    off += 4;
    std::vector<Entry> entries;
    uint64_t cursor = off;
    for (const auto& row : rows) {
        Entry entry;
        entry.name = row.first;
        entry.size = row.second;
        entry.offset = cursor;
        cursor += row.second;
        entries.push_back(entry);
    }
    if (cursor > size) throw std::runtime_error("tzarc payloads overrun blob");
    return entries;
}

std::string base_name(std::string name) {
    for (char& c : name) {
        if (c == '\\') c = '/';
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    auto slash = name.rfind('/');
    if (slash != std::string::npos) name = name.substr(slash + 1);
    return name;
}

const Entry* config_entry(const std::vector<Entry>& entries) {
    const Entry* best = nullptr;
    int rank = 99;
    for (const Entry& entry : entries) {
        std::string base = base_name(entry.name);
        int next = base == "config.txt" ? 0 : base == "config.chump" ? 1 : 99;
        if (next < rank) {
            rank = next;
            best = &entry;
        }
    }
    return best;
}

}  // namespace

std::vector<uint8_t> read_tzarc_config(const uint8_t* data, size_t size) {
    need(size, 12, "not a tzarc");
    if (std::memcmp(data, "TZac", 4) != 0) throw std::runtime_error("not a tzarc");
    uint32_t be = rd_u32be(data + 4);
    uint32_t le = rd_u32(data + 4);
    int version = 0;
    bool big = false;
    if (be == 1 || be == 2) {
        version = static_cast<int>(be);
        big = true;
    } else if (le == 1 || le == 2) {
        version = static_cast<int>(le);
    } else {
        throw std::runtime_error("tzarc version not supported");
    }
    std::vector<uint8_t> blob;
    const uint8_t* view = data;
    size_t view_size = size;
    if (version == 2) {
        blob = inflate_v2(data, size);
        view = blob.data();
        view_size = blob.size();
        big = true;
    } else {
        view = data + 8;
        view_size = size - 8;
    }
    std::vector<Entry> entries = parse_directory(view, view_size, big);
    const Entry* hit = config_entry(entries);
    if (hit == nullptr) return {};
    if (hit->offset + hit->size > view_size) throw std::runtime_error("tzarc payloads overrun blob");
    return std::vector<uint8_t>(view + hit->offset, view + hit->offset + hit->size);
}
