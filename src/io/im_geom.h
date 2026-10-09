#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct MeshPart {
    std::string name;
    std::vector<float> positions;
    std::vector<uint32_t> indices;
    std::vector<float> normals;
};

std::vector<MeshPart> parse_im_parts(const uint8_t* data, size_t size);
