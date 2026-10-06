"""PyInstaller entry — freeze_support + thin boot (no relative package script)."""
from __future__ import annotations

import multiprocessing
import os
import sys

# Must precede any OpenGL import (also set again in boot / __main__).
os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")
os.environ.setdefault("PYOPENGL_ERROR_LOGGING", "0")


def main() -> int:
    multiprocessing.freeze_support()
    from trainz_studio.ui.boot import main as boot_main

    return int(boot_main())


if __name__ == "__main__":
    raise SystemExit(main())
