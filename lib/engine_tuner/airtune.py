"""Air-brake helper for the Parameters Auto Tune dock.

Writes the enginespec keys the sim actually reads. BP initial is a target
only — Trainz has no minimum-reduction key, so Apply never stores it.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config_io import EngineConfig
from .physics import SimControls, SimParams, simulate

_TO_BAR = 1000.0  # same scale as ui/engine/pressure.py


def _to_bar(native: float) -> float:
    return native * _TO_BAR


def _from_bar(bar: float) -> float:
    return bar / _TO_BAR

# KIHA brakepipe sits ~0.053 bar above brakeinitial when the file has no pair.
_DEFAULT_BP_GAP_BAR = 0.053


@dataclass
class AirTune:
    bp_rel: float = 5.0
    bp_ini: float = 4.8
    bp_full: float = 3.5
    bc_full: float = 3.5
    mr: float = 9.0
    mr_start: float = 0.9
    bc_start: float = 0.0
    vol_mr: float = 40.0
    vol_aux: float = 4.0
    vol_bc: float = 3.0
    vol_pipe: float = 1.0
    vol_ind: float = 3.0
    brake_ratio: float = 20000.0
    max_decel: float = 4500.0  # enginespec mm/s², same number as config.txt
    flow_comp: float = 3.0
    flow_vent: float = 200.0
    flow_res: float = 5.0
    flow_aux: float = 15.0
    flow_bc: float = 10.0
    advanced: bool = False
    speed_kmh: float = 95.0
    mass_t: float = 72.0
    grade: float = 0.0
    emergency: bool = False
    pipe_key: str = "trainbrakepipe"
    bp_gap: float = _DEFAULT_BP_GAP_BAR  # native Trainz units
    press_unit: str = "kPa"
    sim_line: str = ""


_PRESS_UNITS = ("kPa", "bar", "psi")
# display = bar * factor. 1 bar = 100 kPa = 14.5038 psi
_PRESS_FACTOR = {"kPa": 100.0, "bar": 1.0, "psi": 14.503773773}
_PRESSURE_KEYS = {
    "bpRel": "bp_rel",
    "bpIni": "bp_ini",
    "bpFull": "bp_full",
    "bcFull": "bc_full",
    "mr": "mr",
    "mrStart": "mr_start",
    "bcStart": "bc_start",
}


def _bar(block: dict, key: str, default: float) -> float:
    if key not in block:
        return default
    return _to_bar(float(block[key]))


def _num(block: dict, key: str, default: float) -> float:
    if key not in block:
        return default
    return float(block[key])


def load_air(cfg: EngineConfig) -> AirTune:
    press = cfg.pressure
    vol = cfg.volume
    flow = cfg.flowsize
    motor = cfg.motor
    air = AirTune()
    air.bp_rel = _bar(press, "brakeinitial", _bar(press, "brakepipe", air.bp_rel))
    air.bp_full = _bar(press, "brakefull", air.bp_full)
    air.bc_full = _bar(press, "indbrakefull", air.bc_full)
    air.mr = _bar(press, "mainreservoir", _bar(press, "compressor", air.mr))
    air.mr_start = _bar(press, "mainreservoir_start", air.mr * 0.1)
    air.bc_start = _bar(press, "autobrakecylinder_start", 0.0)
    air.bp_ini = max(air.bp_full, air.bp_rel - 0.2)
    if "brakepipe" in press and "brakeinitial" in press:
        air.bp_gap = float(press["brakepipe"]) - float(press["brakeinitial"])
        if air.bp_gap < 0:
            air.bp_gap = _from_bar(_DEFAULT_BP_GAP_BAR)
    else:
        air.bp_gap = _from_bar(_DEFAULT_BP_GAP_BAR)

    no3 = _num(flow, "no3pipe", 0.0) > 0 or _num(vol, "no3pipe", 0.0) > 0
    train = _num(flow, "trainbrakepipe", 0.0) > 0 or _num(vol, "trainbrakepipe", 0.0) > 0
    air.pipe_key = "no3pipe" if no3 and not train else "trainbrakepipe"
    air.vol_mr = _num(vol, "mainreservoir", air.vol_mr)
    air.vol_aux = _num(vol, "auxreservoir", air.vol_aux)
    air.vol_bc = _num(vol, "autobrakecylinder", air.vol_bc)
    air.vol_pipe = _num(vol, air.pipe_key, air.vol_pipe)
    air.vol_ind = _num(vol, "independantbrakecylinder", air.vol_ind)
    air.brake_ratio = _num(motor, "brakeratio", air.brake_ratio)
    air.max_decel = _num(motor, "max-decel", air.max_decel)
    air.flow_comp = _num(flow, "compressor", air.flow_comp)
    air.flow_vent = _num(flow, "trainbrakepipevent", air.flow_vent)
    air.flow_res = _num(flow, "trainbrakepipe_reservoir", air.flow_res)
    air.flow_aux = _num(flow, "auxreservoir_trainbrakepipe", air.flow_aux)
    air.flow_bc = _num(flow, "auxreservoir_autobrakecylinder", air.flow_bc)
    return air


def apply_jnr_preset(air: AirTune) -> None:
    """5.0 / 4.8 / 3.5 / 3.5 / 9.0 bar. Volumes and the decel cap stay."""
    old_mr = air.mr if air.mr > 0 else 9.0
    air.bp_rel = 5.0
    air.bp_ini = 4.8
    air.bp_full = 3.5
    air.bc_full = 3.5
    air.mr = 9.0
    air.mr_start = air.mr_start * (9.0 / old_mr) if air.mr_start > 0 else 0.9
    air.sim_line = ""


def apply_to_cfg(cfg: EngineConfig, air: AirTune) -> None:
    rel = _from_bar(air.bp_rel)
    cfg.pressure["brakeinitial"] = rel
    cfg.pressure["brakepipe"] = rel + air.bp_gap
    cfg.pressure["brakefull"] = _from_bar(air.bp_full)
    cfg.pressure["indbrakefull"] = _from_bar(air.bc_full)
    mr = _from_bar(air.mr)
    cfg.pressure["mainreservoir"] = mr
    cfg.pressure["compressor"] = mr
    cfg.pressure["mainreservoir_start"] = _from_bar(air.mr_start)
    cfg.pressure["autobrakecylinder_start"] = _from_bar(air.bc_start)
    cfg.volume["mainreservoir"] = air.vol_mr
    cfg.volume["auxreservoir"] = air.vol_aux
    cfg.volume["autobrakecylinder"] = air.vol_bc
    cfg.volume[air.pipe_key] = air.vol_pipe
    cfg.volume["independantbrakecylinder"] = air.vol_ind
    cfg.motor["brakeratio"] = air.brake_ratio
    cfg.motor["max-decel"] = air.max_decel
    if air.advanced:
        cfg.flowsize["compressor"] = air.flow_comp
        cfg.flowsize["trainbrakepipevent"] = air.flow_vent
        cfg.flowsize["trainbrakepipe_reservoir"] = air.flow_res
        cfg.flowsize["auxreservoir_trainbrakepipe"] = air.flow_aux
        cfg.flowsize["auxreservoir_autobrakecylinder"] = air.flow_bc


def _reduction_note(air: AirTune) -> str:
    if air.bp_ini <= air.bp_full:
        return "BP ini is at or below BP full — minimum reduction has no room."
    if air.bp_ini >= air.bp_rel:
        return "BP ini is not below BP release."
    gap = air.bp_rel - air.bp_ini
    shown = _fmt_shown(gap, air.press_unit)
    return f"Minimum reduction {shown} {air.press_unit}. Not written — Trainz has no key for it."


def _force_note(air: AirTune) -> str:
    mass = max(air.mass_t, 0.1) * 1000.0
    brake_kn = _from_bar(air.bc_full) * (air.brake_ratio / 800.0)
    air_decel = brake_kn * 1000.0 / mass
    cap_mm = air.max_decel
    cap = cap_mm / 1000.0
    if air_decel > cap + 0.05:
        return (
            f"BC full ≈ {air_decel:.2f} m/s² but max-decel "
            f"{cap_mm:.0f} mm/s² ({cap:.2f} m/s²) is the cap."
        )
    return (
        f"BC full ≈ {air_decel:.2f} m/s², under max-decel "
        f"{cap_mm:.0f} mm/s² ({cap:.2f} m/s²)."
    )


def _pipe_note(air: AirTune) -> str:
    if air.pipe_key != "no3pipe":
        return ""
    return "This file feeds no3pipe. The sim follows the train pipe; flow edits hit that path."


def describe(air: AirTune) -> str:
    lines = [_reduction_note(air), _force_note(air), _pipe_note(air)]
    if air.sim_line:
        lines.append(air.sim_line)
    return "\n".join(line for line in lines if line)


def preview_brake(cfg: EngineConfig, air: AirTune) -> str:
    """Notch 0, full service (or emergency), from the test speed. Does not write cfg."""
    trial = cfg.clone()
    apply_to_cfg(trial, air)
    speed = max(0.0, air.speed_kmh) / 3.6
    result = simulate(
        trial,
        SimParams(
            consist_mass_t=max(air.mass_t, 0.1),
            motor_count=1,
            grade_percent=air.grade,
            duration_s=120.0,
            dt=0.05,
            initial_speed_mps=speed,
        ),
        SimControls(throttle_notch=0, brake_handle=1.0, emergency=air.emergency),
    )
    stop_m = None
    stop_t = None
    for sample in result.samples:
        if sample.t > 0.2 and sample.speed_kmh < 0.3:
            stop_m = sample.distance_m
            stop_t = sample.t
            break
    apply_s = "—" if result.brake_apply_s is None else f"{result.brake_apply_s:.1f}s"
    full_s = "—" if result.brake_full_s is None else f"{result.brake_full_s:.1f}s"
    if stop_m is None:
        end = result.samples[-1] if result.samples else None
        dist = 0.0 if end is None else end.distance_m
        air.sim_line = f"BC apply {apply_s}, full {full_s}. Still moving after 120s ({dist:.0f} m)."
    else:
        air.sim_line = (
            f"BC apply {apply_s}, full {full_s}. Stop {stop_m:.0f} m in {stop_t:.1f}s."
        )
    return air.sim_line


def _fmt_shown(bar: float, unit: str) -> str:
    shown = bar * _PRESS_FACTOR.get(unit, 100.0)
    decimals = 2 if unit == "bar" else 1
    text = f"{shown:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _bar_from_shown(shown: float, unit: str) -> float:
    return shown / _PRESS_FACTOR.get(unit, 100.0)


def cycle_press_unit(air: AirTune) -> str:
    try:
        index = _PRESS_UNITS.index(air.press_unit)
    except ValueError:
        index = 0
    air.press_unit = _PRESS_UNITS[(index + 1) % len(_PRESS_UNITS)]
    air.sim_line = ""
    return air.press_unit


def fields_dict(air: AirTune) -> dict[str, str]:
    def num(value: float, decimals: int) -> str:
        text = f"{value:.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    unit = air.press_unit if air.press_unit in _PRESS_FACTOR else "kPa"
    return {
        "pressUnit": unit,
        "bpRel": _fmt_shown(air.bp_rel, unit),
        "bpIni": _fmt_shown(air.bp_ini, unit),
        "bpFull": _fmt_shown(air.bp_full, unit),
        "bcFull": _fmt_shown(air.bc_full, unit),
        "mr": _fmt_shown(air.mr, unit),
        "mrStart": _fmt_shown(air.mr_start, unit),
        "bcStart": _fmt_shown(air.bc_start, unit),
        "volMr": num(air.vol_mr, 1),
        "volAux": num(air.vol_aux, 1),
        "volBc": num(air.vol_bc, 1),
        "volPipe": num(air.vol_pipe, 1),
        "volInd": num(air.vol_ind, 1),
        "brakeRatio": num(air.brake_ratio, 0),
        "maxDecel": num(air.max_decel, 1),
        "flowComp": num(air.flow_comp, 2),
        "flowVent": num(air.flow_vent, 1),
        "flowRes": num(air.flow_res, 1),
        "flowAux": num(air.flow_aux, 1),
        "flowBc": num(air.flow_bc, 1),
        "advanced": "1" if air.advanced else "0",
        "speedKmh": num(air.speed_kmh, 0),
        "massT": num(air.mass_t, 1),
        "grade": num(air.grade, 1),
        "emergency": "1" if air.emergency else "0",
        "pipeNote": _pipe_note(air),
    }


_FLOATS = {
    "bpRel": "bp_rel",
    "bpIni": "bp_ini",
    "bpFull": "bp_full",
    "bcFull": "bc_full",
    "mr": "mr",
    "mrStart": "mr_start",
    "bcStart": "bc_start",
    "volMr": "vol_mr",
    "volAux": "vol_aux",
    "volBc": "vol_bc",
    "volPipe": "vol_pipe",
    "volInd": "vol_ind",
    "brakeRatio": "brake_ratio",
    "maxDecel": "max_decel",
    "flowComp": "flow_comp",
    "flowVent": "flow_vent",
    "flowRes": "flow_res",
    "flowAux": "flow_aux",
    "flowBc": "flow_bc",
    "speedKmh": "speed_kmh",
    "massT": "mass_t",
    "grade": "grade",
}


def set_field(air: AirTune, key: str, raw: str) -> bool:
    air.sim_line = ""
    if key in ("advanced", "emergency"):
        on = str(raw).lower() in ("1", "true", "yes", "on")
        if key == "advanced":
            air.advanced = on
        else:
            air.emergency = on
        return True
    attr = _FLOATS.get(key)
    if attr is None:
        return False
    try:
        value = float(raw)
    except ValueError:
        return False
    if key in _PRESSURE_KEYS:
        value = _bar_from_shown(value, air.press_unit)
    setattr(air, attr, value)
    return True


def self_check() -> None:
    from .check import _sample_path
    from .config_io import EngineConfig, load_config

    cfg = load_config(_sample_path())
    air = load_air(cfg)
    assert air.max_decel == 4000.0
    assert abs(air.bp_rel - 6.077) < 1e-6
    assert air.pipe_key == "trainbrakepipe"
    apply_jnr_preset(air)
    assert air.press_unit == "kPa"
    assert fields_dict(air)["bpRel"] == "500"
    assert fields_dict(air)["mr"] == "900"
    apply_to_cfg(cfg, air)
    assert abs(_to_bar(cfg.pressure["brakefull"]) - 3.5) < 1e-9
    assert abs(_to_bar(cfg.pressure["brakeinitial"]) - 5.0) < 1e-9
    assert cfg.pressure["brakepipe"] > cfg.pressure["brakeinitial"]
    assert "bpini" not in cfg.pressure
    assert abs(cfg.motor["brakeratio"] - 20000.0) < 1e-6
    assert abs(cfg.motor["max-decel"] - 4000.0) < 1e-6
    note = describe(air)
    assert "max-decel" in note
    assert "Not written" in note
    line = preview_brake(cfg, air)
    assert "m" in line
    # BP ini stays off the file after a second apply
    air.bp_ini = 4.8
    apply_to_cfg(cfg, air)
    assert "bpini" not in cfg.pressure
    direct = EngineConfig()
    direct.flowsize["no3pipe"] = 10
    direct.volume["no3pipe"] = 1
    direct.flowsize["trainbrakepipe"] = 0
    no3 = load_air(direct)
    assert no3.pipe_key == "no3pipe"
    assert "no3pipe" in describe(no3)
    assert fields_dict(no3)["brakeRatio"] == "20000"
    set_field(air, "bpRel", "500")
    assert abs(air.bp_rel - 5.0) < 1e-9
    assert cycle_press_unit(air) == "bar"
    assert fields_dict(air)["bpRel"] == "5"
    assert cycle_press_unit(air) == "psi"
    assert fields_dict(air)["bpRel"] == "72.5"
    assert cycle_press_unit(air) == "kPa"
