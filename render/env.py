"""Procedural viewer environments — sky + ground presets (no heavy assets)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvPreset:
    key: str
    label: str
    sky_top: tuple[float, float, float]
    sky_horizon: tuple[float, float, float]
    ground: tuple[float, float, float]
    ground_line: tuple[float, float, float]
    clear: tuple[float, float, float]
    ambient: float
    # soft secondary fill color toward horizon (shader tint)
    haze: tuple[float, float, float]


# ponytail: procedural color fields only — swap for HDRI cubemaps if shipping real env maps
ENVIRONMENTS: dict[str, EnvPreset] = {
    "studio": EnvPreset(
        key="studio",
        label="Studio",
        sky_top=(0.12, 0.13, 0.15),
        sky_horizon=(0.22, 0.24, 0.27),
        ground=(0.16, 0.17, 0.19),
        ground_line=(0.28, 0.30, 0.33),
        clear=(0.10, 0.11, 0.13),
        ambient=0.24,
        haze=(0.18, 0.19, 0.21),
    ),
    "station": EnvPreset(
        key="station",
        label="Station yard",
        sky_top=(0.35, 0.48, 0.62),
        sky_horizon=(0.72, 0.78, 0.82),
        ground=(0.32, 0.31, 0.30),
        ground_line=(0.42, 0.40, 0.38),
        clear=(0.55, 0.62, 0.70),
        ambient=0.32,
        haze=(0.62, 0.66, 0.70),
    ),
    "harbor": EnvPreset(
        key="harbor",
        label="Harbor",
        sky_top=(0.18, 0.38, 0.58),
        sky_horizon=(0.55, 0.72, 0.82),
        ground=(0.12, 0.28, 0.38),
        ground_line=(0.20, 0.42, 0.52),
        clear=(0.40, 0.58, 0.70),
        ambient=0.30,
        haze=(0.45, 0.62, 0.72),
    ),
    "lake": EnvPreset(
        key="lake",
        label="Lake",
        sky_top=(0.28, 0.52, 0.72),
        sky_horizon=(0.78, 0.88, 0.92),
        ground=(0.10, 0.32, 0.36),
        ground_line=(0.18, 0.48, 0.52),
        clear=(0.62, 0.78, 0.86),
        ambient=0.34,
        haze=(0.70, 0.82, 0.88),
    ),
    "mountains": EnvPreset(
        key="mountains",
        label="Mountains",
        sky_top=(0.22, 0.36, 0.58),
        sky_horizon=(0.85, 0.78, 0.70),
        ground=(0.22, 0.28, 0.20),
        ground_line=(0.34, 0.40, 0.30),
        clear=(0.55, 0.58, 0.62),
        ambient=0.28,
        haze=(0.70, 0.68, 0.62),
    ),
    "none": EnvPreset(
        key="none",
        label="None (clear)",
        sky_top=(0.07, 0.08, 0.10),
        sky_horizon=(0.07, 0.08, 0.10),
        ground=(0.07, 0.08, 0.10),
        ground_line=(0.20, 0.22, 0.24),
        clear=(0.07, 0.08, 0.10),
        ambient=0.22,
        haze=(0.07, 0.08, 0.10),
    ),
}


def env_keys() -> list[str]:
    return list(ENVIRONMENTS.keys())


def get_env(key: str) -> EnvPreset:
    return ENVIRONMENTS.get(key) or ENVIRONMENTS["studio"]
