#include "lzss.h"

#include "bin.h"

#include <windows.h>

namespace {

constexpr int kLengthTable[][2] = {
    {0, 0}, {1, 0}, {2, 0}, {3, 0}, {4, 0}, {5, 1}, {7, 1}, {9, 2},
    {13, 2}, {17, 3}, {25, 3}, {33, 4}, {49, 4}, {65, 5}, {97, 5}, {129, 7},
};
constexpr int kEofSymbol = 272;
constexpr int kNumLitSymbols = 273;
constexpr int kLeafFlag = 0x8000;
constexpr int kRebuildThreshold = 0x7FFF;
constexpr int kUnprocessed = static_cast<int>(0xFFFFFFFEu);

struct BitReader {
    const uint8_t* data = nullptr;
    int len_bits = 0;
    int pos = 0;

    int read_bit() {
        if (pos >= len_bits) return 0;
        int byte_idx = pos / 8;
        int bit_idx = pos % 8;
        ++pos;
        return (data[byte_idx] >> bit_idx) & 1;
    }

    int read_bits(int n) {
        if (n == 0) return 0;
        int available = len_bits - pos;
        if (available > n) available = n;
        if (available < 0) available = 0;
        pos += available;
        if (available == 0) return 0;
        int result = 0;
        int start = pos - available;
        for (int i = 0; i < available; ++i) {
            int byte_idx = (start + i) / 8;
            int bit_idx = (start + i) % 8;
            if ((data[byte_idx] >> bit_idx) & 1) result |= 1 << i;
        }
        return result;
    }
};

struct HuffmanTree {
    int num_leaves = 0;
    int total_nodes = 0;
    int root_idx = 0;
    std::vector<int> freq;
    std::vector<int> parent;
    std::vector<int> child;
    std::vector<int> sym_to_node;

    explicit HuffmanTree(int num_symbols_raw) {
        int n = (num_symbols_raw + 1) & 0xFFE;
        int total = n * 2 - 1;
        int root = total - 1;
        num_leaves = n;
        total_nodes = total;
        root_idx = root;
        freq.assign(total, 0);
        parent.assign(total, 0);
        child.assign(total, 0);
        sym_to_node.assign(n, 0);
        for (int i = 0; i < n; ++i) {
            freq[i] = 1;
            child[i] = i | kLeafFlag;
            sym_to_node[i] = i;
        }
        int j = 0;
        for (int k = n; k < total; ++k) {
            freq[k] = freq[j] + freq[j + 1];
            child[k] = j;
            parent[j] = k;
            parent[j + 1] = k;
            j += 2;
        }
        parent[root] = root;
    }

    int decode(BitReader& br) {
        int v = child[root_idx];
        int depth = 0;
        while ((v & kLeafFlag) == 0) {
            int idx = v + br.read_bit();
            if (idx >= total_nodes) throw std::runtime_error("tree index out of bounds");
            v = child[idx];
            if (++depth > 50) throw std::runtime_error("tree decode depth exceeded");
        }
        int sym = v & ~kLeafFlag;
        update(sym);
        return sym;
    }

    void update(int symbol) {
        if (freq[root_idx] > kRebuildThreshold) rebuild();
        int i = sym_to_node[symbol];
        while (true) {
            freq[i] += 1;
            int f = freq[i];
            if (i + 1 < total_nodes && freq[i + 1] < f) {
                int j = i + 2;
                while (j < total_nodes && freq[j] < f) ++j;
                --j;
                int ci = child[i];
                int cj = child[j];
                if ((cj & kLeafFlag) == 0) {
                    parent[cj] = i;
                    parent[cj + 1] = i;
                } else {
                    sym_to_node[cj & ~kLeafFlag] = i;
                }
                if ((ci & kLeafFlag) == 0) {
                    parent[ci] = j;
                    parent[ci + 1] = j;
                } else {
                    sym_to_node[ci & ~kLeafFlag] = j;
                }
                freq[i] = freq[j];
                freq[j] = f;
                child[i] = child[j];
                child[j] = ci;
                i = j;
            }
            int p = parent[i];
            if (p == i || p == root_idx) break;
            i = p;
        }
        freq[root_idx] += 1;
    }

    void rebuild() {
        int remaining_leaves = num_leaves;
        for (int i = 0; i < root_idx; ++i) {
            if (child[i] & kLeafFlag) freq[i] = (freq[i] + 1) >> 1;
            parent[i] = kUnprocessed;
        }
        parent[root_idx] = kUnprocessed;
        int pair_scan = 0;
        int node_scan = 0;
        while (true) {
            bool found = false;
            while (pair_scan < root_idx) {
                if (parent[pair_scan] == kUnprocessed) {
                    found = true;
                    break;
                }
                ++pair_scan;
            }
            if (!found || pair_scan >= root_idx) {
                parent[root_idx] = static_cast<int>(0xFFFFFFFFu);
                return;
            }
            int left = pair_scan;
            int right = pair_scan + 1;
            pair_scan += 2;
            while (node_scan <= root_idx) {
                if (child[node_scan] & kLeafFlag) --remaining_leaves;
                else if (parent[node_scan] == kUnprocessed) break;
                ++node_scan;
            }
            int slot = node_scan;
            ++node_scan;
            int next_scan = node_scan;
            int new_freq = freq[left] + freq[right];
            int insert_at = slot;
            if (slot > 0 && freq[slot - 1] > new_freq) {
                int scan = slot - 1;
                while (scan >= 0 && freq[scan] > new_freq) {
                    int c = child[scan];
                    if ((c & kLeafFlag) == 0) {
                        parent[c] += 1;
                        parent[c + 1] += 1;
                    } else {
                        sym_to_node[c & ~kLeafFlag] += 1;
                    }
                    --scan;
                }
                int pos = scan + 1;
                int count = slot - pos;
                if (count > 0) {
                    for (int s = count - 1; s >= 0; --s) {
                        freq[pos + 1 + s] = freq[pos + s];
                        child[pos + 1 + s] = child[pos + s];
                    }
                }
                insert_at = pos;
            } else if (remaining_leaves > 0) {
                int scan_pos = next_scan;
                int dst = slot;
                int nxt = next_scan;
                while (true) {
                    while (scan_pos < root_idx) {
                        if (child[scan_pos] & kLeafFlag) break;
                        ++scan_pos;
                    }
                    if (scan_pos >= root_idx || freq[scan_pos] >= new_freq) break;
                    freq[dst] = freq[scan_pos];
                    child[dst] = child[scan_pos];
                    parent[dst] = kUnprocessed;
                    sym_to_node[child[scan_pos] & ~kLeafFlag] = dst;
                    dst = nxt;
                    child[scan_pos] = 0;
                    ++nxt;
                    node_scan = nxt;
                    --remaining_leaves;
                    if (remaining_leaves <= 0) break;
                    ++scan_pos;
                }
                insert_at = dst;
            }
            freq[insert_at] = new_freq;
            child[insert_at] = left;
            parent[left] = insert_at;
            parent[right] = insert_at;
        }
    }
};

void copy_match(std::vector<uint8_t>& output, int distance, int match_len, uint32_t max_size) {
    for (int n = 0; n < match_len; ++n) {
        if (output.size() >= max_size) break;
        if (distance > 0 && distance <= static_cast<int>(output.size())) {
            output.push_back(output[output.size() - static_cast<size_t>(distance)]);
        } else {
            output.push_back(0);
        }
    }
}

struct FlagBits {
    BitReader* br = nullptr;
    uint32_t flags = 0;
    uint32_t mask = 0;

    int bit() {
        if (mask == 0) {
            flags = static_cast<uint32_t>(br->read_bits(32));
            mask = 1;
        }
        int bit = (flags & mask) ? 1 : 0;
        mask = (mask << 1) & 0xFFFFFFFFu;
        return bit;
    }
};

std::vector<uint8_t> decompress_huffman(
    const uint8_t* stream, size_t stream_size, uint32_t uncomp_size, int dist_bits_total, int num_dist_symbols,
    int dist_extra_bits) {
    int dist_mask = (1 << dist_bits_total) - 1;
    HuffmanTree lit_tree(kNumLitSymbols);
    HuffmanTree dist_tree(num_dist_symbols);
    BitReader br{stream, static_cast<int>(stream_size * 8), 0};
    std::vector<uint8_t> output;
    while (output.size() < uncomp_size) {
        int sym = lit_tree.decode(br);
        if (sym == kEofSymbol) break;
        if (sym > kEofSymbol) throw std::runtime_error("invalid symbol");
        if (sym < 256) {
            output.push_back(static_cast<uint8_t>(sym));
        } else {
            int base = kLengthTable[sym - 256][0];
            int extra = kLengthTable[sym - 256][1];
            int extra_val = extra > 0 ? br.read_bits(extra) : 0;
            int match_len = base + extra_val + 3;
            int dist_sym = dist_tree.decode(br);
            int dist_extra = br.read_bits(dist_extra_bits);
            int distance = ((dist_sym << dist_extra_bits) | dist_extra) & dist_mask;
            if (distance == 0) distance = 1;
            copy_match(output, distance, match_len, uncomp_size);
        }
    }
    if (output.size() > uncomp_size) output.resize(uncomp_size);
    return output;
}

std::vector<uint8_t> decompress_bitstream(
    const uint8_t* stream, size_t stream_size, uint32_t uncomp_size, int dist_bits_total, int dist_extra_bits) {
    int dist_mask = (1 << dist_bits_total) - 1;
    int len_overflow = dist_bits_total < 16 ? ((1 << (16 - dist_bits_total)) - 1) : 0;
    int offset_shift = dist_bits_total < 15 ? dist_bits_total : 15;
    BitReader br{stream, static_cast<int>(stream_size * 8), 0};
    std::vector<uint8_t> output;
    FlagBits fb{&br, 0, 0};
    if (dist_bits_total == 8) {
        while (output.size() < uncomp_size) {
            if (fb.bit() == 0) {
                output.push_back(static_cast<uint8_t>(br.read_bits(8) & 0xFF));
                continue;
            }
            int len_code = 0;
            for (int i = 0; i < 3; ++i) {
                if (fb.bit()) len_code |= 1 << i;
            }
            if (len_code == 7) len_code = br.read_bits(8);
            int distance = br.read_bits(8);
            if (distance == 0) distance = 1;
            copy_match(output, distance, len_code + 3, uncomp_size);
        }
    } else {
        while (output.size() < uncomp_size) {
            if (fb.bit() == 0) {
                if (fb.bit() == 0) {
                    output.push_back(static_cast<uint8_t>(br.read_bits(8) & 0xFF));
                } else {
                    int run_len = (br.read_bits(8) & 0xFF) + 3;
                    for (int n = 0; n < run_len && output.size() < uncomp_size; ++n) {
                        output.push_back(static_cast<uint8_t>(br.read_bits(8) & 0xFF));
                    }
                }
            } else {
                int word = br.read_bits(16);
                int distance = word & dist_mask;
                int len_code = (word >> offset_shift) & len_overflow;
                if (len_code == len_overflow) len_code = br.read_bits(8);
                if (distance == 0) distance = 1;
                copy_match(output, distance, len_code + 3, uncomp_size);
            }
        }
    }
    if (output.size() > uncomp_size) output.resize(uncomp_size);
    return output;
}

bool utf8_ok(const uint8_t* data, size_t size) {
    for (size_t i = 0; i < size;) {
        uint8_t c = data[i];
        size_t need = 1;
        if (c < 0x80) need = 1;
        else if ((c & 0xE0) == 0xC0 && c >= 0xC2) need = 2;
        else if ((c & 0xF0) == 0xE0) need = 3;
        else if ((c & 0xF8) == 0xF0 && c <= 0xF4) need = 4;
        else return false;
        if (i + need > size) return false;
        for (size_t k = 1; k < need; ++k) {
            if ((data[i + k] & 0xC0) != 0x80) return false;
        }
        i += need;
    }
    return true;
}

std::string wide_to_utf8(const wchar_t* text, int wlen) {
    if (wlen <= 0) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, text, wlen, nullptr, 0, nullptr, nullptr);
    std::string out(static_cast<size_t>(n), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text, wlen, out.data(), n, nullptr, nullptr);
    return out;
}

}  // namespace

std::vector<uint8_t> lzss_decompress(const uint8_t* data, size_t size, uint32_t uncompressed_size) {
    if (size == 0) throw std::runtime_error("truncated input");
    int mode = (data[0] >> 4) & 3;
    int level = data[0] & 0xF;
    if (level == 0) {
        size_t end = 1 + uncompressed_size;
        if (end > size) end = size;
        return std::vector<uint8_t>(data + 1, data + end);
    }
    int dist_bits_total = 0;
    int num_dist_symbols = 0;
    int dist_extra_bits = 0;
    if (mode == 0) {
        dist_bits_total = 8;
        num_dist_symbols = 16;
        dist_extra_bits = 4;
    } else if (mode == 1) {
        dist_bits_total = 12;
        num_dist_symbols = 64;
        dist_extra_bits = 6;
    } else if (mode == 2) {
        dist_bits_total = 14;
        num_dist_symbols = 64;
        dist_extra_bits = 8;
    } else {
        throw std::runtime_error("invalid compression mode");
    }
    if (level < 7) {
        return decompress_bitstream(data + 1, size - 1, uncompressed_size, dist_bits_total, dist_extra_bits);
    }
    return decompress_huffman(
        data + 1, size - 1, uncompressed_size, dist_bits_total, num_dist_symbols, dist_extra_bits);
}

std::vector<uint8_t> decode_binary_blob(const uint8_t* data, size_t size) {
    need(size, 4, "binary blob too short");
    uint32_t uncompressed = rd_u32(data);
    return lzss_decompress(data + 4, size - 4, uncompressed);
}

std::string decode_asset_text(const uint8_t* data, size_t size) {
    if (size == 0) return {};
    if (size >= 2 && ((data[0] == 0xFF && data[1] == 0xFE) || (data[0] == 0xFE && data[1] == 0xFF))) {
        int wlen = static_cast<int>(size / 2);
        bool be = data[0] == 0xFE;
        std::vector<wchar_t> wide(static_cast<size_t>(wlen));
        for (int i = 0; i < wlen; ++i) {
            uint8_t a = data[i * 2];
            uint8_t b = data[i * 2 + 1];
            wide[static_cast<size_t>(i)] = static_cast<wchar_t>(be ? ((a << 8) | b) : ((b << 8) | a));
        }
        int start = wide[0] == 0xFEFF ? 1 : 0;
        return wide_to_utf8(wide.data() + start, wlen - start);
    }
    const uint8_t* body = data;
    size_t body_size = size;
    if (size >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF) {
        body += 3;
        body_size -= 3;
    }
    if (utf8_ok(body, body_size)) return std::string(reinterpret_cast<const char*>(body), body_size);
    int wlen = MultiByteToWideChar(932, MB_ERR_INVALID_CHARS, reinterpret_cast<const char*>(data), static_cast<int>(size), nullptr, 0);
    if (wlen > 0) {
        std::vector<wchar_t> wide(static_cast<size_t>(wlen));
        MultiByteToWideChar(932, MB_ERR_INVALID_CHARS, reinterpret_cast<const char*>(data), static_cast<int>(size), wide.data(), wlen);
        return wide_to_utf8(wide.data(), wlen);
    }
    std::string out;
    out.reserve(size);
    for (size_t i = 0; i < size; ++i) {
        if (data[i] < 0x80) out.push_back(static_cast<char>(data[i]));
        else out.append("\xEF\xBF\xBD");
    }
    return out;
}
