#!/usr/bin/env python3
"""Pre-flight checks for engine_tuner.

Default / --fast: config_io + physics only (safe before GUI launch).
Full (incl. Qt UI): run without --fast, e.g. `python check.py` or `run.ps1 --check`.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Headless matplotlib for non-UI checks.
os.environ.setdefault("MPLBACKEND", "Agg")

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ponytail: tiny fixture so checks don't depend on a live Trainz asset path
_SAMPLE_TEXT = """\
kuid                                    <kuid:0:0>
username                                "engine_tuner check sample"
kind                                    "enginespec"
trainz-build                            4.6

flowsize
{
  trainbrakepipe                        900
}

volume
{
  mainreservoir                         40
}

pressure
{
  brakepipe                             0.00613
  brakeinitial                          0.006077
  brakefull                             0.004601
}

mass
{
  fuel                                  1
}

motor
{
  resistance                            1.7
  maxspeed                              33.333332
  brakeratio                            20000
  max-accel                             1600
  max-decel                             4000
  throttle-notches                      8
  axle-count                            4
  surface-area                          80
  moving-friction-coefficient           0.032
  air-drag-coefficient                  0.00019
}

throttle-power
{
  0
  {
    0                                   1
    2.8                                 0
  }
  1
  {
    0                                   9
  }
  5
  {
    0                                   50
    5                                   40
    10                                  28
    15                                  18
    20                                  10
    30                                  0
  }
}
"""


def _sample_path() -> Path:
    path = Path(tempfile.gettempdir()) / "engine_tuner_check_sample_config.txt"
    path.write_text(_SAMPLE_TEXT, encoding="utf-8")
    return path


def check_config_io() -> None:
    from .config_io import config_to_text, load_config, parse_config_text

    sample = _sample_path()
    cfg = load_config(sample)
    assert cfg.motor.get("max-accel") == 1600.0
    assert len(cfg.throttle_power[5]) >= 5
    assert cfg.flowsize.get("trainbrakepipe") == 900.0
    reparsed = parse_config_text(config_to_text(cfg))
    assert reparsed.get("motor", {}).get("max-accel") == 1600.0


def check_physics() -> None:
    from .physics import self_check

    self_check()


def check_autotune() -> None:
    from .autotune import self_check

    self_check()


def check_airtune() -> None:
    from .airtune import self_check

    self_check()


def check_pressure_units() -> None:
    from trainz_studio.ui.engine.pressure import (
        from_bar,
        from_kpa,
        to_bar,
        to_kpa,
    )

    # KIHA-ish BP 0.00613 → ~6.13 bar → ~613 kPa
    native = 0.00613
    assert abs(to_bar(native) - 6.13) < 1e-9
    assert abs(to_kpa(native) - 613.0) < 1e-6
    assert abs(from_bar(6.13) - native) < 1e-12
    assert abs(from_kpa(613.0) - native) < 1e-12


def check_ui_builds() -> None:
    from PySide6.QtWidgets import QApplication

    from trainz_studio.lib.engine_tuner.config_io import load_config
    from trainz_studio.ui.engine import build_engine_tuner
    from trainz_studio.ui.theme import apply_theme

    sample = _sample_path()
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "dark")
    host = build_engine_tuner(on_home=lambda: None, theme_mode="dark")
    try:
        host.cfg = load_config(sample)
        host._load_into_ui()
        assert host.motor_editor is not None
        assert host.mass_editor is not None
        assert host.throttle_editor is not None
        assert host.sim_panel is not None
        assert host.press_editor is not None
        assert host._stack.count() == 3
        assert host._nav is not None
        assert host.sidebar is not None
        host._nav.set_page("simulation", emit=True)
        assert host._stack.currentIndex() == 1
        host._nav.set_page("parameters", emit=True)
        assert host._stack.currentIndex() == 2
        host.open_autotune()
        assert host._auto_kind == "air"
        assert host._stack.currentIndex() == 2
        host.preset_air_fields()
        host.apply_air_fields()
        assert abs(host.cfg.pressure["brakefull"] * 1000 - 3.5) < 1e-6
        assert "bpini" not in host.cfg.pressure
        host.undo()
        host.close_autotune()
        host._nav.set_page("tuner", emit=True)
        host.open_autotune()
        assert host._auto_kind == "engine"
        assert host._stack.currentIndex() == 0
        host.close_autotune()
        host._nav.set_page("parameters", emit=True)
        assert len(host.cfg.throttle_power) >= 1
        host.throttle_editor._redraw()
        # pressure bar column present
        assert host.press_editor.tree.columnCount() == 4
        bp = host.cfg.pressure.get("brakepipe", 0.0)
        if bp:
            from trainz_studio.ui.engine.pressure import to_bar

            assert abs(to_bar(bp) - 6.13) < 1e-6
        # notch +/- buttons not crushed
        col = host.throttle_editor.columns[5]
        assert col.tree.maximumHeight() >= 110
        host.sidebar.refresh_info(host.cfg)
        assert "bar" in host.sidebar._info_rows["bp"].text() or host.sidebar._info_rows["bp"].text() == "—"
    finally:
        host.deleteLater()
        app.processEvents()


def check_undo_redo() -> None:
    from PySide6.QtWidgets import QApplication

    from trainz_studio.lib.engine_tuner.config_io import load_config
    from trainz_studio.ui.engine import build_engine_tuner
    from trainz_studio.ui.theme import apply_theme

    sample = _sample_path()
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "dark")
    host = build_engine_tuner(on_home=lambda: None, theme_mode="dark")
    try:
        host.cfg = load_config(sample)
        host._load_into_ui()
        host.undo()
        assert "Nothing to undo" in host.path_lab.text()

        original_n5 = list(host.cfg.throttle_power[5])
        host._begin_edit()
        host.cfg.throttle_power[5] = [(0.0, 1.0)]
        host.undo()
        assert list(host.cfg.throttle_power[5]) == original_n5
        host.redo()
        assert host.cfg.throttle_power[5] == [(0.0, 1.0)]

        host.undo()
        host._begin_edit()
        host.cfg.throttle_power[5] = [(0.0, 2.0)]
        host.redo()
        assert "Nothing to redo" in host.path_lab.text()
        assert host.cfg.throttle_power[5] == [(0.0, 2.0)]

        before = host.cfg.clone()
        host.cfg.throttle_power[1] = [(0.0, 9.0)]
        host.history.record(before)
        host.undo()
        assert host.cfg.throttle_power[1] == before.throttle_power[1]
    finally:
        host.deleteLater()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    fast = "--fast" in argv
    checks: list[tuple[str, object]] = [
        ("config_io", check_config_io),
        ("physics", check_physics),
        ("autotune", check_autotune),
        ("airtune", check_airtune),
        ("pressure_units", check_pressure_units),
    ]
    if not fast:
        checks.extend(
            (
                ("ui_build", check_ui_builds),
                ("undo_redo", check_undo_redo),
            )
        )
    for name, fn in checks:
        fn()
        print(f"engine_tuner check: {name} ok")
    print("engine_tuner check: all ok" + (" (fast)" if fast else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"engine_tuner check: FAILED — {exc}", file=sys.stderr)
        raise
