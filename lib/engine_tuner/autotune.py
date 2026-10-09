"""TEE-style throttle autogen + Davis train-resistance (Trainz-tuned constants).

Formulas from Trainz Engine Editor (Mats Strid / STW) v1.06b readme + tee.cfg.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .throttle_round import normalize_points

G = 9.80665
HP_PER_KW = 1.0 / 0.746  # metric horsepower, 1 hp = 0.746 kW


def format_power(kw: float, unit: str) -> str:
    shown = kw * HP_PER_KW if unit == "HP" else kw
    text = f"{shown:.1f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_power_kw(shown: float, unit: str) -> float:
    if unit == "HP":
        return shown / HP_PER_KW
    return shown
MPS_PER_MPH = 0.44704
LBF_TO_KN = 4.448221615 / 1000.0  # 1 lbf → kN
M2_TO_FT2 = 10.76391041671
US_TON_PER_TONNE = 1.0 / 0.90718474  # metric tonne → short ton

# tee.cfg [Constants] — Trainz-calibrated (not pure physics textbook)
GRADE_RESISTANCE_LBF_PER_TON_PCT = 26.5
START_RESISTANCE_LBF_PER_TON = 20.0
START_RESISTANCE_SPEED_MPH = 5.0

# TEE Shape dropdown → Trainz air-drag-coefficient style values
SHAPE_PRESETS: dict[str, float] = {
    "Box / Irregular": 0.0025,
    "Streamlined": 0.0017,
    "Freight": 0.0005,
}


@dataclass
class AutogenParams:
    max_power_kw: float
    max_speed_kmh: float
    max_te_kn: float
    power_coeff: float = 1.0
    speed_coeff: float = 1.0
    notch_coeff: float = 1.0
    node_count: int = 20
    max_notch: int = 8


@dataclass
class VehicleResist:
    mass_t: float
    area_m2: float
    drag_cd: float
    axles: int
    fric_coeff: float
    count: int = 1


@dataclass
class ResistParams:
    engine: VehicleResist
    cars: VehicleResist
    grade_percent: float = 0.0
    start_lbf_per_ton: float = START_RESISTANCE_LBF_PER_TON
    start_speed_mph: float = START_RESISTANCE_SPEED_MPH
    grade_lbf_per_ton_pct: float = GRADE_RESISTANCE_LBF_PER_TON_PCT


@dataclass
class BalanceHit:
    notch: int
    speed_kmh: float
    force_kn: float


@dataclass
class AccelResult:
    time_s: float | None
    note: str = ""


def estimate_max_te_kn(*, friction_pct: float, adhesion_weight_t: float) -> float:
    """TEE: TE ≈ friction% × adhesion weight (weight on drivers)."""
    if friction_pct <= 0 or adhesion_weight_t <= 0:
        return 0.0
    return (friction_pct / 100.0) * adhesion_weight_t * G


def _te_kn_at_speed(
    v_mps: float,
    *,
    max_power_kw: float,
    max_te_kn: float,
    power_coeff: float,
    speed_coeff: float,
) -> float:
    """TEE: TE_lbs = HP · 308 / V_mph, clipped at max TE. Coeffs scale power / speed."""
    if max_power_kw <= 0 or max_te_kn <= 0:
        return 0.0
    if v_mps <= 1e-9:
        return max_te_kn
    hp = max_power_kw * HP_PER_KW * max(power_coeff, 1e-9)
    mph = (v_mps / MPS_PER_MPH) / max(speed_coeff, 1e-9)
    te_lbs = hp * 308.0 / max(mph, 1e-9)
    return min(te_lbs * LBF_TO_KN, max_te_kn)


def generate_throttle_power(p: AutogenParams) -> dict[int, list[tuple[float, float]]]:
    """Build notches 0..max_notch. Last node forced to 0 kN at max speed."""
    n_nodes = max(2, min(39, int(p.node_count)))
    max_n = max(1, int(p.max_notch))
    v_max = max(p.max_speed_kmh, 1.0) / 3.6
    # evenly spaced speeds including endpoints
    speeds = [v_max * i / (n_nodes - 1) for i in range(n_nodes)]

    out: dict[int, list[tuple[float, float]]] = {}
    for notch in range(0, max_n + 1):
        # TEE: lower notches evaluated as if at higher speed → curve shifts left
        offset = (max_n - notch) * max(p.notch_coeff, 0.0)  # m/s
        pts: list[tuple[float, float]] = []
        for i, v in enumerate(speeds):
            if i == n_nodes - 1:
                pts.append((v, 0.0))
                continue
            te = _te_kn_at_speed(
                v + offset,
                max_power_kw=p.max_power_kw,
                max_te_kn=p.max_te_kn,
                power_coeff=p.power_coeff,
                speed_coeff=p.speed_coeff,
            )
            pts.append((v, te))
        out[notch] = normalize_points(pts)
    return out


def _vehicle_resist_lbf(v_mph: float, veh: VehicleResist, rp: ResistParams) -> float:
    """Davis lb/ton (TEE) × short-tons + grade. Starting resistance below start_speed."""
    if veh.count <= 0 or veh.mass_t <= 0:
        return 0.0
    us_tons = veh.mass_t * US_TON_PER_TONNE
    axles = max(1, int(veh.axles))
    w_axle = us_tons / axles
    area_ft2 = max(veh.area_m2, 0.0) * M2_TO_FT2
    d = max(veh.drag_cd, 0.0)
    f = max(veh.fric_coeff, 0.0)

    if v_mph < rp.start_speed_mph:
        r_per_ton = rp.start_lbf_per_ton
    else:
        # R = 1.3 + 29/W + F·V + D·A·V²/W · N  (TEE readme)
        r_per_ton = (
            1.3
            + 29.0 / max(w_axle, 0.05)
            + f * v_mph
            + d * area_ft2 * (v_mph**2) / max(w_axle, 0.05) * axles
        )
    r = r_per_ton * us_tons
    r += rp.grade_lbf_per_ton_pct * us_tons * rp.grade_percent
    return r * veh.count


def resistance_kn(v_mps: float, rp: ResistParams) -> float:
    v_mph = max(0.0, v_mps) / MPS_PER_MPH
    total_lbf = _vehicle_resist_lbf(v_mph, rp.engine, rp) + _vehicle_resist_lbf(
        v_mph, rp.cars, rp
    )
    return total_lbf * LBF_TO_KN


def resistance_curve(
    rp: ResistParams, *, max_speed_kmh: float, samples: int = 80
) -> list[tuple[float, float]]:
    """Return [(speed_mps, resist_kn), ...] from 0 → max_speed."""
    n = max(2, samples)
    v_max = max(max_speed_kmh, 1.0) / 3.6
    return [(v_max * i / (n - 1), resistance_kn(v_max * i / (n - 1), rp)) for i in range(n)]


def _interp_y(curve: list[tuple[float, float]], x: float) -> float:
    if not curve:
        return 0.0
    if x <= curve[0][0]:
        return curve[0][1]
    for i in range(1, len(curve)):
        x0, y0 = curve[i - 1]
        x1, y1 = curve[i]
        if x <= x1:
            if x1 == x0:
                return y1
            u = (x - x0) / (x1 - x0)
            return y0 + (y1 - y0) * u
    return curve[-1][1]


def balancing_speeds(
    throttle: dict[int, list[tuple[float, float]]],
    rp: ResistParams,
    *,
    max_speed_kmh: float,
) -> list[BalanceHit]:
    """First TE↔resistance crossing per notch (balancing / max speed on that notch)."""
    hits: list[BalanceHit] = []
    v_max = max(max_speed_kmh, 1.0) / 3.6
    steps = 400
    for notch in sorted(throttle):
        pts = throttle[notch]
        if len(pts) < 2:
            continue
        prev_diff: float | None = None
        found: BalanceHit | None = None
        for i in range(steps + 1):
            v = v_max * i / steps
            te = _interp_y(pts, v)
            r = resistance_kn(v, rp)
            diff = te - r
            if prev_diff is not None and prev_diff > 0 and diff <= 0:
                # linear interpolate crossing
                v0 = v_max * (i - 1) / steps
                if prev_diff - diff == 0:
                    vc = v
                else:
                    u = prev_diff / (prev_diff - diff)
                    vc = v0 + (v - v0) * u
                found = BalanceHit(notch, vc * 3.6, resistance_kn(vc, rp))
                break
            prev_diff = diff
        if found is not None:
            hits.append(found)
    return hits


def acceleration_time(
    curve: list[tuple[float, float]],
    rp: ResistParams,
    *,
    v0_kmh: float,
    v1_kmh: float,
    mass_t: float | None = None,
) -> AccelResult:
    """Newton slices along TE−R (same idea as TEE acceleration box)."""
    if v1_kmh <= v0_kmh:
        return AccelResult(None, "end speed must be > start")
    total_t = rp.engine.mass_t * rp.engine.count + rp.cars.mass_t * rp.cars.count
    if mass_t is not None and mass_t > 0:
        total_t = mass_t
    if total_t <= 0:
        return AccelResult(None, "mass is zero")
    mass_kg = total_t * 1000.0
    v0 = v0_kmh / 3.6
    v1 = v1_kmh / 3.6
    steps = 200
    t = 0.0
    for i in range(steps):
        va = v0 + (v1 - v0) * i / steps
        vb = v0 + (v1 - v0) * (i + 1) / steps
        vm = 0.5 * (va + vb)
        net_kn = _interp_y(curve, vm) - resistance_kn(vm, rp)
        if net_kn <= 1e-6:
            return AccelResult(None, f"TE ≤ resistance near {vm * 3.6:.1f} km/h")
        a = (net_kn * 1000.0) / mass_kg
        t += (vb - va) / a
    return AccelResult(t)


def self_check() -> None:
    # ~2000 kW, 120 km/h, 250 kN → notch 8 should stick to adhesion then fall with 1/v
    curves = generate_throttle_power(
        AutogenParams(
            max_power_kw=2000.0,
            max_speed_kmh=120.0,
            max_te_kn=250.0,
            power_coeff=1.5,
            speed_coeff=1.0,
            notch_coeff=1.0,
            node_count=20,
            max_notch=8,
        )
    )
    assert set(curves.keys()) == set(range(0, 9))
    n8 = curves[8]
    assert abs(n8[0][0]) < 1e-9
    assert abs(n8[0][1] - 250.0) < 0.5  # adhesion-capped at standstill
    assert format_power(2000.0, "kW") == "2000"
    assert format_power(2000.0, "HP") == "2681"
    assert abs(parse_power_kw(2681.0, "HP") - 2000.0) < 1.0
    assert n8[-1][1] == 0.0
    assert n8[-1][0] * 3.6 == 120.0 or abs(n8[-1][0] * 3.6 - 120.0) < 0.05
    # lower notch has less (or equal) TE at same mid speed
    mid = n8[len(n8) // 2][0]
    assert _interp_y(curves[4], mid) <= _interp_y(curves[8], mid) + 1e-6

    te_est = estimate_max_te_kn(friction_pct=30.0, adhesion_weight_t=100.0)
    assert abs(te_est - 294.1995) < 0.01

    rp = ResistParams(
        engine=VehicleResist(72.0, 10.0, 0.0017, 4, 0.03, 1),
        cars=VehicleResist(40.0, 8.0, 0.0005, 4, 0.045, 10),
        grade_percent=0.0,
    )
    r0 = resistance_kn(0.0, rp)
    r_fast = resistance_kn(30.0, rp)
    assert r0 > 0 and r_fast > r0
    hits = balancing_speeds(curves, rp, max_speed_kmh=120.0)
    assert hits, "expected at least one balancing speed"
    assert hits[-1].notch == 8

    acc = acceleration_time(curves[8], rp, v0_kmh=0.0, v1_kmh=60.0)
    assert acc.time_s is not None and acc.time_s > 0


if __name__ == "__main__":
    self_check()
    print("autotune: ok")
