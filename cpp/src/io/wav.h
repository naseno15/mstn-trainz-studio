#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct PcmClip {
    int rate = 0;
    int channels = 1;
    std::vector<int16_t> samples;
};

struct QcFinding {
    std::string kind;
    std::string severity;
    std::string message;
};

PcmClip read_wav_pcm16(const uint8_t* data, size_t size);
std::vector<uint8_t> write_wav_pcm16(const std::vector<int16_t>& samples, int rate);
std::vector<QcFinding> analyze_pcm(const std::vector<int16_t>& samples, int rate, const std::string& key);
