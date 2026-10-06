"""Clip playback — Windows winsound; supports one-shot finish for A→B."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from ...audio.export_wav import write_mono_pcm16


class ClipPlayer:
    """ponytail: winsound on Windows — timing ≈ duration, not sample-accurate."""

    def __init__(self) -> None:
        self._tmp: Path | None = None
        self._playing = False
        self._loop = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._mono: np.ndarray | None = None
        self._sr = 44100
        self._t0 = 0.0
        self._duration_s = 0.0
        self._oneshot_done = False

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def oneshot_done(self) -> bool:
        return self._oneshot_done

    def clear_oneshot_done(self) -> None:
        self._oneshot_done = False

    def set_loop(self, on: bool) -> None:
        self._loop = bool(on)

    def load(self, mono: np.ndarray, sample_rate: int) -> None:
        was_playing = self._playing
        if was_playing:
            self.stop()
        self._mono = np.asarray(mono, dtype=np.int16)
        self._sr = int(sample_rate)

    def play(self, *, start_s: float = 0.0, end_s: float | None = None, loop: bool | None = None) -> None:
        if self._mono is None or self._mono.size == 0:
            return
        use_loop = self._loop if loop is None else bool(loop)
        self.stop()
        self.clear_oneshot_done()
        sr = self._sr
        i0 = max(0, int(start_s * sr))
        i1 = self._mono.size if end_s is None else max(i0 + 1, int(end_s * sr))
        clip = self._mono[i0:i1]
        if clip.size == 0:
            return
        path = Path(tempfile.gettempdir()) / f"tzs_play_{os.getpid()}_{time.time_ns()}.wav"
        write_mono_pcm16(path, clip, sr)
        self._tmp = path
        self._stop.clear()
        self._playing = True
        self._t0 = time.monotonic()
        self._duration_s = clip.size / float(sr)
        self._loop = use_loop

        def _run() -> None:
            finished_clean = False
            try:
                if sys.platform.startswith("win"):
                    import winsound

                    flags = winsound.SND_FILENAME | winsound.SND_ASYNC
                    if use_loop:
                        flags |= winsound.SND_LOOP
                    winsound.PlaySound(str(path), flags)
                    if not use_loop:
                        end = time.monotonic() + self._duration_s
                        while not self._stop.is_set() and time.monotonic() < end:
                            time.sleep(0.03)
                        if not self._stop.is_set():
                            finished_clean = True
                        winsound.PlaySound(None, winsound.SND_PURGE)
                    else:
                        while not self._stop.is_set():
                            time.sleep(0.05)
                        winsound.PlaySound(None, winsound.SND_PURGE)
                else:
                    if use_loop:
                        while not self._stop.is_set():
                            time.sleep(0.05)
                    else:
                        end = time.monotonic() + self._duration_s
                        while not self._stop.is_set() and time.monotonic() < end:
                            time.sleep(0.03)
                        finished_clean = not self._stop.is_set()
            finally:
                self._playing = False
                if finished_clean and not use_loop:
                    self._oneshot_done = True

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self._playing = False
        self._oneshot_done = False
        if self._tmp is not None:
            try:
                self._tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._tmp = None

    def playhead_s(self) -> float:
        if not self._playing:
            return 0.0
        return max(0.0, time.monotonic() - self._t0)
