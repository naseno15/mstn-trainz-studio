"""Approximate Trainz engine + air-brake simulation for tuning."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config_io import EngineConfig

G = 9.80665


@dataclass
class SimParams:
    consist_mass_t: float = 72.0
    motor_count: int = 2
    grade_percent: float = 0.0
    dt: float = 0.05
    duration_s: float = 200.0


@dataclass
class SimControls:
    throttle_notch: int = 8
    brake_handle: float = 0.0  # 0 release, 1 full service
    emergency: bool = False


@dataclass
class SimSample:
    t: float
    speed_mps: float
    speed_kmh: float
    distance_m: float
    te_kn: float
    resist_kn: float
    brake_kn: float
    accel_mps2: float
    mr_pressure: float
    bp_pressure: float
    bc_pressure: float
    air_used_rel: float


@dataclass
class SimResult:
    samples: list[SimSample] = field(default_factory=list)
    peak_speed_kmh: float = 0.0
    time_to_60_kmh: float | None = None
    time_to_90_kmh: float | None = None
    brake_apply_s: float | None = None
    brake_full_s: float | None = None


def interp_te(curve: list[tuple[float, float]], speed_mps: float) -> float:
    if not curve:
        return 0.0
    if speed_mps <= curve[0][0]:
        return curve[0][1]
    for i in range(1, len(curve)):
        x0, y0 = curve[i - 1]
        x1, y1 = curve[i]
        if speed_mps <= x1:
            if x1 == x0:
                return y1
            u = (speed_mps - x0) / (x1 - x0)
            return y0 + (y1 - y0) * u
    return curve[-1][1]


def resist_force_kn(cfg: EngineConfig, speed_mps: float, mass_kg: float) -> float:
    m = cfg.motor
    tonnes = mass_kg / 1000.0
    # ponytail: heuristic resist model for tuning comparisons, not exact Trainz physics
    roll = tonnes * m.get("resistance", 1.0) * 0.008
    roll += tonnes * m.get("moving-friction-coefficient", 0.03) * 0.35
    drag = m.get("air-drag-coefficient", 0.00017) * m.get("surface-area", 80.0) * speed_mps * speed_mps * 0.012
    return roll + drag


def grade_force_kn(mass_kg: float, grade_percent: float) -> float:
    return mass_kg * G * (grade_percent / 100.0) / 1000.0


def simulate(cfg: EngineConfig, params: SimParams, controls: SimControls) -> SimResult:
    motor = cfg.motor
    press = cfg.pressure
    flow = cfg.flowsize
    vol = cfg.volume

    mass_kg = params.consist_mass_t * 1000.0
    motors = max(1, params.motor_count)
    max_speed = motor.get("maxspeed", 33.33)
    max_accel = motor.get("max-accel", 1600.0) / 1000.0  # mm/s² -> m/s²
    max_decel = motor.get("max-decel", 6600.0) / 1000.0
    brake_ratio = motor.get("brakeratio", 20000.0) / 800.0  # ponytail: heuristic scale for kN

    notch = max(0, min(int(controls.throttle_notch), int(motor.get("throttle-notches", 8))))
    curve = cfg.throttle_power.get(notch, cfg.throttle_power.get(0, [(0.0, 0.0)]))

    bp_release = press.get("brakeinitial", press.get("brakepipe", 0.006077))
    bp_full = press.get("brakefull", 0.004601)
    mr_charge = press.get("mainreservoir", press.get("compressor", 0.013))
    mr_start = press.get("mainreservoir_start", mr_charge)
    if mr_start <= 0:
        mr_start = mr_charge

    p_mr = mr_start
    p_bp = bp_release
    p_aux = bp_release
    p_bc = press.get("autobrakecylinder_start", 0.0)

    v = 0.0
    x = 0.0
    t = 0.0
    air_used = 0.0
    result = SimResult()
    brake_started = False
    brake_full_t: float | None = None
    bc_full_threshold = press.get("indbrakefull", 0.01021) * 0.85

    f_bp = flow.get("trainbrakepipe", 900.0)
    f_vent = flow.get("trainbrakepipevent", 200.0)
    f_res = flow.get("trainbrakepipe_reservoir", 5.0)
    f_aux = flow.get("auxreservoir_trainbrakepipe", 15.0)
    f_bc = flow.get("auxreservoir_autobrakecylinder", 10.0)
    f_comp = max(flow.get("compressor", 0.001), 1e-6)

    v_mr = max(vol.get("mainreservoir", 20.0), 0.1)
    v_bp = max(vol.get("trainbrakepipe", 1.0), 0.1)
    v_aux = max(vol.get("auxreservoir", 2.0), 0.1)
    v_bc = max(vol.get("autobrakecylinder", 1.0), 0.1)

    target_bp = bp_release - controls.brake_handle * (bp_release - bp_full)
    if controls.emergency:
        target_bp = bp_full * 0.5

    steps = int(params.duration_s / params.dt) + 1
    for _ in range(steps):
        target_bp = bp_release - controls.brake_handle * (bp_release - bp_full)
        if controls.emergency:
            target_bp = bp_full * 0.5

        # Compressor tops up main reservoir.
        if p_mr < mr_charge:
            dp = f_comp * (mr_charge - p_mr) / v_mr * params.dt
            p_mr = min(mr_charge, p_mr + dp)

        # Brake pipe follows driver target with pipe flow + vent.
        if p_bp > target_bp + 1e-6:
            dp = f_vent * (p_bp - target_bp) / v_bp * params.dt
            p_bp = max(target_bp, p_bp - dp)
            air_used += dp * v_bp
        elif p_bp < target_bp - 1e-6:
            dp = f_res * (target_bp - p_bp) / v_bp * params.dt
            p_bp = min(target_bp, p_bp + dp)

        # Aux reservoir tracks brake pipe with lag.
        if p_aux > p_bp:
            dp = f_aux * (p_aux - p_bp) / v_aux * params.dt
            p_aux = max(p_bp, p_aux - dp)
        else:
            dp = f_aux * (p_bp - p_aux) / v_aux * params.dt
            p_aux = min(p_bp, p_aux + dp)

        # Brake cylinder charges when aux exceeds BC.
        if p_aux > p_bc:
            dp = f_bc * (p_aux - p_bc) / v_bc * params.dt
            p_bc = min(p_aux, p_bc + dp)
            air_used += dp * v_bc * 0.5
        elif p_bc > p_aux:
            dp = f_bc * (p_bc - p_aux) / v_bc * params.dt
            p_bc = max(p_aux, p_bc - dp)

        if controls.brake_handle > 0.01 and not brake_started and p_bc > 1e-4:
            brake_started = True
            result.brake_apply_s = t
        if brake_started and brake_full_t is None and p_bc >= bc_full_threshold:
            brake_full_t = t
            result.brake_full_s = t

        te = interp_te(curve, v) * motors
        resist = resist_force_kn(cfg, v, mass_kg) + grade_force_kn(mass_kg, params.grade_percent)
        brake_kn = p_bc * brake_ratio
        net_kn = te - resist - brake_kn
        net_n = net_kn * 1000.0
        accel = net_n / mass_kg
        if accel > 0:
            accel = min(accel, max_accel)
        else:
            accel = max(accel, -max_decel)

        v = max(0.0, v + accel * params.dt)
        if v > max_speed:
            v = max_speed
            if accel > 0:
                accel = 0.0
        x += v * params.dt

        kmh = v * 3.6
        result.samples.append(
            SimSample(
                t=t,
                speed_mps=v,
                speed_kmh=kmh,
                distance_m=x,
                te_kn=te,
                resist_kn=resist,
                brake_kn=brake_kn,
                accel_mps2=accel,
                mr_pressure=p_mr,
                bp_pressure=p_bp,
                bc_pressure=p_bc,
                air_used_rel=air_used,
            )
        )
        result.peak_speed_kmh = max(result.peak_speed_kmh, kmh)
        if result.time_to_60_kmh is None and kmh >= 60.0:
            result.time_to_60_kmh = t
        if result.time_to_90_kmh is None and kmh >= 90.0:
            result.time_to_90_kmh = t
        t += params.dt

    return result


def self_check() -> None:
    from .check import _sample_path
    from .config_io import load_config

    cfg = load_config(_sample_path())
    r = simulate(cfg, SimParams(consist_mass_t=72, motor_count=2), SimControls(throttle_notch=5))
    assert r.samples, "no samples"
    assert r.peak_speed_kmh > 50.0, r.peak_speed_kmh
    assert r.samples[-1].distance_m > 500.0


if __name__ == "__main__":
    self_check()
    print("physics: ok")
