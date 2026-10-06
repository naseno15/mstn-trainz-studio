"""Fix Trainz loops: trim · heal holes · seamless wrap · optional level-match."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def rms(a: np.ndarray) -> float:
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(a.astype(np.float64)))) + 1e-12)


def trim_leading_to_energy(
    mono: np.ndarray,
    *,
    sample_rate: int,
    keep_s: float = 0.06,
    abs_thresh: float = 400.0,
    win_s: float = 0.01,
) -> np.ndarray:
    if mono.size == 0:
        return mono
    win = max(1, int(sample_rate * win_s))
    keep = int(sample_rate * max(0.0, keep_s))
    x = mono.astype(np.float64)
    for i in range(0, max(1, x.size - win + 1), win):
        if float(np.max(np.abs(x[i : i + win]))) >= abs_thresh:
            start = max(0, i - keep)
            out = mono[start:]
            return out if out.size >= int(sample_rate * 0.15) else mono
    return mono


def trim_trailing_silence(
    mono: np.ndarray,
    *,
    sample_rate: int,
    floor: int = 400,
    pad_ms: float = 40.0,
) -> np.ndarray:
    if mono.size == 0:
        return mono
    active = np.where(np.abs(mono.astype(np.int32)) >= floor)[0]
    if active.size == 0:
        return mono[: max(1, int(sample_rate * 0.05))]
    last = int(active[-1])
    end = min(mono.size, last + int(sample_rate * (pad_ms / 1000.0)) + 1)
    return mono[:end]


def heal_short_holes(
    mono: np.ndarray,
    *,
    sample_rate: int,
    floor: int = 40,
    max_hole_s: float = 0.18,
) -> tuple[np.ndarray, int]:
    if mono.size < 8:
        return mono, 0
    x = mono.astype(np.float64).copy()
    quiet = np.abs(x) < float(floor)
    max_n = max(2, int(sample_rate * max_hole_s))
    healed = 0
    i = 0
    n = quiet.size
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        run = j - i
        if i > 0 and j < n and 2 <= run <= max_n:
            left = x[i - 1]
            right = x[j]
            for k in range(run):
                u = (k + 1) / (run + 1)
                x[i + k] = left + (right - left) * u
            healed += 1
        i = j
    if healed == 0:
        return mono, 0
    return np.clip(x, -32768, 32767).astype(np.int16), healed


def pick_body(
    x: np.ndarray, sr: int, loop_s: float, fade_s: float
) -> tuple[int, int]:
    need = int((loop_s + fade_s) * sr)
    pad = int(0.12 * sr)
    if x.size < need + 2 * pad:
        start = max(0, (x.size - need) // 2)
        return start, start + min(need, x.size - start)

    win = int(0.05 * sr)
    best_s = pad
    best_score = 1e99
    step = int(0.01 * sr)
    last = x.size - need - pad
    for s in range(pad, max(pad + 1, last), step):
        seg = x[s : s + need]
        hops = [rms(seg[i : i + win]) for i in range(0, need - win, win)]
        score = float(np.std(hops)) + 0.05 * abs(rms(seg[:win]) - rms(seg[-win:]))
        if score < best_score:
            best_score = score
            best_s = s
    return best_s, best_s + need


def seamless_loop(body: np.ndarray, xf: int) -> np.ndarray:
    """body length = L+xf; returns length L with equal-power wrap."""
    if body.size <= 2 * xf + 8:
        raise ValueError("body too short for seamless bake")
    L = body.size - xf
    mid = body[xf:L].astype(np.float64)
    a = body[L : L + xf].astype(np.float64)
    b = body[0:xf].astype(np.float64)
    t = np.linspace(0.0, 1.0, xf, endpoint=True)
    wa = np.cos(0.5 * math.pi * t)
    wb = np.sin(0.5 * math.pi * t)
    cross = a * wa + b * wb
    out = np.concatenate([mid, cross])
    assert out.size == L
    return out


def match_tail_to_ref_head(
    mono: np.ndarray,
    ref: np.ndarray,
    *,
    sample_rate: int,
    edge_ms: float = 180.0,
) -> tuple[np.ndarray, float]:
    """Scale clip so tail RMS matches ref head (transition → steady seam)."""
    n = max(1, int(sample_rate * (edge_ms / 1000.0)))
    if mono.size < n or ref.size < n:
        return mono, 1.0
    a = mono[-n:].astype(np.float64)
    b = ref[:n].astype(np.float64)
    ra = float(np.sqrt(np.mean(np.square(a))))
    rb = float(np.sqrt(np.mean(np.square(b))))
    if ra < 1.0 or rb < 1.0:
        return mono, 1.0
    gain = rb / ra
    peak = float(np.max(np.abs(mono.astype(np.float64))))
    if peak * gain > 32000.0:
        gain = 32000.0 / peak
    out = np.clip(mono.astype(np.float64) * gain, -32768, 32767).astype(np.int16)
    return out, float(gain)


def fix_loop(
    mono: np.ndarray,
    sample_rate: int,
    *,
    fade_s: float = 0.060,
    target_loop_s: float | None = None,
    match_ref: np.ndarray | None = None,
    do_seamless: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Full Fix pipeline. Returns (pcm16, report)."""
    report: dict[str, Any] = {"steps": []}
    x = mono.astype(np.int16, copy=True)
    before = x.size

    x = trim_leading_to_energy(x, sample_rate=sample_rate)
    report["steps"].append({"trim_lead": True, "n": int(x.size)})
    x = trim_trailing_silence(x, sample_rate=sample_rate)
    report["steps"].append({"trim_trail": True, "n": int(x.size)})

    x, holes = heal_short_holes(x, sample_rate=sample_rate)
    report["steps"].append({"heal_holes": holes})

    if match_ref is not None and match_ref.size > 0:
        x, gain = match_tail_to_ref_head(x, match_ref, sample_rate=sample_rate)
        report["steps"].append({"level_match_gain": gain})

    if do_seamless and x.size > int(sample_rate * 0.5):
        fade_s = max(0.02, min(fade_s, 0.12))
        dur = x.size / float(sample_rate)
        loop_s = target_loop_s
        if loop_s is None:
            loop_s = max(0.4, min(dur - fade_s - 0.05, max(0.8, dur * 0.85)))
        loop_s = min(loop_s, dur - fade_s - 0.02)
        if loop_s > 0.35:
            start, end = pick_body(x.astype(np.float64), sample_rate, loop_s, fade_s)
            body = x[start:end].astype(np.float64)
            xf = int(fade_s * sample_rate)
            if body.size > 2 * xf + 8:
                rh, rt = rms(body[:xf]), rms(body[-xf:])
                if rh > 1e-6 and rt > 1e-6:
                    gain = float(np.clip(rh / rt, 0.88, 1.14))
                    span = min(2 * xf, body.size // 4)
                    body[-span:] *= np.linspace(1.0, gain, span)
                    report["steps"].append({"tail_tilt": gain})
                out = seamless_loop(body, xf)
                peak = float(np.max(np.abs(out)))
                if peak > 32000.0:
                    out *= 32000.0 / peak
                    report["steps"].append({"peak_scale": 32000.0 / peak})
                x = np.clip(out, -32768, 32767).astype(np.int16)
                report["steps"].append(
                    {
                        "seamless": True,
                        "body": [start, end],
                        "loop_s": loop_s,
                        "fade_s": fade_s,
                    }
                )

    report["samples_in"] = before
    report["samples_out"] = int(x.size)
    report["duration_out"] = x.size / float(sample_rate)
    return x, report
