"""Background import of heavy hub modules — overlaps MainWindow construction."""
from __future__ import annotations

import threading
from typing import Optional

_HUB_MODULES = (
    "trainz_studio.ui.frost",
    "trainz_studio.ui.editor",
    "trainz_studio.ui.sounds",
    "trainz_studio.ui.engine",
    "trainz_studio.ui.assets",
    "trainz_studio.ui.assets.studio",
    "trainz_studio.ui.assets.packages",
    "trainz_studio.io.loaders",
)

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_done = False


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
            global _done
            for name in _HUB_MODULES:
                try:
                    __import__(name)
                except Exception:
                    pass
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
