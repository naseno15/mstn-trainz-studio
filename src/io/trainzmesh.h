#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct SubMesh {
    std::string name;
    std::string format;
    std::vector<float> positions;
    std::vector<float> normals;
    std::vector<float> uvs;
    std::vector<uint32_t> indices;
    std::string albedo;
    std::string normal_map;
    std::string parameter_map;
    std::string material_type;
    size_t tail_off = 0;
};

struct TrainzMesh {
    int version = 0;
    std::vector<SubMesh> submeshes;
};

struct TzTex {
    std::string key;
    std::string value;
    size_t value_off = 0;
};

struct TzMaterial {
    std::string type_name;
    std::string name;
    std::string vertex_format;
    size_t type_off = 0;
    size_t name_off = 0;
    size_t color_off = 0;
    float color[4] = {1.f, 1.f, 1.f, 1.f};
    float emissive[4] = {0.f, 0.f, 0.f, 1.f};
    float specular[4] = {0.8f, 0.8f, 0.8f, 1.f};
    float spec_power = 25.f;
    int emissive_off = -1;
    int specular_off = -1;
    int spec_power_off = -1;
    std::vector<TzTex> textures;
};

struct TzAttachment {
    std::string name;
    float orient[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};  // row-major, each row is an axis
    float pos[3] = {};
    float quat[4] = {0, 0, 0, 1};  // xyzw as stored
    size_t off = 0;                // first of the 7 BE floats
};

TrainzMesh parse_trainzmesh(const uint8_t* data, size_t size);
std::vector<TzMaterial> parse_tzmf_materials(const uint8_t* data, size_t size);
// u8 len + "a.name" + 7× BE float32 (Z-up pos + quat xyzw). Same hits as the Python loader.
std::vector<TzAttachment> parse_trainzmesh_attachments(const uint8_t* data, size_t size);
