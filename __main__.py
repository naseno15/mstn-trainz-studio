from __future__ import annotations

import os

# PyOpenGL defaults ERROR_CHECKING=True → glGetError after every call (viewport jank).
# Must be set before any `from OpenGL import GL`.
os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")
os.environ.setdefault("PYOPENGL_ERROR_LOGGING", "0")

# Thin boot — QApplication before MainWindow import.
from .ui.boot import main

if __name__ == "__main__":
    raise SystemExit(main())
