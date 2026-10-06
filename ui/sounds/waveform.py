"""Simple peak waveform view for Sounds Studio."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..theme import palette


class WaveformWidget(QWidget):
    """Paint min/max peaks; optional selection + playhead."""

    selection_changed = Signal(float, float)  # t0, t1 seconds

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setObjectName("waveformView")
        self._mono: np.ndarray | None = None
        self._sr = 44100
        self._playhead = 0.0
        self._sel: tuple[float, float] | None = None
        self._drag_origin: float | None = None
        self._theme = "dark"
        self.setMouseTracking(True)

    def set_theme(self, mode: str) -> None:
        self._theme = mode
        self.update()

    def set_audio(self, mono: np.ndarray | None, sample_rate: int) -> None:
        self._mono = None if mono is None else np.asarray(mono, dtype=np.int16)
        self._sr = max(1, int(sample_rate))
        self._playhead = 0.0
        self._sel = None
        self.update()

    def set_playhead(self, t: float) -> None:
        self._playhead = max(0.0, float(t))
        self.update()

    def duration(self) -> float:
        if self._mono is None or self._mono.size == 0:
            return 0.0
        return self._mono.size / float(self._sr)

    def _x_to_t(self, x: float) -> float:
        w = max(1, self.width())
        return max(0.0, min(self.duration(), (x / w) * self.duration()))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            t = self._x_to_t(event.position().x())
            self._drag_origin = t
            self._sel = (t, t)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            t = self._x_to_t(event.position().x())
            a, b = sorted((self._drag_origin, t))
            self._sel = (a, b)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._sel is not None:
            a, b = self._sel
            if b - a < 0.01:
                self._sel = None
            else:
                self.selection_changed.emit(a, b)
            self._drag_origin = None
            self.update()
        super().mouseReleaseEvent(event)

    def clear_selection(self) -> None:
        self._sel = None
        self.update()

    def selection(self) -> tuple[float, float] | None:
        return self._sel

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pal = palette(self._theme)
        bg = QColor(pal.well_fill if hasattr(pal, "well_fill") else "#121214")
        p.fillRect(self.rect(), bg)

        if self._mono is None or self._mono.size < 2:
            p.setPen(QColor(pal.muted))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop a WAV / audio file")
            return

        w = max(1, self.width())
        h = max(1, self.height())
        mid = h // 2
        mono = self._mono
        # one min/max column per pixel
        cols = w
        n = mono.size
        ink = QColor(pal.accent)
        ink.setAlpha(210)
        pen = QPen(ink, 1)
        p.setPen(pen)
        for x in range(cols):
            i0 = int(x * n / cols)
            i1 = int((x + 1) * n / cols)
            if i1 <= i0:
                i1 = i0 + 1
            chunk = mono[i0:i1]
            mn = int(chunk.min())
            mx = int(chunk.max())
            y0 = mid - int((mx / 32768.0) * (mid - 4))
            y1 = mid - int((mn / 32768.0) * (mid - 4))
            if y1 < y0:
                y0, y1 = y1, y0
            p.drawLine(x, y0, x, max(y0 + 1, y1))

        # zero line
        p.setPen(QPen(QColor(pal.muted), 1))
        p.drawLine(0, mid, w, mid)

        if self._sel is not None:
            a, b = self._sel
            dur = self.duration() or 1.0
            x0 = int(a / dur * w)
            x1 = int(b / dur * w)
            sel = QColor(pal.accent)
            sel.setAlpha(50)
            p.fillRect(x0, 0, max(1, x1 - x0), h, sel)

        if self._playhead > 0 and self.duration() > 0:
            px = int(self._playhead / self.duration() * w)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawLine(px, 0, px, h)
