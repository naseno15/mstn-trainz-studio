#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct MeshPart {
    std::string name;
    std::string albedo;
    std::string normal_map;
    std::vector<float> positions;
    std::vector<uint32_t> indices;
    std::vector<float> normals;
    std::vector<float> uvs;
};

struct ImAttachment {
    std::string name;
    float orient[9] = {};
    float pos[3] = {};
};

struct ImView {
    std::vector<MeshPart> parts;
    std::vector<ImAttachment> atts;
};

std::vector<MeshPart> parse_im_parts(const uint8_t* data, size_t size);
std::vector<ImAttachment> parse_im_attachments(const uint8_t* data, size_t size);
// GEOM parts plus a marker at each ATCH point. Throws only when both are missing.
ImView parse_im_view(const uint8_t* data, size_t size);
