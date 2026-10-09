#pragma once

#include <cstdint>
#include <string>
#include <vector>

enum class ChumpType : int {
    Soup = 0,
    Int = 1,
    Float = 2,
    Text = 3,
    Raw = 4,
    Null = 5,
    Kuid = 13,
};

struct ChumpTag {
    std::string name;
    ChumpType type = ChumpType::Null;
    std::vector<ChumpTag> children;
    std::vector<int32_t> ints;
    std::vector<float> floats;
    std::string text;
    std::vector<uint8_t> raw;
};

struct ChumpFile {
    uint32_t version = 1;
    uint32_t reserved = 0;
    std::vector<ChumpTag> root;
};

ChumpFile read_chump(const uint8_t* data, size_t size);
std::vector<uint8_t> encode_chump(const ChumpFile& file);
const ChumpTag* find_tag(const std::vector<ChumpTag>& tags, const std::string& name);
