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
    double time = -1;  // seconds into the clip, -1 = whole clip
};

PcmClip read_wav_pcm16(const uint8_t* data, size_t size);
std::vector<uint8_t> write_wav_pcm16(const std::vector<int16_t>& samples, int rate);
std::vector<QcFinding> analyze_pcm(const std::vector<int16_t>& samples, int rate, const std::string& key);

// Whole-track scan for pops/jumps/dropouts/clipping, time-stamped. Strongest events first-cut to `limit`, returned in time order.
std::vector<QcFinding> scan_glitches(const std::vector<int16_t>& samples, int rate, size_t limit = 12);
// Gain in dB with clipping.
std::vector<int16_t> apply_gain_db(const std::vector<int16_t>& samples, double db);
// Linear resample (mono). ponytail: no low-pass; fine for A/B preview and loop fixes at near-equal rates.
std::vector<int16_t> resample_linear(const std::vector<int16_t>& samples, int from_rate, int to_rate);
// Seamless loop: last f samples' continuation is faded into the head (equal-power), clip shortened by f.
std::vector<int16_t> make_loop(const std::vector<int16_t>& samples, int rate);
// Bake a handoff: tail of `from` is equal-power crossfaded into the end of loop `to`, so playing `to` from its start continues seamlessly.
std::vector<int16_t> make_transition(const std::vector<int16_t>& from, const std::vector<int16_t>& to, int rate);
