"""Machine-sized runtime knobs (CPU count → worker pools / BLAS / priority)."""
from __future__ import annotations

import os
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def cpu_count() -> int:
    return max(1, os.cpu_count() or 4)


def _worker_budget() -> int:
    """Leave one logical core for UI + GL; use the rest for CPU work."""
    return max(1, cpu_count() - 1)


def decode_workers() -> int:
    """Texture precache threads — scale with machine, soft-cap for RAM thrash."""
    # ponytail: cap 24 — beyond that Pillow decode is usually I/O / cache bound
    return min(24, max(2, _worker_budget()))


def bake_workers() -> int:
    """CPU bake chunk workers (CUDA path ignores this when CuPy is live)."""
    return min(16, max(2, _worker_budget()))


def apply_runtime_threads(env: os._Environ[str] | dict[str, str] | None = None) -> None:
    """Set BLAS/OpenMP thread caps once at process start if unset."""
    target = os.environ if env is None else env
    n = str(_worker_budget())
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        target.setdefault(key, n)


def boost_process() -> None:
    """Win32: ABOVE_NORMAL so Studio beats browsers/Steam for CPU slices.

    HIGH_PRIORITY_CLASS is avoided — it can starve DWM / audio and feel worse.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # ABOVE_NORMAL_PRIORITY_CLASS
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(),
            0x00008000,
        )
    except Exception:
        pass


def apply_qt_gl_attrs() -> None:
    """Force desktop OpenGL before QApplication (no ANGLE/software fallback)."""
    try:
        from PySide6.QtCore import QCoreApplication, Qt

        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True
        )
        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
        )
    except Exception:
        pass


def apply_all() -> None:
    """One-shot boot: threads + process priority + Qt GL attrs."""
    apply_runtime_threads()
    boost_process()
    apply_qt_gl_attrs()


def summary() -> str:
    return (
        f"cpus={cpu_count()} tex_workers={decode_workers()} "
        f"bake_workers={bake_workers()}"
    )
