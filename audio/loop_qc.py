"""Loop / clip QC — holes, dips, uneven seams (Trainz steady style)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .decode import load_mono_pcm16


@dataclass
class Finding:
    key: str
    path: str
    kind: str  # ok | hole | dip | uneven_loop | quiet | short | click
    severity: str  # ok | warn | fail
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.severity == "ok"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))) / 32768.0)


def envelope_windows(mono: np.ndarray, sr: int, win_s: float = 0.25) -> list[float]:
    step = max(1, int(sr * win_s))
    out: list[float] = []
    for i in range(0, mono.size, step):
        chunk = mono[i : i + step]
        if chunk.size:
            out.append(_rms(chunk))
    return out


def zero_runs(
    mono: np.ndarray, sr: int, *, min_s: float = 0.02, floor: float = 8.0
) -> list[tuple[float, float, float]]:
    runs: list[tuple[float, float, float]] = []
    zs = None
    ze = 0
    n = mono.size
    for i, v in enumerate(mono):
        if abs(int(v)) < floor:
            if zs is None:
                zs = i
            ze = i
        else:
            if zs is not None:
                dur = (ze - zs) / float(sr)
                if dur >= min_s and zs > 0 and ze < n - 1:
                    runs.append((zs / sr, ze / sr, dur))
            zs = None
    if zs is not None:
        dur = (ze - zs) / float(sr)
        if dur >= min_s and zs > 0 and ze < n - 1:
            runs.append((zs / sr, ze / sr, dur))
    return runs


def wrap_click_score(mono: np.ndarray, *, edge: int = 32) -> float:
    """Phase-ish discontinuity at loop wrap (0 = smooth)."""
    if mono.size < edge * 2 + 8:
        return 0.0
    a = mono[-edge:].astype(np.float64)
    b = mono[:edge].astype(np.float64)
    # adjacent-sample jump at wrap
    jump = abs(float(b[0]) - float(a[-1])) / 32768.0
    # local mean mismatch
    mean_d = abs(float(np.mean(a)) - float(np.mean(b))) / 32768.0
    return float(jump + 0.5 * mean_d)


def analyze_mono(
    mono: np.ndarray,
    sr: int,
    *,
    key: str,
    path: str = "",
    treat_as: str | None = None,
) -> list[Finding]:
    """treat_as: 'steady' | 'trans' | None (infer from key stem)."""
    findings: list[Finding] = []
    stem = Path(key).stem if key else "clip"
    dur = mono.size / float(sr) if sr else 0.0
    if dur < 0.35:
        findings.append(
            Finding(
                key=key,
                path=path,
                kind="short",
                severity="fail",
                message=f"too short {dur:.2f}s",
                detail={"dur": dur},
            )
        )

    full = _rms(mono)
    if full < 0.008:
        findings.append(
            Finding(
                key=key,
                path=path,
                kind="quiet",
                severity="fail",
                message=f"near-silent RMS={full:.5f}",
                detail={"rms": full},
            )
        )

    holes = zero_runs(mono, sr, min_s=0.02)
    if holes:
        desc = ", ".join(f"{a:.2f}-{b:.2f}s ({d * 1000:.0f}ms)" for a, b, d in holes[:6])
        findings.append(
            Finding(
                key=key,
                path=path,
                kind="hole",
                severity="fail",
                message=f"interior silence / glitch: {desc}",
                detail={"holes": [{"t0": a, "t1": b, "dur": d} for a, b, d in holes]},
            )
        )

    wins = envelope_windows(mono, sr, 0.25)
    is_trans = treat_as == "trans" or (
        treat_as is None and "-" in stem and not stem.endswith("-stop")
    )
    is_steady = treat_as == "steady" or (
        treat_as is None
        and not is_trans
        and "stop" not in stem
        and stem != "start"
    )

    head_rms = tail_rms = mid_rms = 0.0
    seam_db = 0.0
    if len(wins) >= 4:
        head_rms = sum(wins[:2]) / 2.0
        tail_rms = sum(wins[-2:]) / 2.0
        mid_slice = wins[len(wins) // 3 : 2 * len(wins) // 3]
        mid_rms = sum(mid_slice) / max(1, len(mid_slice))
        if head_rms > 1e-9 and tail_rms > 1e-9:
            seam_db = abs(20.0 * math.log10(max(head_rms, 1e-9) / max(tail_rms, 1e-9)))

    click = wrap_click_score(mono)
    if is_steady and click >= 0.12:
        findings.append(
            Finding(
                key=key,
                path=path,
                kind="click",
                severity="fail" if click >= 0.25 else "warn",
                message=f"loop wrap click risk={click:.3f}",
                detail={"click": click},
            )
        )

    if is_steady and len(wins) >= 4 and head_rms > 1e-6 and tail_rms > 1e-6:
        ratio = max(head_rms, tail_rms) / max(min(head_rms, tail_rms), 1e-9)
        if seam_db >= 2.5 or ratio >= 1.35:
            findings.append(
                Finding(
                    key=key,
                    path=path,
                    kind="uneven_loop",
                    severity="fail" if seam_db >= 4.0 else "warn",
                    message=f"loop seam uneven head/tail Δ={seam_db:.1f} dB",
                    detail={
                        "head_rms": head_rms,
                        "tail_rms": tail_rms,
                        "mid_rms": mid_rms,
                        "db": seam_db,
                    },
                )
            )

    if is_trans and len(wins) >= 6:
        mid_slice = wins[2 : max(3, len(wins) - 2)]
        mid = min(mid_slice) if mid_slice else 0.0
        ref = max(head_rms, tail_rms, 1e-9)
        if mid < ref * 0.45 and mid < 0.035:
            findings.append(
                Finding(
                    key=key,
                    path=path,
                    kind="dip",
                    severity="fail",
                    message=f"level dip / mid={mid:.4f} vs ends≈{ref:.4f}",
                    detail={"head": head_rms, "mid": mid, "tail": tail_rms},
                )
            )

    if not findings:
        findings.append(
            Finding(
                key=key,
                path=path,
                kind="ok",
                severity="ok",
                message="ok",
                detail={
                    "dur": dur,
                    "rms": full,
                    "seam_db": seam_db,
                    "click": click,
                    "head_rms": head_rms,
                    "tail_rms": tail_rms,
                },
            )
        )
    return findings


def analyze_path(path: Path, *, treat_as: str | None = None) -> list[Finding]:
    path = Path(path)
    key = f"{path.parent.name}/{path.stem}" if path.parent.name else path.stem
    try:
        mono, sr, _ = load_mono_pcm16(path)
    except Exception as e:
        return [
            Finding(
                key=key,
                path=str(path),
                kind="quiet",
                severity="fail",
                message=str(e),
            )
        ]
    return analyze_mono(mono, sr, key=key, path=str(path), treat_as=treat_as)


def worst_severity(findings: list[Finding]) -> str:
    order = {"ok": 0, "warn": 1, "fail": 2}
    return max((f.severity for f in findings), key=lambda s: order.get(s, 0), default="ok")
