#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct SubMesh {
    std::string name;
    std::string format;
    std::vector<float> positions;
    std::vector<float> uvs;
    std::vector<uint32_t> indices;
    std::string albedo;
    std::string material_type;
};

struct TrainzMesh {
    int version = 0;
    std::vector<SubMesh> submeshes;
};

TrainzMesh parse_trainzmesh(const uint8_t* data, size_t size);
