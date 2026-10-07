"""Damped pixel scroll for QAbstractItemView / QScrollArea / code editors."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTreeWidget,
    QWidget,
)

# Heavier coast = longer glide; softer impulse = less twitchy wheel steps.
DEFAULT_COAST = 0.955
DEFAULT_IMPULSE_PIXEL = 0.20
DEFAULT_IMPULSE_NOTCH = 12.0
DEFAULT_VEL_CAP = 72.0

# CodeEdit / text viewers — short glide, hard brake (user: ลื่นเกิน / เบรคไม่อยู่)
CODE_COAST = 0.78
CODE_IMPULSE_PIXEL = 0.22
CODE_IMPULSE_NOTCH = 14.0
CODE_VEL_CAP = 48.0
CODE_STOP_VEL = 0.35
CODE_EDGE_DAMP = 0.08


class DampedScrollFilter(QObject):
    """Wheel inertia — soft coast, passes through when view can't scroll.

    With ``middle_auto=True`` (CodeEdit): middle-click toggles browser-style
    autoscroll — move mouse above/below origin to scroll; middle/left/Esc stops.
    """

    def __init__(
        self,
        view: QAbstractScrollArea,
        *,
        coast: float = DEFAULT_COAST,
        impulse_pixel: float = DEFAULT_IMPULSE_PIXEL,
        impulse_notch: float = DEFAULT_IMPULSE_NOTCH,
        vel_cap: float = DEFAULT_VEL_CAP,
        stop_vel: float = 0.08,
        edge_damp: float = 0.18,
        middle_auto: bool = False,
    ) -> None:
        super().__init__(view)
        self._view = view
        self._coast = float(coast)
        self._impulse_pixel = float(impulse_pixel)
        self._impulse_notch = float(impulse_notch)
        self._vel_cap = float(vel_cap)
        self._stop_vel = float(stop_vel)
        self._edge_damp = float(edge_damp)
        self._middle_auto = bool(middle_auto)
        self._auto_active = False
        self._auto_origin: QPoint | None = None
        self._cursor_overridden = False
        self._vel = 0.0
        self._pos: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._view.viewport().installEventFilter(self)
        # Wheel hits the child under the cursor. Qt does not retarget that
        # event onto the viewport, so a viewport-only filter never scrolls.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _bar(self):
        return self._view.verticalScrollBar()

    def _under_view(self, obj) -> bool:
        view = getattr(self, "_view", None)
        if view is None or not isinstance(obj, QWidget):
            return False
        try:
            vp = view.viewport()
        except RuntimeError:
            return False
        w: QWidget | None = obj
        while w is not None:
            if w is vp or w is view:
                return True
            w = w.parentWidget()
        return False

    def _inner_scroll_takes(self, obj, vp, impulse: float) -> bool:
        """A nested scroll area that can still move keeps the wheel."""
        w: QWidget | None = obj if isinstance(obj, QWidget) else None
        while w is not None and w is not vp and w is not self._view:
            if isinstance(w, QAbstractScrollArea):
                bar = w.verticalScrollBar()
                lo, hi = bar.minimum(), bar.maximum()
                if hi > lo and (
                    (impulse > 0 and bar.value() < hi)
                    or (impulse < 0 and bar.value() > lo)
                ):
                    return True
            w = w.parentWidget()
        return False

    def _brake_coast(self) -> None:
        self._vel = 0.0
        try:
            self._pos = float(self._bar().value())
        except RuntimeError:
            self._pos = None

    def _start_auto(self, origin: QPoint) -> None:
        self._brake_coast()
        self._auto_active = True
        self._auto_origin = QPoint(origin)
        if not self._cursor_overridden:
            QApplication.setOverrideCursor(Qt.CursorShape.SizeVerCursor)
            self._cursor_overridden = True
        if not self._timer.isActive():
            self._timer.start()

    def _stop_auto(self) -> None:
        self._auto_active = False
        self._auto_origin = None
        self._brake_coast()
        if self._cursor_overridden:
            QApplication.restoreOverrideCursor()
            self._cursor_overridden = False
        if self._timer.isActive() and abs(self._vel) < self._stop_vel:
            self._timer.stop()

    def _handle_middle_auto(self, obj, event) -> bool:
        """Toggle / stop middle-click autoscroll. True = event consumed."""
        if not self._middle_auto:
            return False
        et = event.type()
        if et == QEvent.Type.KeyPress and self._auto_active:
            if event.key() == Qt.Key.Key_Escape:
                self._stop_auto()
                event.accept()
                return True
            return False
        if et == QEvent.Type.MouseButtonPress:
            btn = event.button()
            if self._auto_active:
                # second middle / any left click stops (even outside the view)
                if btn in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
                    self._stop_auto()
                    event.accept()
                    return True
                return False
            if btn == Qt.MouseButton.MiddleButton and self._under_view(obj):
                bar = self._bar()
                if bar.maximum() <= bar.minimum():
                    return False
                self._start_auto(QCursor.pos())
                event.accept()
                return True
        return False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if self._handle_middle_auto(obj, event):
            return True
        if event.type() != QEvent.Type.Wheel:
            return False
        view = getattr(self, "_view", None)
        if view is None:
            return False
        try:
            vp = view.viewport()
        except RuntimeError:
            return False
        if self._auto_active:
            # wheel exits autoscroll then applies normal impulse
            self._stop_auto()
        if not self._under_view(obj):
            return False
        pixel = event.pixelDelta().y()
        angle = event.angleDelta().y()
        if pixel != 0:
            impulse = -float(pixel) * self._impulse_pixel
        elif angle != 0:
            impulse = -float(angle) / 120.0 * self._impulse_notch
        else:
            return False
        if obj is not vp and self._inner_scroll_takes(obj, vp, impulse):
            return False
        bar = self._bar()
        lo = bar.minimum()
        hi = bar.maximum()
        if hi <= lo:
            return False
        at_top = bar.value() <= lo
        at_bottom = bar.value() >= hi
        if (impulse < 0 and at_top) or (impulse > 0 and at_bottom):
            return False
        if self._pos is None or not self._timer.isActive():
            self._pos = float(bar.value())
        # reverse wheel → kill coast so it actually brakes
        if self._vel and (self._vel > 0) != (impulse > 0):
            self._vel = 0.0
        cap = self._vel_cap
        self._vel = float(max(-cap, min(cap, self._vel + impulse)))
        if not self._timer.isActive():
            self._timer.start()
        event.accept()
        return True

    def _tick(self) -> None:
        bar = self._bar()
        lo = float(bar.minimum())
        hi = float(bar.maximum())
        if self._pos is None:
            self._pos = float(bar.value())

        if self._auto_active and self._auto_origin is not None:
            if hi <= lo:
                return
            dy = QCursor.pos().y() - self._auto_origin.y()
            dead = 12
            if abs(dy) <= dead:
                self._vel = 0.0
            else:
                signed = float(dy - dead if dy > 0 else dy + dead)
                # farther from origin → faster; 80px ≈ full cap
                self._vel = max(
                    -self._vel_cap,
                    min(self._vel_cap, signed / 80.0 * self._vel_cap),
                )
            if abs(self._vel) >= self._stop_vel:
                self._pos += self._vel
                if self._pos < lo:
                    self._pos = lo
                    self._vel = 0.0
                elif self._pos > hi:
                    self._pos = hi
                    self._vel = 0.0
                bar.setValue(int(round(self._pos)))
            return

        if abs(self._vel) < self._stop_vel:
            self._vel = 0.0
            self._pos = float(bar.value())
            self._timer.stop()
            return
        self._pos += self._vel
        if self._pos < lo:
            self._pos = lo
            self._vel *= self._edge_damp
        elif self._pos > hi:
            self._pos = hi
            self._vel *= self._edge_damp
        bar.setValue(int(round(self._pos)))
        self._vel *= self._coast


def _prepare_item_view(view: QAbstractItemView) -> None:
    """Stop viewports / headers painting Windows Base white under translucent QSS."""
    view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    view.setAutoFillBackground(False)
    vp = view.viewport()
    if vp is not None:
        vp.setAutoFillBackground(False)
        vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    headers: list[QHeaderView | None] = []
    if isinstance(view, QTreeWidget):
        headers.append(view.header())
    elif isinstance(view, QTableWidget):
        headers.append(view.horizontalHeader())
        headers.append(view.verticalHeader())
    for hdr in headers:
        if hdr is None:
            continue
        hdr.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hdr.setAutoFillBackground(False)
    # Rounded row hover/selection — QSS radii are ignored for multi-col items on Win.
    from .table_chrome import install_rounded_rows

    install_rounded_rows(view)


def enable_smooth_scroll(
    view: QAbstractItemView,
    *,
    coast: float = DEFAULT_COAST,
    impulse_pixel: float = DEFAULT_IMPULSE_PIXEL,
    impulse_notch: float = DEFAULT_IMPULSE_NOTCH,
    vel_cap: float = DEFAULT_VEL_CAP,
    horizontal: bool = False,
) -> None:
    """Pixel scroll + damped wheel. Keeps a ref on the view so GC keeps the filter."""
    _prepare_item_view(view)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    if horizontal:
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    else:
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    bar = view.verticalScrollBar()
    bar.setSingleStep(4)
    bar.setPageStep(36)
    view.setAlternatingRowColors(True)
    _bind_damped(
        view,
        DampedScrollFilter(
            view,
            coast=coast,
            impulse_pixel=impulse_pixel,
            impulse_notch=impulse_notch,
            vel_cap=vel_cap,
        ),
    )


def enable_smooth_table(
    view: QAbstractItemView,
    *,
    coast: float = DEFAULT_COAST,
    flat: bool = True,
    horizontal: bool = False,
) -> None:
    """Engine-style flat data table: smooth scroll + optional flatten tree chrome."""
    enable_smooth_scroll(view, coast=coast, horizontal=horizontal)
    if isinstance(view, QTreeWidget):
        if flat:
            if not view.objectName():
                view.setObjectName("engineTable")
            hdr = view.header()
            if hdr is not None:
                hdr.setObjectName("studioTableHeader")
            view.setRootIsDecorated(False)
            view.setIndentation(0)
    elif isinstance(view, QTableWidget):
        if not view.objectName():
            view.setObjectName("studioTable")
        hdr = view.horizontalHeader()
        # Don't clobber page-specific headers (e.g. pkgFinderHeader).
        if hdr is not None and not hdr.objectName():
            hdr.setObjectName("studioTableHeader")


def enable_smooth_scroll_area(area: QScrollArea, *, coast: float = DEFAULT_COAST) -> None:
    from .frost import prepare_frost_scroll

    if not area.objectName():
        area.setObjectName("sideScroll")
    prepare_frost_scroll(area)
    bar = area.verticalScrollBar()
    bar.setSingleStep(6)
    bar.setPageStep(48)
    _bind_damped(area, DampedScrollFilter(area, coast=coast))


def enable_code_scroll(area: QAbstractScrollArea) -> None:
    """Short-coast wheel + middle-click toggle autoscroll for CodeEdit."""
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    bar = area.verticalScrollBar()
    bar.setSingleStep(3)
    bar.setPageStep(32)
    _bind_damped(
        area,
        DampedScrollFilter(
            area,
            coast=CODE_COAST,
            impulse_pixel=CODE_IMPULSE_PIXEL,
            impulse_notch=CODE_IMPULSE_NOTCH,
            vel_cap=CODE_VEL_CAP,
            stop_vel=CODE_STOP_VEL,
            edge_damp=CODE_EDGE_DAMP,
            middle_auto=True,
        ),
    )


def _bind_damped(host: QAbstractScrollArea, filt: DampedScrollFilter) -> None:
    """Keep one live filter. A replaced filter stays installed and then throws."""
    old = getattr(host, "_damped_scroll", None)
    if old is not None and old is not filt:
        if hasattr(old, "_stop_auto"):
            old._stop_auto()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(old)
        try:
            host.viewport().removeEventFilter(old)
        except RuntimeError:
            pass
        old.deleteLater()
    host._damped_scroll = filt  # type: ignore[attr-defined]


if __name__ == "__main__":
    # ponytail: middle-auto toggle + brake — fails if autoscroll state breaks
    import sys

    from PySide6.QtWidgets import QApplication, QPlainTextEdit

    app = QApplication.instance() or QApplication(sys.argv)
    ed = QPlainTextEdit()
    ed.setPlainText("\n".join(f"line {i}" for i in range(80)))
    ed.resize(320, 200)
    enable_code_scroll(ed)
    filt = ed._damped_scroll  # type: ignore[attr-defined]
    assert filt._middle_auto
    assert not filt._auto_active
    filt._start_auto(QPoint(100, 100))
    assert filt._auto_active and filt._auto_origin == QPoint(100, 100)
    filt._stop_auto()
    assert not filt._auto_active and filt._auto_origin is None
    print("smooth_scroll middle_auto: ok")
