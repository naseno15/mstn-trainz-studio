"""Background import of heavy hub modules — overlaps MainWindow construction."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

_HUB_MODULES = (
    "trainz_studio.ui.frost",
    "trainz_studio.ui.editor",
    "trainz_studio.ui.sounds",
    "trainz_studio.ui.engine",
    "trainz_studio.ui.assets",
    "trainz_studio.ui.assets.studio",
    "trainz_studio.ui.assets.packages",
    "trainz_studio.io.loaders",
    "trainz_studio.io.trainz_install",
    "trainz_studio.ui.trainzutil_host",
)

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_done = False
_current = ""
_finished = 0
_t0 = time.perf_counter()
_log_fn: Optional[Callable[[str], None]] = None
_pending: list[str] = []


def preload_progress() -> tuple[str, int, int]:
    """Module being imported, how many finished, and the list length."""
    with _lock:
        return _current, _finished, len(_HUB_MODULES)


def set_boot_logger(fn: Optional[Callable[[str], None]]) -> None:
    """UI sink for boot lines. Main-thread calls paint immediately; import thread queues."""
    global _log_fn
    _log_fn = fn
    if fn is None:
        with _lock:
            _pending.clear()
        return
    drain_boot_log()


def boot_log(text: str) -> None:
    """One loading-dialog line: seconds since boot, then the call."""
    line = f"{time.perf_counter() - _t0:6.2f}s  {text}"
    fn = _log_fn
    if threading.current_thread() is threading.main_thread():
        if fn is not None:
            fn(line)
        return
    with _lock:
        if len(_pending) < 80:
            _pending.append(line)


def drain_boot_log() -> None:
    fn = _log_fn
    if fn is None:
        return
    with _lock:
        lines = list(_pending)
        _pending.clear()
    for line in lines:
        fn(line)


def start_hub_module_preload() -> threading.Thread:
    """Import hub packages on a daemon thread (safe: import only, no QWidgets)."""
    global _thread, _done
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        if _done:
            t = threading.Thread(target=lambda: None, daemon=True)
            t.start()
            t.join(0)
            return t

        def _run() -> None:
            global _done, _current, _finished
            for name in _HUB_MODULES:
                with _lock:
                    _current = name
                short = name.rsplit(".", 1)[-1]
                boot_log(f"import {name}")
                started = time.perf_counter()
                try:
                    __import__(name)
                    boot_log(f"imported {short} · {(time.perf_counter() - started) * 1000:.0f} ms")
                except Exception as exc:
                    boot_log(f"import failed {short} · {exc}")
                with _lock:
                    _finished += 1
                    _current = ""
            _done = True

        _thread = threading.Thread(target=_run, name="ts-hub-preload", daemon=True)
        _thread.start()
        return _thread


def join_hub_module_preload(timeout: float = 12.0) -> bool:
    """Wait for preload (or return False on timeout). Idempotent if already done."""
    global _thread
    t = _thread
    if t is None:
        return _done
    t.join(timeout=max(0.05, float(timeout)))
    return not t.is_alive()


def hub_modules_ready() -> bool:
    return bool(_done)
