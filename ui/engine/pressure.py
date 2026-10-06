"""Trainz pressure block ↔ bar / kPa display helpers.

Trainz enginespec stores gauge-ish pressures as tiny floats where
×1000 ≈ bar (KIHA MR 0.011227 → ~11.2 bar, BP 0.00613 → ~6.1 bar).
"""
from __future__ import annotations

# native → bar
TRAINZ_TO_BAR = 1000.0
BAR_TO_KPA = 100.0  # 1 bar = 100 kPa


def to_bar(native: float) -> float:
    return native * TRAINZ_TO_BAR


def to_kpa(native: float) -> float:
    return to_bar(native) * BAR_TO_KPA


def from_bar(bar: float) -> float:
    return bar / TRAINZ_TO_BAR


def from_kpa(kpa: float) -> float:
    return from_bar(kpa / BAR_TO_KPA)


def fmt_native(v: float) -> str:
    if abs(v) < 1e-15:
        return "0"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    text = f"{v:.8f}".rstrip("0").rstrip(".")
    return text or "0"


def fmt_bar(v: float) -> str:
    b = to_bar(v)
    if abs(b) < 1e-12:
        return "0"
    return f"{b:.3f}".rstrip("0").rstrip(".")


def fmt_kpa(v: float) -> str:
    k = to_kpa(v)
    if abs(k) < 1e-9:
        return "0"
    if abs(k - round(k)) < 0.05:
        return str(int(round(k)))
    return f"{k:.1f}".rstrip("0").rstrip(".")
