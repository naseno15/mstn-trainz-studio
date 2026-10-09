#include "trainzmesh.h"

#include "bin.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace {

struct Vfmt {
    int stride = 0;
    int position = 0;
    int normal = -1;
    int uv = -1;
    int tangent = -1;
};

bool starts_with(const std::string& text, size_t i, const char* prefix) {
    size_t n = std::strlen(prefix);
    return i + n <= text.size() && text.compare(i, n, prefix) == 0;
}

Vfmt parse_vertex_format(const std::string& fmt, int declared_stride) {
    Vfmt result;
    auto us = fmt.find('_');
    std::string payload = us == std::string::npos ? fmt : fmt.substr(us + 1);
    const char* prefixes[] = {"BWg", "Tg", "Wi", "T0", "T1", "T2", "T3", "P", "N", "C"};
    size_t i = 0;
    int offset = 0;
    while (i < payload.size()) {
        const char* prefix = nullptr;
        for (const char* item : prefixes) {
            if (starts_with(payload, i, item)) {
                prefix = item;
                break;
            }
        }
        if (prefix == nullptr) break;
        size_t j = i + std::strlen(prefix);
        int count = 0;
        bool any = false;
        while (j < payload.size() && payload[j] >= '0' && payload[j] <= '9') {
            any = true;
            count = count * 10 + (payload[j] - '0');
            ++j;
        }
        if (!any) count = 1;
        char typ = 0;
        if (std::strcmp(prefix, "Wi") != 0 && j < payload.size() && std::strchr("fdiIhHsSbB", payload[j])) {
            typ = payload[j++];
        }
        int size = count * 4;
        if (typ == 'f') size = count * 4;
        else if (typ == 'd') size = count * 8;
        else if (std::strcmp(prefix, "Wi") == 0 && typ == 0) size = count;
        else if (typ == 'b' || typ == 'B') size = count;
        else if (typ == 'h' || typ == 'H' || typ == 's' || typ == 'S') size = count * 2;
        else if (typ == 'i' || typ == 'I') size = count * 4;
        if (std::strcmp(prefix, "P") == 0) result.position = offset;
        else if (std::strcmp(prefix, "N") == 0 && result.normal < 0) result.normal = offset;
        else if (std::strcmp(prefix, "Tg") == 0 && result.tangent < 0) result.tangent = offset;
        else if (prefix[0] == 'T' && std::strcmp(prefix, "Tg") != 0 && result.uv < 0) result.uv = offset;
        offset += size;
        i = j;
    }
    result.stride = declared_stride ? declared_stride : offset;
    if (declared_stride == 64 && fmt.find("Wi4") != std::string::npos && fmt.find("BWg4f") != std::string::npos) {
        result.position = 0;
        result.normal = 32;
        result.tangent = 44;
        result.uv = 56;
        result.stride = 64;
    }
    return result;
}

bool finite3(float x, float y, float z) {
    return std::isfinite(x) && std::isfinite(y) && std::isfinite(z) && std::fabs(x) < 1e7f && std::fabs(y) < 1e7f &&
           std::fabs(z) < 1e7f;
}

bool sample_ok(const uint8_t* data, size_t size, size_t offset, int count, int stride, const Vfmt& fmt) {
    if (count < 3) return false;
    int sample[5] = {0, 1, 2, count / 2, count - 1};
    float xs[5], ys[5], zs[5];
    for (int s = 0; s < 5; ++s) {
        size_t base = offset + static_cast<size_t>(sample[s]) * stride;
        if (base + static_cast<size_t>(stride) > size) return false;
        float x = rd_f32(data + base + fmt.position);
        float y = rd_f32(data + base + fmt.position + 4);
        float z = rd_f32(data + base + fmt.position + 8);
        if (!finite3(x, y, z)) return false;
        xs[s] = x;
        ys[s] = y;
        zs[s] = z;
        if (fmt.normal >= 0) {
            float nx = rd_f32(data + base + fmt.normal);
            float ny = rd_f32(data + base + fmt.normal + 4);
            float nz = rd_f32(data + base + fmt.normal + 8);
            if (!finite3(nx, ny, nz)) return false;
        }
        if (fmt.uv >= 0) {
            float u = rd_f32(data + base + fmt.uv);
            float v = rd_f32(data + base + fmt.uv + 4);
            if (!(std::isfinite(u) && std::isfinite(v) && std::fabs(u) < 1e5f && std::fabs(v) < 1e5f)) return false;
        }
    }
    auto span = [](const float* v) {
        float lo = v[0], hi = v[0];
        for (int i = 1; i < 5; ++i) {
            if (v[i] < lo) lo = v[i];
            if (v[i] > hi) hi = v[i];
        }
        return hi - lo;
    };
    float extent = span(xs);
    if (span(ys) > extent) extent = span(ys);
    if (span(zs) > extent) extent = span(zs);
    return extent < 1e6f;
}

bool indices_ok(const uint8_t* data, size_t size, size_t offset, int count, int width, int vc) {
    if (count < 3 || count % 3) return false;
    if (offset + static_cast<size_t>(count) * width > size) return false;
    int step = count / 2048;
    if (step < 1) step = 1;
    for (int i = 0; i < count; i += step) {
        uint32_t index = width == 2 ? rd_u16(data + offset + i * 2) : rd_u32(data + offset + i * 4);
        if (index >= static_cast<uint32_t>(vc)) return false;
    }
    for (int i = count - 3; i < count; ++i) {
        uint32_t index = width == 2 ? rd_u16(data + offset + i * 2) : rd_u32(data + offset + i * 4);
        if (index >= static_cast<uint32_t>(vc)) return false;
    }
    return true;
}

std::string lower_copy(std::string text) {
    for (char& c : text) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return text;
}

bool is_env(const std::string& text) {
    std::string low = lower_copy(text);
    return low.find("$pbr-env") != std::string::npos || low.find("txenv") != std::string::npos ||
           low.find("radiance") != std::string::npos || low.find("irradiance") != std::string::npos ||
           low.find("envbrdf") != std::string::npos;
}

std::vector<std::string> extract_strings(const uint8_t* data, size_t start, size_t end) {
    std::vector<std::string> records;
    size_t pos = start;
    while (pos + 5 <= end) {
        uint32_t n = rd_u32(data + pos);
        if (n >= 1 && n <= 512 && pos + 4 + n <= end) {
            const uint8_t* raw = data + pos + 4;
            size_t vis = n;
            while (vis > 0 && raw[vis - 1] == 0) --vis;
            bool ascii = vis > 0;
            for (size_t i = 0; i < vis; ++i) {
                if (raw[i] < 32 || raw[i] >= 127) ascii = false;
            }
            if (ascii) {
                records.emplace_back(reinterpret_cast<const char*>(raw), vis);
                pos += 4 + n;
                continue;
            }
        }
        ++pos;
    }
    return records;
}

void pick_textures(const std::vector<std::string>& strings, std::string& material, std::string& albedo) {
    const char* types[] = {"stdonetex", "pbrmetal", "pbrmetalmasked", "pbrmetaldetail", "pbrmetalspec"};
    for (size_t i = 0; i < strings.size(); ++i) {
        std::string low = lower_copy(strings[i]);
        bool typed = low.rfind("m.", 0) == 0 || low.find(".m.") != std::string::npos;
        if (!typed) {
            for (const char* item : types) {
                if (low == item) typed = true;
            }
        }
        if (typed && material.empty()) material = strings[i];
        std::string next = i + 1 < strings.size() ? strings[i + 1] : "";
        if (is_env(strings[i]) || is_env(next)) continue;
        if ((low == "txalbedo" || low == "albedo" || low == "txdiffuse" || low == "diffuse" || low == "texture0") &&
            !next.empty() && albedo.empty()) {
            albedo = next;
        } else if (strings[i].size() >= 8 &&
                   (strings[i].find(".texture") != std::string::npos || strings[i].find(".tga") != std::string::npos ||
                    strings[i].find(".png") != std::string::npos || strings[i].find(".jpg") != std::string::npos)) {
            bool normal = low.find("normal") != std::string::npos || low.find("_n.") != std::string::npos;
            bool param = low.find("parameter") != std::string::npos || low.find("_p.") != std::string::npos;
            if (!normal && !param && albedo.empty() && !is_env(strings[i])) albedo = strings[i];
        }
    }
}

struct Hit {
    float score = 0;
    size_t vertex_offset = 0;
    int vc = 0;
    int stride = 0;
    Vfmt fmt;
    size_t iofs = 0;
    int index_count = 0;
    int index_size = 0;
    size_t tail = 0;
    std::string albedo;
    std::string material;
    bool set = false;
};

bool try_decode(const uint8_t* data, size_t size, size_t fmt_end, const std::string& fmt_text, SubMesh& mesh, size_t& start, size_t& end) {
    size_t nominal = fmt_end;
    if (fmt_end < size && data[fmt_end] == 0) nominal = fmt_end + 1;
    int token_stride = parse_vertex_format(fmt_text, 0).stride;
    size_t offsets[3] = {nominal, (nominal + 3) & ~size_t{3}, nominal + 4};
    Hit best;
    bool done = false;
    for (size_t cofs : offsets) {
        if (done || cofs + 12 > size) continue;
        for (int be = 1; be >= 0; --be) {
            if (done) break;
            uint32_t vc = be ? rd_u32be(data + cofs) : rd_u32(data + cofs);
            uint32_t ic_raw = be ? rd_u32be(data + cofs + 4) : rd_u32(data + cofs + 4);
            uint32_t stride = be ? rd_u32be(data + cofs + 8) : rd_u32(data + cofs + 8);
            if (vc < 3 || vc > 2000000) continue;
            if (stride < 12 || stride > 512 || stride % 4) continue;
            if (token_stride && token_stride > static_cast<int>(stride)) continue;
            Vfmt fmt = parse_vertex_format(fmt_text, static_cast<int>(stride));
            if (fmt.position + 12 > static_cast<int>(stride)) continue;
            if (fmt.uv >= 0 && fmt.uv + 8 > static_cast<int>(stride)) continue;
            if (fmt.normal >= 0 && fmt.normal + 12 > static_cast<int>(stride)) continue;
            size_t vertex_offset = cofs + 12;
            if (vertex_offset + static_cast<size_t>(vc) * stride > size) continue;
            if (!sample_ok(data, size, vertex_offset, static_cast<int>(vc), static_cast<int>(stride), fmt)) continue;
            size_t base_index = vertex_offset + static_cast<size_t>(vc) * stride;
            uint32_t candidates[2] = {ic_raw, 0};
            int ncand = 1;
            if (ic_raw > 0 && ic_raw * 3ull <= 6000000ull) candidates[ncand++] = ic_raw * 3;
            for (int ci = 0; ci < ncand; ++ci) {
                uint32_t index_count = candidates[ci];
                if (done || index_count < 3 || index_count % 3) continue;
                for (int index_size : {2, 4}) {
                    if (index_size == 2 && vc > 65535) continue;
                    size_t iofs = base_index;
                    if (!indices_ok(data, size, iofs, static_cast<int>(index_count), index_size, static_cast<int>(vc))) {
                        size_t iofs2 = (base_index + 3) & ~size_t{3};
                        if (iofs2 == iofs || !indices_ok(data, size, iofs2, static_cast<int>(index_count), index_size, static_cast<int>(vc))) {
                            continue;
                        }
                        iofs = iofs2;
                    }
                    float score = 20;
                    if (be) score += 15;
                    if (token_stride && static_cast<int>(stride) == token_stride) score += 10;
                    if (index_size == 2) score += 3;
                    size_t tail = iofs + static_cast<size_t>(index_count) * index_size;
                    auto strings = extract_strings(data, tail, std::min(size, tail + 4096));
                    std::string material;
                    std::string albedo;
                    pick_textures(strings, material, albedo);
                    if (!albedo.empty() || !material.empty()) score += 12;
                    if (!best.set || score > best.score) {
                        best.set = true;
                        best.score = score;
                        best.vertex_offset = vertex_offset;
                        best.vc = static_cast<int>(vc);
                        best.stride = static_cast<int>(stride);
                        best.fmt = fmt;
                        best.iofs = iofs;
                        best.index_count = static_cast<int>(index_count);
                        best.index_size = index_size;
                        best.tail = tail;
                        best.albedo = albedo;
                        best.material = material;
                    }
                    if (be && token_stride == static_cast<int>(stride) && score >= 45) done = true;
                }
            }
        }
    }
    if (!best.set) return false;
    mesh.format = fmt_text;
    mesh.albedo = best.albedo;
    mesh.material_type = best.material;
    mesh.positions.resize(static_cast<size_t>(best.vc) * 3);
    mesh.uvs.resize(static_cast<size_t>(best.vc) * 2);
    for (int v = 0; v < best.vc; ++v) {
        const uint8_t* src = data + best.vertex_offset + static_cast<size_t>(v) * best.stride;
        mesh.positions[v * 3] = rd_f32(src + best.fmt.position);
        mesh.positions[v * 3 + 1] = rd_f32(src + best.fmt.position + 4);
        mesh.positions[v * 3 + 2] = rd_f32(src + best.fmt.position + 8);
        if (best.fmt.uv >= 0) {
            mesh.uvs[v * 2] = rd_f32(src + best.fmt.uv);
            mesh.uvs[v * 2 + 1] = 1.f - rd_f32(src + best.fmt.uv + 4);
        }
    }
    mesh.indices.resize(best.index_count);
    for (int i = 0; i < best.index_count; ++i) {
        mesh.indices[i] = best.index_size == 2 ? rd_u16(data + best.iofs + i * 2) : rd_u32(data + best.iofs + i * 4);
    }
    start = best.vertex_offset;
    end = best.tail;
    return true;
}

}  // namespace

TrainzMesh parse_trainzmesh(const uint8_t* data, size_t size) {
    if (size < 20 || std::memcmp(data, "tzMF", 4) != 0) throw std::runtime_error("Not a tzMF .trainzmesh file");
    TrainzMesh mesh;
    mesh.version = static_cast<int>(rd_u32be(data + 4));
    uint32_t f1 = rd_u32be(data + 8);
    uint32_t f3 = rd_u32be(data + 16);
    int limit = 0;
    if (f3 > 0 && f3 < 10000) limit = static_cast<int>(f3);
    else if (f1 > 0 && f1 < 10000) limit = static_cast<int>(f1);
    std::vector<std::pair<size_t, size_t>> seen;
    for (size_t i = 0; i + 4 < size; ++i) {
        if (data[i] != 'S' || data[i + 1] < '0' || data[i + 1] > '9') continue;
        size_t j = i + 1;
        while (j < size && data[j] >= '0' && data[j] <= '9') ++j;
        if (j >= size || data[j] != '_') continue;
        size_t k = j + 1;
        while (k < size) {
            unsigned char c = data[k];
            if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_')) break;
            ++k;
        }
        std::string text(reinterpret_cast<const char*>(data + i), k - i);
        if (text.find("P3f") == std::string::npos) continue;
        SubMesh sub;
        size_t start = 0;
        size_t end = 0;
        if (!try_decode(data, size, k, text, sub, start, end)) continue;
        bool overlap = false;
        for (const auto& span : seen) {
            if (!(end <= span.first || start >= span.second)) overlap = true;
        }
        if (overlap) continue;
        seen.emplace_back(start, end);
        sub.name = "mesh_" + std::to_string(mesh.submeshes.size());
        mesh.submeshes.push_back(std::move(sub));
        if (limit && static_cast<int>(mesh.submeshes.size()) >= limit) break;
        i = k - 1;
    }
    if (mesh.submeshes.empty()) throw std::runtime_error("Failed to decode any tzMF vertex/index buffers");
    return mesh;
}
