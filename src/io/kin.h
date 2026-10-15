#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct KinXform {
    float pos[3] = {};
    float quat[4] = {0.f, 0.f, 0.f, 1.f};  // xyzw
    float scale[3] = {1.f, 1.f, 1.f};
};

struct KinClip {
    bool ok = false;
    std::string error;
    int tick = 60;
    std::vector<std::string> bones;
    std::vector<std::vector<KinXform>> frames;  // [frame][bone]
};

// JIRF .kin: BONE names plus one FRAM (pos, quat, scale) per bone per frame.
KinClip parse_kin(const uint8_t* data, size_t size);
// Every bone name must occur in the mesh bytes as a whole name. missing receives the first absent name.
bool kin_bones_in_mesh(const KinClip& clip, const uint8_t* mesh, size_t mesh_size, std::string* missing);
