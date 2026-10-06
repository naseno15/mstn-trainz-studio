"""MSTN Trainz Studio — mesh preview + Trainz sounds tools."""
from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.3.0"


def _pkg_root() -> Path:
    # PyInstaller onedir: datas land under sys._MEIPASS/trainz_studio/
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        bundled = meipass / "trainz_studio"
        if bundled.is_dir():
            return bundled
        return meipass
    return Path(__file__).resolve().parent


# Package root (assets/, fixtures/, vendor/ live here — not under ui/io/…).
PKG_ROOT = _pkg_root()
# Repo root (trs22/): package lives at <repo>/trainz_studio
REPO_ROOT = PKG_ROOT.parent
# Sibling one-shot scripts folder (optional).
TOOLS_ROOT = REPO_ROOT / "tools"
