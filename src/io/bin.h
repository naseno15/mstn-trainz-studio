#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

inline uint32_t rd_u32(const uint8_t* p) {
    uint32_t value = 0;
    std::memcpy(&value, p, 4);
    return value;
}

inline int32_t rd_i32(const uint8_t* p) {
    return static_cast<int32_t>(rd_u32(p));
}

inline uint32_t rd_u32be(const uint8_t* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

inline uint64_t rd_u64be(const uint8_t* p) {
    uint64_t value = 0;
    for (int i = 0; i < 8; ++i) value = (value << 8) | p[i];
    return value;
}

inline uint64_t rd_u64(const uint8_t* p) {
    uint64_t value = 0;
    std::memcpy(&value, p, 8);
    return value;
}

inline uint16_t rd_u16(const uint8_t* p) {
    uint16_t value = 0;
    std::memcpy(&value, p, 2);
    return value;
}

inline float rd_f32(const uint8_t* p) {
    float value = 0;
    std::memcpy(&value, p, 4);
    return value;
}

inline void wr_u32(std::vector<uint8_t>& out, uint32_t value) {
    uint8_t bytes[4];
    std::memcpy(bytes, &value, 4);
    out.insert(out.end(), bytes, bytes + 4);
}

inline void wr_i32(std::vector<uint8_t>& out, int32_t value) {
    wr_u32(out, static_cast<uint32_t>(value));
}

inline void wr_f32(std::vector<uint8_t>& out, float value) {
    uint8_t bytes[4];
    std::memcpy(bytes, &value, 4);
    out.insert(out.end(), bytes, bytes + 4);
}

inline void need(size_t have, size_t want, const char* what) {
    if (have < want) throw std::runtime_error(what);
}
