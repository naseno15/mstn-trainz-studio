#pragma once

#include <cstdint>
#include <string>
#include <vector>

// Minimal waveOut player: `head` plays once, then `tail` plays (looped forever if loop_tail). Windows only; elsewhere a no-op.
class WavePlayer {
public:
    ~WavePlayer() { stop(); }
    static std::vector<std::string> devices();  // output device names; index i -> waveOut device i
    void set_device(int index) { device_ = index; }  // -1 = Windows default
    void start(std::vector<int16_t> head, std::vector<int16_t> tail, bool loop_tail, int rate);
    void stop();
    bool playing() const;
    size_t head_size() const { return head_.size(); }
    size_t tail_size() const { return tail_.size(); }
    size_t position() const;  // samples since start

private:
    std::vector<int16_t> head_, tail_;
    bool loop_ = false;
    int device_ = -1;
    void* dev_ = nullptr;
    void* hdr_ = nullptr;  // WAVEHDR[2]
};
