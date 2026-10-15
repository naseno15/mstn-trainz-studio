#include "kin.h"

#include "bin.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>

namespace {

bool tag_at(const uint8_t* data, size_t size, size_t i, const char* tag) {
    return i + 4 <= size && std::memcmp(data + i, tag, 4) == 0;
}

bool ascii_name(const uint8_t* p, uint32_t n) {
    if (n < 1 || n > 128) return false;
    for (uint32_t i = 0; i < n; ++i)
        if (p[i] < 32 || p[i] > 126) return false;
    return true;
}

}  // namespace

KinClip parse_kin(const uint8_t* data, size_t size) {
    KinClip clip;
    if (!data || size < 36 || std::memcmp(data, "JIRF", 4) != 0) {
        clip.error = "not a JIRF .kin";
        return clip;
    }
    const uint32_t tick = rd_u32(data + 32);
    if (tick >= 1 && tick <= 240) clip.tick = static_cast<int>(tick);
    for (size_t i = 0; i + 16 <= size; ++i) {
        if (!tag_at(data, size, i, "BONE")) continue;
        if (rd_u32(data + i + 4) != 0 || rd_u32(data + i + 8) != 0x64) continue;
        const uint32_t nlen = rd_u32(data + i + 12);
        if (i + 16 + nlen > size || !ascii_name(data + i + 16, nlen)) continue;
        clip.bones.emplace_back(reinterpret_cast<const char*>(data + i + 16), nlen);
        i += 15 + nlen;
    }
    if (clip.bones.empty()) {
        clip.error = "no bones in this .kin";
        return clip;
    }
    const int bones = static_cast<int>(clip.bones.size());
    std::vector<std::vector<KinXform>> by_frame;
    for (size_t i = 0; i + 56 <= size; ++i) {
        if (!tag_at(data, size, i, "FRAM")) continue;
        if (rd_u32(data + i + 8) != 0x65) continue;
        const uint32_t frame = rd_u32(data + i + 12);
        if (frame > 100000) continue;
        KinXform xf;
        const uint8_t* f = data + i + 16;
        bool finite = true;
        for (int k = 0; k < 3; ++k) finite = finite && std::isfinite(xf.pos[k] = rd_f32(f + k * 4));
        for (int k = 0; k < 4; ++k) finite = finite && std::isfinite(xf.quat[k] = rd_f32(f + 12 + k * 4));
        for (int k = 0; k < 3; ++k) finite = finite && std::isfinite(xf.scale[k] = rd_f32(f + 28 + k * 4));
        if (!finite) continue;
        if (by_frame.size() <= frame) by_frame.resize(frame + 1);
        if (static_cast<int>(by_frame[frame].size()) < bones) by_frame[frame].push_back(xf);
        i += 55;
    }
    by_frame.erase(std::remove_if(by_frame.begin(), by_frame.end(), [&](const std::vector<KinXform>& row) { return static_cast<int>(row.size()) != bones; }), by_frame.end());
    if (by_frame.empty()) {
        clip.error = "no frames in this .kin";
        return clip;
    }
    clip.frames = std::move(by_frame);
    clip.ok = true;
    return clip;
}

bool kin_bones_in_mesh(const KinClip& clip, const uint8_t* mesh, size_t mesh_size, std::string* missing) {
    if (!clip.ok || !mesh || mesh_size == 0) {
        if (missing) *missing = clip.bones.empty() ? std::string() : clip.bones.front();
        return false;
    }
    const uint8_t* end = mesh + mesh_size;
    auto name_char = [](uint8_t c) { return std::isalnum(c) || c == '_' || c == '.' || c == '-'; };
    for (const std::string& bone : clip.bones) {
        if (bone.empty()) continue;
        // Whole name only: "r.ats" must not match inside "r.atsleft".
        const uint8_t* hit = mesh;
        while ((hit = std::search(hit, end, bone.begin(), bone.end())) != end) {
            const uint8_t* after = hit + bone.size();
            if (after == end || !name_char(*after)) break;
            ++hit;
        }
        if (hit == end) {
            if (missing) *missing = bone;
            return false;
        }
    }
    return true;
}
