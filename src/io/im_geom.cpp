#include "im_geom.h"

#include "bin.h"

#include <cstring>

namespace {

struct Chunk {
    char tag[4];
    size_t body = 0;
    uint32_t size = 0;
};

std::vector<Chunk> parse_chunks(const uint8_t* data, size_t size) {
    if (size < 12 || std::memcmp(data, "JIRF", 4) != 0) throw std::runtime_error("not a JIRF/.im file");
    uint32_t jirf_size = rd_u32(data + 4);
    if (jirf_size != size - 8) throw std::runtime_error("JIRF size mismatch");
    if (std::memcmp(data + 8, "IDXM", 4) != 0) throw std::runtime_error("missing IDXM");
    std::vector<Chunk> out;
    size_t off = 12;
    while (off < size) {
        if (off + 8 > size) throw std::runtime_error("chunk walk did not end at EOF");
        Chunk chunk;
        std::memcpy(chunk.tag, data + off, 4);
        chunk.size = rd_u32(data + off + 4);
        chunk.body = off + 8;
        if (chunk.body + chunk.size > size) throw std::runtime_error("chunk walk did not end at EOF");
        out.push_back(chunk);
        off = chunk.body + chunk.size;
    }
    if (off != size) throw std::runtime_error("chunk walk did not end at EOF");
    return out;
}

std::vector<Chunk> iter_chunks(const uint8_t* data, size_t start, size_t end) {
    std::vector<Chunk> out;
    size_t off = start;
    while (off + 8 <= end) {
        bool alnum = true;
        for (int i = 0; i < 4; ++i) {
            unsigned char c = data[off + i];
            if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))) alnum = false;
        }
        if (!alnum) break;
        Chunk chunk;
        std::memcpy(chunk.tag, data + off, 4);
        chunk.size = rd_u32(data + off + 4);
        chunk.body = off + 8;
        if (chunk.body + chunk.size > end) break;
        out.push_back(chunk);
        off = chunk.body + chunk.size;
    }
    return out;
}

std::string jet_name(const uint8_t* data, size_t& p, size_t end) {
    if (p + 4 > end) throw std::runtime_error("material name overruns chunk");
    uint32_t n = rd_u32(data + p);
    p += 4;
    if (n > 4096 || p + n > end) throw std::runtime_error("material name overruns chunk");
    size_t cut = 0;
    while (cut < n && data[p + cut] != 0) ++cut;
    std::string name(reinterpret_cast<const char*>(data + p), cut);
    p += n;
    return name;
}

std::string mat_name(const uint8_t* data, size_t body, uint32_t size) {
    size_t end = body + size;
    if (size < 8) return {};
    uint32_t ver = rd_u32(data + body);
    size_t p = body + 4;
    if (ver < 102 || p + 4 > end) return {};
    try {
        return jet_name(data, p, end);
    } catch (const std::runtime_error&) {
        return {};
    }
}

bool fit_vertex_block(int remaining, int nverts, int nidx, int nface, bool want_tangents, int& stride, int& idx_w) {
    if (nverts <= 0) throw std::runtime_error("GEOM has no vertices");
    int tangent_opts[2] = {want_tangents ? 1 : 0, 0};
    int tangent_n = want_tangents ? 2 : 1;
    int face_opts[2] = {nface ? nface : 0, 0};
    int face_n = nface ? 2 : 1;
    for (int iw : {2, 4}) {
        for (int fi = 0; fi < face_n; ++fi) {
            for (int ti = 0; ti < tangent_n; ++ti) {
                int faces = face_opts[fi];
                bool tangents = tangent_opts[ti] != 0;
                int tail = nidx * iw + nverts * 12 + faces * 12;
                if (tangents) tail += nverts * 12;
                int room = remaining - tail;
                if (room < nverts * 12 || room % nverts != 0) continue;
                int next = room / nverts;
                if (next == 12 || next == 20 || next == 28 || next == 36) {
                    stride = next;
                    idx_w = iw;
                    return true;
                }
            }
        }
    }
    return false;
}

MeshPart parse_geom(const uint8_t* data, size_t body, uint32_t size, const std::string& name) {
    size_t end = body + size;
    size_t p = body;
    uint32_t ver = rd_u32(data + p);
    p += 4;
    if (ver < 100 || ver > 201) throw std::runtime_error("unsupported GEOM version");
    uint32_t flags = 4;
    uint32_t use_tangents = 0;
    if (ver >= 101) {
        flags = rd_u32(data + p);
        p += 4;
    }
    if (ver >= 201) {
        use_tangents = rd_u32(data + p);
        p += 4;
    }
    p += 4;
    uint32_t nverts = rd_u32(data + p);
    p += 4;
    uint32_t nprims = rd_u32(data + p);
    p += 4;
    uint32_t nidx = nprims * (flags == 2 ? 2 : 3);
    uint32_t nface = 0;
    if (ver >= 101) {
        nidx = rd_u32(data + p);
        p += 4;
        nface = rd_u32(data + p);
        p += 4;
    }
    if (ver == 103 || ver == 104) p += 4;
    if (ver >= 102) p += 4;
    if (ver >= 200) {
        uint32_t n = rd_u32(data + p);
        p += 4;
        if (n > 1048576 || p + n > end) throw std::runtime_error("jet string overruns chunk");
        p += n;
    }
    if (flags != 0 && flags != 4) throw std::runtime_error("GEOM primitive flags are not triangles");
    if (nverts > 2000000 || nidx > 6000000 || nidx % 3 != 0) throw std::runtime_error("GEOM counts out of range");
    int stride = 0;
    int idx_w = 0;
    if (!fit_vertex_block(static_cast<int>(end - p), static_cast<int>(nverts), static_cast<int>(nidx), static_cast<int>(nface), use_tangents != 0, stride, idx_w)) {
        throw std::runtime_error("GEOM vertex block does not match header counts");
    }
    MeshPart part;
    part.name = name.empty() ? "mesh" : name;
    part.positions.resize(nverts * 3);
    for (uint32_t v = 0; v < nverts; ++v) {
        const uint8_t* src = data + p + static_cast<size_t>(v) * stride;
        part.positions[v * 3] = rd_f32(src);
        part.positions[v * 3 + 1] = rd_f32(src + 4);
        part.positions[v * 3 + 2] = rd_f32(src + 8);
    }
    p += static_cast<size_t>(nverts) * stride;
    for (uint32_t i = 0; i < nidx; ++i) {
        uint32_t index = idx_w == 2 ? rd_u16(data + p + i * 2) : rd_u32(data + p + i * 4);
        part.indices.push_back(index);
    }
    uint32_t max_index = 0;
    for (uint32_t index : part.indices) if (index > max_index) max_index = index;
    if (!part.indices.empty() && max_index >= nverts) throw std::runtime_error("GEOM index out of range");
    p += static_cast<size_t>(nidx) * idx_w;
    part.normals.assign(nverts * 3, 0);
    if (p + static_cast<size_t>(nverts) * 12 <= end) {
        for (uint32_t v = 0; v < nverts * 3; ++v) part.normals[v] = rd_f32(data + p + v * 4);
    }
    return part;
}

}  // namespace

std::vector<MeshPart> parse_im_parts(const uint8_t* data, size_t size) {
    std::vector<MeshPart> parts;
    std::string error;
    for (const Chunk& chunk : parse_chunks(data, size)) {
        if (std::memcmp(chunk.tag, "CHNK", 4) != 0) continue;
        size_t nested_at = chunk.size >= 8 ? chunk.body + 8 : chunk.body;
        std::string mat;
        for (const Chunk& nested : iter_chunks(data, nested_at, chunk.body + chunk.size)) {
            if (std::memcmp(nested.tag, "MATL", 4) == 0) {
                std::string next = mat_name(data, nested.body, nested.size);
                if (!next.empty()) mat = next;
            } else if (std::memcmp(nested.tag, "GEOM", 4) == 0) {
                try {
                    parts.push_back(parse_geom(data, nested.body, nested.size, mat.empty() ? "chunk_" + std::to_string(parts.size()) : mat));
                } catch (const std::runtime_error& exc) {
                    if (error.empty()) error = exc.what();
                }
            }
        }
    }
    if (!parts.empty()) return parts;
    if (!error.empty()) throw std::runtime_error(error);
    throw std::runtime_error("no GEOM chunk in this .im");
}
