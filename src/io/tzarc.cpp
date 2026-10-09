#include "tzarc.h"

#include "bin.h"

extern "C" {
#include "puff.h"
}

#include <algorithm>
#include <atomic>
#include <cstring>
#include <memory>
#include <thread>

namespace {

struct Entry {
    std::string name;
    uint64_t size = 0;
    uint64_t offset = 0;
};

// One zlib chunk straight into out[0..room); returns bytes written.
size_t inflate_zlib_into(const uint8_t* data, size_t size, uint8_t* out, size_t room) {
    if (size < 6 || room == 0) throw std::runtime_error("tzarc v2 zlib error");
    unsigned long destlen = static_cast<unsigned long>(room);
    unsigned long sourcelen = static_cast<unsigned long>(size - 2);
    int rc = puff(out, &destlen, data + 2, &sourcelen);
    if (rc != 0) throw std::runtime_error("tzarc v2 zlib error");
    return destlen;
}

// 32-bit `unsigned long` on Windows: stay under 2 GiB.
constexpr uint64_t kMaxUnc = 1800ull * 1024ull * 1024ull;

// Whole v2 blob, sequential. Fallback for archives whose chunks are not a fixed size.
std::vector<uint8_t> inflate_v2(const uint8_t* data, size_t size) {
    need(size, 20, "tzarc v2 header truncated");
    uint64_t unc = rd_u64(data + 8);
    uint32_t nchunk = rd_u32(data + 16);
    if (nchunk < 1 || nchunk > 1000000) throw std::runtime_error("tzarc v2 bad chunk count");
    if (unc == 0 || unc > kMaxUnc) throw std::runtime_error("tzarc v2 zlib error");
    size_t off = 20 + 2 * static_cast<size_t>(nchunk);
    std::vector<uint8_t> inner(static_cast<size_t>(unc));
    size_t pos = 0;
    for (uint32_t i = 0; i < nchunk; ++i) {
        size_t take = static_cast<size_t>(rd_u16(data + 20 + 2 * i)) + 1;
        if (off + take > size) throw std::runtime_error("tzarc v2 truncated chunk");
        pos += inflate_zlib_into(data + off, take, inner.data() + pos, inner.size() - pos);
        off += take;
    }
    if (pos != unc) throw std::runtime_error("tzarc v2 size mismatch");
    return inner;
}

// `limit` is the payload area size; the directory itself may only be partly inflated so far.
std::vector<Entry> parse_directory(const uint8_t* data, size_t size, bool be, uint64_t limit) {
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
    if (cursor > limit) throw std::runtime_error("tzarc payloads overrun blob");
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

// An opened archive whose payload bytes are inflated on demand. v2 chunks are independent zlib streams
// of one fixed size (all but the last), so any byte range maps to a few chunks that can be inflated in
// parallel; a config at the front of a 500 MB archive costs a handful of chunks, not the whole blob.
class Archive {
public:
    Archive(const uint8_t* data, size_t size) {
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
        if (version == 1) {
            base_ = data + 8;
            total_ = size - 8;
            entries_ = parse_directory(base_, total_, big, total_);
            return;
        }
        if (!open_chunked(data, size)) {
            whole_ = inflate_v2(data, size);
            base_ = whole_.data();
            total_ = whole_.size();
            entries_ = parse_directory(base_, total_, true, total_);
        }
    }

    const std::vector<Entry>& entries() const { return entries_; }

    // Make sure [offset, offset+len) of every given entry is readable.
    void ensure(const std::vector<const Entry*>& wanted) {
        if (!chunked_) return;
        std::vector<uint32_t> todo;
        for (const Entry* e : wanted) {
            if (e->size == 0) continue;
            if (e->offset + e->size > total_) throw std::runtime_error("tzarc payloads overrun blob");
            for (uint64_t c = e->offset / chunk_; c <= (e->offset + e->size - 1) / chunk_; ++c)
                if (!done_[c]) {
                    done_[c] = 1;  // claimed: dedupes the todo list
                    todo.push_back(static_cast<uint32_t>(c));
                }
        }
        run(todo);
    }

    std::vector<uint8_t> read(const Entry* e) {
        if (e == nullptr) return {};
        ensure({e});
        if (e->offset + e->size > total_) throw std::runtime_error("tzarc payloads overrun blob");
        return std::vector<uint8_t>(base_ + e->offset, base_ + e->offset + e->size);
    }

private:
    bool open_chunked(const uint8_t* data, size_t size) {
        need(size, 20, "tzarc v2 header truncated");
        total_ = rd_u64(data + 8);
        n_ = rd_u32(data + 16);
        if (n_ < 1 || n_ > 1000000) throw std::runtime_error("tzarc v2 bad chunk count");
        if (total_ == 0 || total_ > kMaxUnc) throw std::runtime_error("tzarc v2 zlib error");
        size_t off = 20 + 2 * static_cast<size_t>(n_);
        for (uint32_t i = 0; i < n_; ++i) {
            const size_t take = static_cast<size_t>(rd_u16(data + 20 + 2 * i)) + 1;
            if (off + take > size) throw std::runtime_error("tzarc v2 truncated chunk");
            src_.push_back(data + off);
            len_.push_back(take);
            off += take;
        }
        // Chunk 0 sets the fixed size; a single chunk is just itself.
        // Probe with 256 KiB: real archives use 65000-byte chunks; anything bigger takes the sequential path.
        std::vector<uint8_t> first(static_cast<size_t>(std::min<uint64_t>(total_, 256u << 10)));
        size_t got = 0;
        try {
            got = inflate_zlib_into(src_[0], len_[0], first.data(), first.size());
        } catch (const std::exception&) {
            return false;
        }
        chunk_ = n_ == 1 ? total_ : got;
        if (n_ == 1 && got != total_) return false;
        if (chunk_ == 0 || (n_ - 1) * chunk_ >= total_ || total_ - (n_ - 1) * chunk_ > chunk_) return false;  // not fixed-size
        buf_.reset(new uint8_t[static_cast<size_t>(total_)]);  // uninitialised: untouched pages stay uncommitted
        base_ = buf_.get();
        done_.assign(n_, 0);
        chunked_ = true;
        try {
            // Directory first: inflate in order until it parses (it is a few KB, normally chunk 0).
            for (uint32_t c = 0; c < n_; ++c) {
                run_one(c);
                done_[c] = 1;
                const size_t have = static_cast<size_t>(std::min<uint64_t>(total_, (c + 1) * chunk_));
                try {
                    entries_ = parse_directory(base_, have, true, total_);
                    return true;
                } catch (const std::exception& e) {
                    if (std::strstr(e.what(), "truncated") == nullptr) throw;  // bad data, not just "need more"
                }
            }
        } catch (const std::exception&) {
            chunked_ = false;
            return false;  // unexpected chunk sizes: take the sequential path
        }
        return false;
    }

    void run_one(uint32_t c) {
        const uint64_t start = static_cast<uint64_t>(c) * chunk_;
        const size_t want = static_cast<size_t>(std::min<uint64_t>(chunk_, total_ - start));
        const size_t got = inflate_zlib_into(src_[c], len_[c], buf_.get() + start, want);
        if (got != want) throw std::runtime_error("tzarc v2 chunk size mismatch");
    }

    void run(const std::vector<uint32_t>& todo) {
        if (todo.empty()) return;
        std::atomic<size_t> next{0};
        std::atomic<bool> failed{false};
        auto work = [&] {
            for (size_t i = next.fetch_add(1); i < todo.size() && !failed; i = next.fetch_add(1)) {
                try {
                    run_one(todo[i]);
                } catch (const std::exception&) {
                    failed = true;
                }
            }
        };
        const size_t workers = std::min<size_t>(todo.size(), std::max(1u, std::thread::hardware_concurrency()));
        std::vector<std::thread> pool;
        for (size_t t = 1; t < workers; ++t) pool.emplace_back(work);
        work();
        for (std::thread& t : pool) t.join();
        if (failed) throw std::runtime_error("tzarc v2 zlib error");
    }

    const uint8_t* base_ = nullptr;
    uint64_t total_ = 0;
    uint32_t n_ = 0;
    uint64_t chunk_ = 0;
    bool chunked_ = false;
    std::vector<const uint8_t*> src_;
    std::vector<size_t> len_;
    std::vector<uint8_t> done_;
    std::unique_ptr<uint8_t[]> buf_;
    std::vector<uint8_t> whole_;
    std::vector<Entry> entries_;
};

std::string lower_slash(std::string s) {
    for (char& c : s) {
        if (c == '\\') c = '/';
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return s;
}

}  // namespace

std::vector<uint8_t> read_tzarc_config(const uint8_t* data, size_t size) {
    Archive archive(data, size);
    return archive.read(config_entry(archive.entries()));
}

std::vector<std::pair<std::string, std::vector<uint8_t>>> read_tzarc_all(const uint8_t* data, size_t size) {
    return read_tzarc_select(data, size, [](const std::string&) { return true; });
}

std::vector<std::pair<std::string, std::vector<uint8_t>>> read_tzarc_select(const uint8_t* data, size_t size, const std::function<bool(const std::string&)>& wanted) {
    Archive archive(data, size);
    std::vector<const Entry*> hits;
    for (const Entry& entry : archive.entries())
        if (wanted(entry.name)) hits.push_back(&entry);
    archive.ensure(hits);
    std::vector<std::pair<std::string, std::vector<uint8_t>>> out;
    for (const Entry* entry : hits) out.emplace_back(entry->name, archive.read(entry));
    return out;
}

std::vector<uint8_t> read_tzarc_named(const uint8_t* data, size_t size, const std::vector<std::string>& names) {
    Archive archive(data, size);
    for (const std::string& want : names) {
        const std::string path = lower_slash(want);
        const std::string base = base_name(want);
        for (const Entry& entry : archive.entries())
            if (lower_slash(entry.name) == path || base_name(entry.name) == base) return archive.read(&entry);
    }
    return {};
}
