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
#else
std::vector<std::string> WavePlayer::devices() { return {}; }
std::vector<std::string> WavePlayer::devices() {
    std::vector<std::string> names;
    for (UINT i = 0; i < waveOutGetNumDevs(); ++i) {
        WAVEOUTCAPSA caps{};
        waveOutGetDevCapsA(i, &caps, sizeof(caps));
        names.emplace_back(caps.szPname);
    }
    return names;
}

void WavePlayer::start(std::vector<int16_t>, std::vector<int16_t>, bool, int) {}
void WavePlayer::stop() {}
bool WavePlayer::playing() const { return false; }
size_t WavePlayer::position() const { return 0; }
#endif
