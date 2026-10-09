#include "wav.h"

#include "bin.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>

namespace {

uint32_t fourcc(const char* text) {
    return static_cast<uint32_t>(static_cast<uint8_t>(text[0])) | (static_cast<uint32_t>(static_cast<uint8_t>(text[1])) << 8) |
           (static_cast<uint32_t>(static_cast<uint8_t>(text[2])) << 16) | (static_cast<uint32_t>(static_cast<uint8_t>(text[3])) << 24);
}

void append_u16(std::vector<uint8_t>& out, uint16_t value) {
    out.push_back(static_cast<uint8_t>(value));
    out.push_back(static_cast<uint8_t>(value >> 8));
}

void append_u32(std::vector<uint8_t>& out, uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8) out.push_back(static_cast<uint8_t>(value >> shift));
}

double rms_of(const int16_t* data, size_t count) {
    if (count == 0) return 0;
    double sum = 0;
    for (size_t i = 0; i < count; ++i) {
        const double sample = data[i];
        sum += sample * sample;
    }
    return std::sqrt(sum / static_cast<double>(count)) / 32768.0;
}

std::string stem_of(const std::string& key) {
    const auto slash = key.find_last_of("/\\");
    std::string name = slash == std::string::npos ? key : key.substr(slash + 1);
    const auto dot = name.find_last_of('.');
    if (dot != std::string::npos) name.resize(dot);
    return name;
}

}  // namespace

PcmClip read_wav_pcm16(const uint8_t* data, size_t size) {
    need(size, 12, "not a wav");
    if (std::memcmp(data, "RIFF", 4) != 0 || std::memcmp(data + 8, "WAVE", 4) != 0) throw std::runtime_error("not a wav");
    int channels = 0;
    int bits = 0;
    int rate = 0;
    const uint8_t* pcm = nullptr;
    size_t pcm_size = 0;
    size_t pos = 12;
    while (pos + 8 <= size) {
        const uint32_t id = rd_u32(data + pos);
        const uint32_t chunk = rd_u32(data + pos + 4);
        pos += 8;
        if (pos + chunk > size) break;
        if (id == fourcc("fmt ")) {
            need(chunk, 16, "bad fmt");
            channels = rd_u16(data + pos + 2);
            rate = static_cast<int>(rd_u32(data + pos + 4));
            bits = rd_u16(data + pos + 14);
        } else if (id == fourcc("data")) {
            pcm = data + pos;
            pcm_size = chunk;
        }
        pos += chunk + (chunk & 1);
    }
    if (channels < 1 || rate < 1 || pcm == nullptr) throw std::runtime_error("wav missing pcm");
    if (bits != 8 && bits != 16 && bits != 24 && bits != 32) throw std::runtime_error("unsupported sample width");
    const size_t frame = static_cast<size_t>(channels * (bits / 8));
    if (frame == 0 || pcm_size < frame) throw std::runtime_error("wav missing pcm");
    const size_t frames = pcm_size / frame;
    PcmClip clip;
    clip.rate = rate;
    clip.channels = channels;
    clip.samples.resize(frames);
    for (size_t i = 0; i < frames; ++i) {
        int64_t mixed = 0;
        const uint8_t* frame_bytes = pcm + i * frame;
        for (int ch = 0; ch < channels; ++ch) {
            const uint8_t* sample = frame_bytes + static_cast<size_t>(ch * (bits / 8));
            int32_t value = 0;
            if (bits == 8) value = (static_cast<int32_t>(sample[0]) - 128) << 8;
            else if (bits == 16) value = static_cast<int16_t>(sample[0] | (sample[1] << 8));
            else if (bits == 24) {
                value = sample[0] | (sample[1] << 8) | (sample[2] << 16);
                if (value & 0x800000) value -= 0x1000000;
                value >>= 8;
            } else value = static_cast<int32_t>(rd_u32(sample)) >> 16;
            mixed += value;
        }
        clip.samples[i] = static_cast<int16_t>(mixed / channels);
    }
    return clip;
}

std::vector<uint8_t> write_wav_pcm16(const std::vector<int16_t>& samples, int rate) {
    const uint32_t data_bytes = static_cast<uint32_t>(samples.size() * 2);
    std::vector<uint8_t> out;
    out.insert(out.end(), {'R', 'I', 'F', 'F'});
    append_u32(out, 36 + data_bytes);
    out.insert(out.end(), {'W', 'A', 'V', 'E', 'f', 'm', 't', ' '});
    append_u32(out, 16);
    append_u16(out, 1);
    append_u16(out, 1);
    append_u32(out, static_cast<uint32_t>(rate));
    append_u32(out, static_cast<uint32_t>(rate) * 2);
    append_u16(out, 2);
    append_u16(out, 16);
    out.insert(out.end(), {'d', 'a', 't', 'a'});
    append_u32(out, data_bytes);
    for (int16_t sample : samples) append_u16(out, static_cast<uint16_t>(sample));
    return out;
}

std::vector<QcFinding> analyze_pcm(const std::vector<int16_t>& samples, int rate, const std::string& key) {
    std::vector<QcFinding> findings;
    const std::string stem = stem_of(key);
    const double duration = rate > 0 ? static_cast<double>(samples.size()) / rate : 0;
    if (duration < 0.35) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "too short %.2fs", duration);
        findings.push_back({"short", "fail", buf});
    }
    const double full = rms_of(samples.data(), samples.size());
    if (full < 0.008) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "near-silent RMS=%.5f", full);
        findings.push_back({"quiet", "fail", buf});
    }
    if (rate > 0) {
        const int step = std::max(1, static_cast<int>(rate * 0.25));
        std::vector<double> windows;
        for (size_t i = 0; i < samples.size(); i += static_cast<size_t>(step)) {
            const size_t count = std::min(samples.size() - i, static_cast<size_t>(step));
            windows.push_back(rms_of(samples.data() + i, count));
        }
        const bool trans = stem.find('-') != std::string::npos && (stem.size() < 5 || stem.compare(stem.size() - 5, 5, "-stop") != 0);
        const bool steady = !trans && stem.find("stop") == std::string::npos && stem != "start";
        double click = 0;
        if (samples.size() >= 72) {
            double mean_a = 0;
            double mean_b = 0;
            for (int i = 0; i < 32; ++i) {
                mean_a += samples[samples.size() - 32 + static_cast<size_t>(i)];
                mean_b += samples[static_cast<size_t>(i)];
            }
            const double jump = std::abs(static_cast<double>(samples[0]) - samples.back()) / 32768.0;
            click = jump + 0.5 * std::abs(mean_a - mean_b) / 32.0 / 32768.0;
        }
        if (steady && click >= 0.12) {
            char buf[64];
            std::snprintf(buf, sizeof(buf), "loop wrap click risk=%.3f", click);
            findings.push_back({"click", click >= 0.25 ? "fail" : "warn", buf});
        }
        if (steady && windows.size() >= 4) {
            const double head = (windows[0] + windows[1]) / 2.0;
            const double tail = (windows[windows.size() - 2] + windows.back()) / 2.0;
            if (head > 1e-6 && tail > 1e-6) {
                const double seam = std::abs(20.0 * std::log10(std::max(head, 1e-9) / std::max(tail, 1e-9)));
                const double ratio = std::max(head, tail) / std::max(std::min(head, tail), 1e-9);
                if (seam >= 2.5 || ratio >= 1.35) {
                    char buf[64];
                    std::snprintf(buf, sizeof(buf), "loop seam uneven head/tail Δ=%.1f dB", seam);
                    findings.push_back({"uneven_loop", seam >= 4.0 ? "fail" : "warn", buf});
                }
            }
        }
    }
    for (QcFinding& glitch : scan_glitches(samples, rate)) findings.push_back(std::move(glitch));
    if (findings.empty()) findings.push_back({"ok", "ok", "ok"});
    return findings;
}

std::vector<int16_t> resample_linear(const std::vector<int16_t>& samples, int from_rate, int to_rate) {
    if (from_rate == to_rate || from_rate < 1 || to_rate < 1 || samples.size() < 2) return samples;
    const size_t count = static_cast<size_t>(static_cast<double>(samples.size()) * to_rate / from_rate);
    std::vector<int16_t> out(count);
    for (size_t i = 0; i < count; ++i) {
        const double pos = static_cast<double>(i) * from_rate / to_rate;
        const size_t a = std::min(static_cast<size_t>(pos), samples.size() - 1);
        const size_t b = std::min(a + 1, samples.size() - 1);
        const double frac = pos - static_cast<double>(a);
        out[i] = static_cast<int16_t>(std::lround(samples[a] * (1.0 - frac) + samples[b] * frac));
    }
    return out;
}

namespace {
size_t fade_len(int rate, size_t limit) { return std::min(static_cast<size_t>(std::max(rate, 1) / 4), limit); }
int16_t clamp16(double v) { return static_cast<int16_t>(std::lround(std::clamp(v, -32768.0, 32767.0))); }
}  // namespace

std::vector<int16_t> make_loop(const std::vector<int16_t>& s, int rate) {
    const size_t f = fade_len(rate, s.size() / 4);
    if (f < 2) return s;
    const size_t len = s.size() - f;
    std::vector<int16_t> out(s.begin(), s.begin() + static_cast<std::ptrdiff_t>(len));
    for (size_t i = 0; i < f; ++i) {
        const double t = (static_cast<double>(i) + 0.5) / static_cast<double>(f) * 1.5707963267948966;
        out[i] = clamp16(s[i] * std::sin(t) + s[len + i] * std::cos(t));
    }
    return out;
}

std::vector<int16_t> make_transition(const std::vector<int16_t>& from, const std::vector<int16_t>& to, int rate) {
    const size_t f = fade_len(rate, std::min(from.size(), to.size()) / 2);
    if (f < 2) return from;
    std::vector<int16_t> out(from.begin(), from.end());
    for (size_t i = 0; i < f; ++i) {
        const double t = (static_cast<double>(i) + 0.5) / static_cast<double>(f) * 1.5707963267948966;
        out[from.size() - f + i] = clamp16(from[from.size() - f + i] * std::cos(t) + to[to.size() - f + i] * std::sin(t));
    }
    return out;
}

std::vector<int16_t> apply_gain_db(const std::vector<int16_t>& samples, double db) {
    if (db == 0.0) return samples;
    const double g = std::pow(10.0, db / 20.0);
    std::vector<int16_t> out(samples.size());
    for (size_t i = 0; i < samples.size(); ++i) out[i] = clamp16(samples[i] * g);
    return out;
}

// ponytail: local-scale jump detector. |x[i]-x[i-1]| vs RMS of neighbouring differences (+-1024 samples, self excluded).
// Engine noise stays under ~9x locally; real pops/splices reach 14x+ (measured on idle 2 @5.83s, idle 3 @7.07s).
// Ceiling: a very sparse tonal clip has tiny local scale, so the absolute floor (kMinJump) guards false hits.
std::vector<QcFinding> scan_glitches(const std::vector<int16_t>& s, int rate, size_t limit) {
    std::vector<QcFinding> out;
    constexpr size_t W = 1024;
    constexpr double kWarn = 10.0, kFail = 18.0, kMinJump = 600.0;
    if (rate < 1 || s.size() < 2 * W + 4) return out;
    const size_t n = s.size() - 1;  // number of differences
    std::vector<double> prefix(n + 1, 0.0);
    for (size_t i = 0; i < n; ++i) {
        const double d = static_cast<double>(s[i + 1]) - s[i];
        prefix[i + 1] = prefix[i] + d * d;
    }
    struct Hit { size_t at; double ratio; double jump; bool clip; };
    std::vector<Hit> hits;
    for (size_t i = W; i + W < n; ++i) {
        const double d = static_cast<double>(s[i + 1]) - s[i];
        const double self = d * d;
        if (self < kMinJump * kMinJump) continue;
        const double scale2 = (prefix[i + W] - prefix[i - W] - self) / (2.0 * W - 1.0);
        const double ratio = std::abs(d) / std::sqrt(scale2 + 1.0);
        if (ratio < kWarn) continue;
        // merge events within 20 ms into the strongest one
        if (!hits.empty() && i - hits.back().at < static_cast<size_t>(rate / 50)) {
            if (ratio > hits.back().ratio) hits.back() = {i, ratio, d, false};
            continue;
        }
        hits.push_back({i, ratio, d, false});
    }
    // clipping: runs of >=4 full-scale samples, reported once as a summary (loud engine loops clip often)
    size_t clip_runs = 0, first_clip = 0;
    for (size_t i = 0; i + 4 < s.size();) {
        size_t j = i;
        while (j < s.size() && (s[j] >= 32760 || s[j] <= -32760)) ++j;
        if (j - i >= 4) {
            if (clip_runs++ == 0) first_clip = i;
            i = j + static_cast<size_t>(rate / 50);
        } else i = std::max(j, i + 1);
    }
    // dropout: 10 ms RMS >18 dB under both +-60 ms neighbours
    const size_t hop = std::max<size_t>(1, static_cast<size_t>(rate / 100));
    const size_t blocks = s.size() / hop;
    std::vector<double> db(blocks);
    for (size_t b = 0; b < blocks; ++b) {
        double sum = 0;
        for (size_t k = 0; k < hop; ++k) sum += static_cast<double>(s[b * hop + k]) * s[b * hop + k];
        db[b] = 20.0 * std::log10(std::sqrt(sum / static_cast<double>(hop)) + 1.0);
    }
    for (size_t b = 7; b + 7 < blocks; ++b) {
        double around = 0;
        for (size_t k = 1; k <= 6; ++k) around += db[b - k] + db[b + k];
        around /= 12.0;
        if (around > 40.0 && around - db[b] > 18.0) {
            hits.push_back({b * hop, 50.0, around - db[b], true});
            b += 6;
        }
    }
    std::sort(hits.begin(), hits.end(), [](const Hit& a, const Hit& b) { return a.ratio > b.ratio; });
    if (hits.size() > limit) hits.resize(limit);
    std::sort(hits.begin(), hits.end(), [](const Hit& a, const Hit& b) { return a.at < b.at; });
    if (clip_runs > 0) {
        char buf[160];
        std::snprintf(buf, sizeof(buf), "%.3fs  clipping: %zu flat full-scale runs (first shown)", static_cast<double>(first_clip) / rate, clip_runs);
        QcFinding f;
        f.time = static_cast<double>(first_clip) / rate;
        f.kind = "clip";
        f.severity = "warn";
        f.message = buf;
        out.push_back(std::move(f));
    }
    for (const Hit& h : hits) {
        char buf[160];
        const double t = static_cast<double>(h.at) / rate;
        QcFinding f;
        f.time = t;
        if (h.clip) {
            std::snprintf(buf, sizeof(buf), "%.3fs  dropout -%.0f dB for ~10ms", t, h.jump);
            f.kind = "dropout"; f.severity = "fail";
        } else {
            std::snprintf(buf, sizeof(buf), "%.3fs  jump %.0fx local level (step %.0f)", t, h.ratio, h.jump);
            f.kind = "glitch"; f.severity = h.ratio >= kFail ? "fail" : "warn";
        }
        f.message = buf;
        out.push_back(std::move(f));
    }
    return out;
}
