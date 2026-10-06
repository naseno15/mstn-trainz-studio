#!/usr/bin/env python3
"""Trainz Engine Tuner — Qt shell themed like MSTN Trainz Studio.

Logic lives in this package (config_io / physics / throttle_round).
UI lives in trainz_studio.ui.engine (HOME hub page + standalone).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root on path so `import trainz_studio` works when launched as a script.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> None:
    if "--check" in sys.argv:
        from .check import main as run_checks

        raise SystemExit(run_checks())

    from PySide6.QtWidgets import QApplication, QMainWindow

    from trainz_studio.ui.engine import build_engine_tuner
    from trainz_studio.ui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    theme = {"mode": "dark"}
    apply_theme(app, theme["mode"])

    win = QMainWindow()
    win.setWindowTitle("MSTN Engine Tuner")
    win.resize(1440, 920)
    win.setMinimumSize(1100, 700)

    def _close() -> None:
        win.close()

    def _toggle_theme() -> None:
        theme["mode"] = "light" if theme["mode"] == "dark" else "dark"
        apply_theme(app, theme["mode"])
        host.set_theme(theme["mode"])

    host = build_engine_tuner(
        on_home=_close, on_theme=_toggle_theme, theme_mode=theme["mode"]
    )
    host.status.connect(lambda msg: win.statusBar().showMessage(msg))
    win.setCentralWidget(host)
    win.statusBar().showMessage("Open an engine config.txt to begin.")
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
