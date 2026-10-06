"""Round throttle-power curve points to 0.1 precision."""
from __future__ import annotations

MS_TO_KMH = 3.6


def round1(v: float) -> float:
    return round(v * 10) / 10


def round_point(speed_mps: float, te_kn: float) -> tuple[float, float]:
    return round1(speed_mps * MS_TO_KMH) / MS_TO_KMH, round1(te_kn)


def normalize_points(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return sorted((round_point(sp, te) for sp, te in pts), key=lambda p: p[0])


def _fmt1(v: float) -> str:
    r = round1(v)
    if abs(r - round(r)) < 1e-9:
        return str(int(round(r)))
    return f"{r:.1f}"


def fmt_kmh(speed_mps: float) -> str:
    return _fmt1(speed_mps * MS_TO_KMH)


def fmt_kn(te_kn: float) -> str:
    return _fmt1(te_kn)


def fmt_config(value: float) -> str:
    return _fmt1(value)


if __name__ == "__main__":
    mps, te = round_point(10.0 / 3.6, 17.25)
    assert abs(mps * MS_TO_KMH - 10.0) < 1e-9
    assert te == 17.2
    assert mps != round1(10.0 / 3.6)  # km/h path, not raw m/s round1
    mps2, _ = round_point(2.78, 0.0)
    assert abs(mps2 * MS_TO_KMH - 10.0) < 1e-9
    print("throttle_round: ok")
