#include "wave_player.h"

#ifdef _WIN32
#include <windows.h>
#include <mmsystem.h>

std::vector<std::string> WavePlayer::devices() {
    std::vector<std::string> names;
    for (UINT i = 0; i < waveOutGetNumDevs(); ++i) {
        WAVEOUTCAPSA caps{};
        waveOutGetDevCapsA(i, &caps, sizeof(caps));
        names.emplace_back(caps.szPname);
    }
    return names;
}

void WavePlayer::start(std::vector<int16_t> head, std::vector<int16_t> tail, bool loop_tail, int rate) {
    stop();
    if (head.empty() && tail.empty()) return;
    head_ = std::move(head);
    tail_ = std::move(tail);
    loop_ = loop_tail && !tail_.empty();
    WAVEFORMATEX fmt{};
    fmt.wFormatTag = WAVE_FORMAT_PCM;
    fmt.nChannels = 1;
    fmt.nSamplesPerSec = static_cast<DWORD>(rate);
    fmt.wBitsPerSample = 16;
    fmt.nBlockAlign = 2;
    fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * 2;
    HWAVEOUT dev = nullptr;
    if (waveOutOpen(&dev, device_ < 0 ? WAVE_MAPPER : static_cast<UINT>(device_), &fmt, 0, 0, CALLBACK_NULL) != MMSYSERR_NOERROR) return;
    dev_ = dev;
    auto* hdr = new WAVEHDR[2]();
    hdr_ = hdr;
    auto submit = [&](WAVEHDR& h, std::vector<int16_t>& data, bool loop) {
        if (data.empty()) return;
        h.lpData = reinterpret_cast<LPSTR>(data.data());
        h.dwBufferLength = static_cast<DWORD>(data.size() * 2);
        if (loop) {
            h.dwFlags = WHDR_BEGINLOOP | WHDR_ENDLOOP;
            h.dwLoops = 0xFFFFFFFFu;
        }
        waveOutPrepareHeader(dev, &h, sizeof(h));
        waveOutWrite(dev, &h, sizeof(h));
    };
    submit(hdr[0], head_, false);
    submit(hdr[1], tail_, loop_);
}

void WavePlayer::stop() {
    if (!dev_) return;
    auto dev = static_cast<HWAVEOUT>(dev_);
    auto* hdr = static_cast<WAVEHDR*>(hdr_);
    waveOutReset(dev);
    for (int i = 0; i < 2; ++i)
        if (hdr[i].dwFlags & WHDR_PREPARED) waveOutUnprepareHeader(dev, &hdr[i], sizeof(WAVEHDR));
    waveOutClose(dev);
    delete[] hdr;
    dev_ = nullptr;
    hdr_ = nullptr;
}

bool WavePlayer::playing() const {
    if (!dev_) return false;
    if (loop_) return true;
    auto* hdr = static_cast<WAVEHDR*>(hdr_);
    const WAVEHDR& last = tail_.empty() ? hdr[0] : hdr[1];
    return !(last.dwFlags & WHDR_DONE);
}

size_t WavePlayer::position() const {
    if (!dev_) return 0;
    MMTIME t{};
    t.wType = TIME_SAMPLES;
    if (waveOutGetPosition(static_cast<HWAVEOUT>(dev_), &t, sizeof(t)) != MMSYSERR_NOERROR || t.wType != TIME_SAMPLES) return 0;
    return t.u.sample;
}

#elif defined(__APPLE__)
#include <AudioToolbox/AudioToolbox.h>

#include <atomic>
#include <cstring>

namespace {

struct MacPlay {
    AudioQueueRef queue = nullptr;
    AudioQueueBufferRef head_buf = nullptr;
    AudioQueueBufferRef tail_buf = nullptr;
    WavePlayer* owner = nullptr;
    std::atomic<bool> alive{true};
    std::atomic<bool> looping{false};
    std::atomic<bool> done{false};
    std::atomic<uint64_t> samples_played{0};
};

void mac_callback(void* user, AudioQueueRef queue, AudioQueueBufferRef buf) {
    auto* state = static_cast<MacPlay*>(user);
    if (!state || !state->alive.load()) return;
    const UInt32 bytes = buf->mAudioDataByteSize;
    state->samples_played.fetch_add(bytes / 2, std::memory_order_relaxed);
    if (state->looping.load() && buf == state->tail_buf && state->alive.load()) {
        AudioQueueEnqueueBuffer(queue, buf, 0, nullptr);
        return;
    }
    if ((!state->looping.load() || buf != state->tail_buf) && buf == (state->tail_buf ? state->tail_buf : state->head_buf))
        state->done.store(true);
}

}  // namespace

std::vector<std::string> WavePlayer::devices() { return {"Default"}; }

void WavePlayer::start(std::vector<int16_t> head, std::vector<int16_t> tail, bool loop_tail, int rate) {
    stop();
    if (head.empty() && tail.empty()) return;
    head_ = std::move(head);
    tail_ = std::move(tail);
    loop_ = loop_tail && !tail_.empty();

    auto* state = new MacPlay();
    state->owner = this;
    state->looping.store(loop_);
    hdr_ = state;

    AudioStreamBasicDescription fmt{};
    fmt.mSampleRate = rate;
    fmt.mFormatID = kAudioFormatLinearPCM;
    fmt.mFormatFlags = kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked;
    fmt.mFramesPerPacket = 1;
    fmt.mChannelsPerFrame = 1;
    fmt.mBitsPerChannel = 16;
    fmt.mBytesPerPacket = 2;
    fmt.mBytesPerFrame = 2;

    if (AudioQueueNewOutput(&fmt, mac_callback, state, nullptr, nullptr, 0, &state->queue) != noErr) {
        delete state;
        hdr_ = nullptr;
        return;
    }
    dev_ = state->queue;

    auto enqueue = [&](AudioQueueBufferRef* slot, const std::vector<int16_t>& data) -> bool {
        if (data.empty()) return true;
        AudioQueueBufferRef buf = nullptr;
        const UInt32 bytes = static_cast<UInt32>(data.size() * 2);
        if (AudioQueueAllocateBuffer(state->queue, bytes, &buf) != noErr) return false;
        std::memcpy(buf->mAudioData, data.data(), bytes);
        buf->mAudioDataByteSize = bytes;
        *slot = buf;
        return AudioQueueEnqueueBuffer(state->queue, buf, 0, nullptr) == noErr;
    };

    if (!enqueue(&state->head_buf, head_) || !enqueue(&state->tail_buf, tail_)) {
        stop();
        return;
    }
    if (AudioQueueStart(state->queue, nullptr) != noErr) stop();
}

void WavePlayer::stop() {
    auto* state = static_cast<MacPlay*>(hdr_);
    if (!state) return;
    state->alive.store(false);
    state->looping.store(false);
    if (state->queue) {
        AudioQueueStop(state->queue, true);
        AudioQueueDispose(state->queue, true);
    }
    delete state;
    hdr_ = nullptr;
    dev_ = nullptr;
}

bool WavePlayer::playing() const {
    auto* state = static_cast<MacPlay*>(hdr_);
    if (!state || !state->queue) return false;
    if (loop_) return true;
    return !state->done.load();
}

size_t WavePlayer::position() const {
    auto* state = static_cast<MacPlay*>(hdr_);
    if (!state || !state->queue) return 0;
    AudioTimeStamp ts{};
    if (AudioQueueGetCurrentTime(state->queue, nullptr, &ts, nullptr) == noErr && (ts.mFlags & kAudioTimeStampSampleTimeValid))
        return static_cast<size_t>(ts.mSampleTime > 0 ? ts.mSampleTime : 0);
    return static_cast<size_t>(state->samples_played.load());
}

#else
std::vector<std::string> WavePlayer::devices() { return {}; }
void WavePlayer::start(std::vector<int16_t>, std::vector<int16_t>, bool, int) {}
void WavePlayer::stop() {}
bool WavePlayer::playing() const { return false; }
size_t WavePlayer::position() const { return 0; }
#endif
