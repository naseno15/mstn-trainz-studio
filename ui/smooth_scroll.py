"""Damped pixel scroll for QAbstractItemView / QScrollArea / code editors."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTreeWidget,
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
    """Wheel inertia — soft coast, passes through when view can't scroll."""

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
    ) -> None:
        super().__init__(view)
        self._view = view
        self._coast = float(coast)
        self._impulse_pixel = float(impulse_pixel)
        self._impulse_notch = float(impulse_notch)
        self._vel_cap = float(vel_cap)
        self._stop_vel = float(stop_vel)
        self._edge_damp = float(edge_damp)
        self._vel = 0.0
        self._pos: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._view.viewport().installEventFilter(self)

    def _bar(self):
        return self._view.verticalScrollBar()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        try:
            vp = self._view.viewport()
        except RuntimeError:
            return False
        if obj is not vp or event.type() != QEvent.Type.Wheel:
            return False
        pixel = event.pixelDelta().y()
        angle = event.angleDelta().y()
        if pixel != 0:
            impulse = -float(pixel) * self._impulse_pixel
        elif angle != 0:
            impulse = -float(angle) / 120.0 * self._impulse_notch
        else:
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
    view._damped_scroll = DampedScrollFilter(  # type: ignore[attr-defined]
        view,
        coast=coast,
        impulse_pixel=impulse_pixel,
        impulse_notch=impulse_notch,
        vel_cap=vel_cap,
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
        if hdr is not None:
            hdr.setObjectName("studioTableHeader")


def enable_smooth_scroll_area(area: QScrollArea, *, coast: float = DEFAULT_COAST) -> None:
    from .frost import prepare_frost_scroll

    if not area.objectName():
        area.setObjectName("sideScroll")
    prepare_frost_scroll(area)
    bar = area.verticalScrollBar()
    bar.setSingleStep(6)
    bar.setPageStep(48)
    area._damped_scroll = DampedScrollFilter(area, coast=coast)  # type: ignore[attr-defined]


def enable_code_scroll(area: QAbstractScrollArea) -> None:
    """Short-coast wheel for CodeEdit / plain-text viewers (brakes quickly)."""
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    bar = area.verticalScrollBar()
    bar.setSingleStep(3)
    bar.setPageStep(32)
    area._damped_scroll = DampedScrollFilter(  # type: ignore[attr-defined]
        area,
        coast=CODE_COAST,
        impulse_pixel=CODE_IMPULSE_PIXEL,
        impulse_notch=CODE_IMPULSE_NOTCH,
        vel_cap=CODE_VEL_CAP,
        stop_vel=CODE_STOP_VEL,
        edge_damp=CODE_EDGE_DAMP,
    )
