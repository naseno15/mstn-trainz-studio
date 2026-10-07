"""Machine-sized runtime knobs (CPU count → worker pools / BLAS / priority)."""
from __future__ import annotations

import os
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def cpu_count() -> int:
    return max(1, os.cpu_count() or 4)


@lru_cache(maxsize=1)
def total_ram_gb() -> float:
    """Best-effort physical RAM in GiB (0.0 if unknown)."""
    if sys.platform == "win32":
        try:
            import ctypes

            class _MemStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemStatusEx()
            stat.dwLength = ctypes.sizeof(_MemStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return float(stat.ullTotalPhys) / (1024.0 ** 3)
        except Exception:
            pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page > 0:
            return float(pages * page) / (1024.0 ** 3)
    except (AttributeError, OSError, ValueError):
        pass
    return 0.0


@lru_cache(maxsize=1)
def is_low_end() -> bool:
    """True on weak laptops — fewer cores and/or little RAM.

    Override: TRAINZ_STUDIO_LOW_END=1|0
    """
    forced = os.environ.get("TRAINZ_STUDIO_LOW_END", "").strip().lower()
    if forced in ("1", "true", "yes", "on"):
        return True
    if forced in ("0", "false", "no", "off"):
        return False
    cpus = cpu_count()
    ram = total_ram_gb()
    # ≤4 logical cores, or ≤8 GiB RAM → treat as low-spec UI path
    if cpus <= 4:
        return True
    if 0.0 < ram <= 8.0:
        return True
    return False


def prefer_instant_panels() -> bool:
    """Skip dock/sidebar slide anim — low-end anim leaves Editor covering Preview."""
    return is_low_end()


def prefer_short_hub_motion() -> bool:
    """Skip HOME↔studio morph on weak GPUs/CPUs (swap is already done)."""
    return is_low_end()


def prefer_light_boot_frost() -> bool:
    """Skip expensive centralWidget grab+blur during boot overlay."""
    return is_low_end()


def hub_reveal_ms(*, warm: bool) -> int:
    """Hub morph duration — silky on normal PCs; skip entirely on low-end."""
    if prefer_short_hub_motion():
        return 0
    # Was cut to ~420 and felt rushed/choppy; restore near original cinema length.
    return 640 if warm else 720


def _worker_budget() -> int:
    """Leave one logical core for UI + GL; use the rest for CPU work."""
    return max(1, cpu_count() - 1)


def decode_workers() -> int:
    """Texture precache threads — scale with machine, soft-cap for RAM thrash."""
    # ponytail: cap 24 — beyond that Pillow decode is usually I/O / cache bound
    budget = _worker_budget()
    if is_low_end():
        return min(4, max(1, budget))
    return min(24, max(2, budget))


def bake_workers() -> int:
    """CPU bake chunk workers (CUDA path ignores this when CuPy is live)."""
    budget = _worker_budget()
    if is_low_end():
        return min(2, max(1, budget))
    return min(16, max(2, budget))


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
    ram = total_ram_gb()
    ram_s = f"{ram:.1f}GiB" if ram > 0 else "?"
    return (
        f"cpus={cpu_count()} ram={ram_s} low_end={is_low_end()} "
        f"tex_workers={decode_workers()} bake_workers={bake_workers()}"
    )
