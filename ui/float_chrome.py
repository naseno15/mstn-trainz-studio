"""Shared floating glass chrome — capsule bars with Home in the center.

Page labels stay text and split left / right. Theme is the top FloatTitleBar menu.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from .frost import glass_is_dark, paint_glass_chip, set_glass_dark
from .icons import set_home_icon

FLOAT_NAV_HEIGHT = 72  # single-line suites (Mesh / Engine / Assets / Sounds)
FLOAT_NAV_HEIGHT_TALL = 88  # two-line labels (Texture & Mesh Lods)
FLOAT_NAV_RADIUS = 30.0
NAV_ICON_SIDE = 36
NAV_ICON_SIDE_TALL = 48  # matches two-line page buttons
HOME_GAP = 16  # air between page cluster and Home (was 8 — too tight)
HOME_GAP_TALL = 22


def split_page_btns(
    page_btns: list[QPushButton] | tuple[QPushButton, ...],
) -> tuple[list[QPushButton], list[QPushButton]]:
    """Left gets ceil(n/2), right the rest — e.g. 3 → 2|1, 5 → 3|2."""
    btns = list(page_btns)
    mid = (len(btns) + 1) // 2
    return btns[:mid], btns[mid:]


def page_buttons_union(btns: list[QPushButton] | tuple[QPushButton, ...]) -> QRect | None:
    if not btns:
        return None
    r = QRect(btns[0].geometry())
    for b in btns[1:]:
        r = r.united(b.geometry())
    return r


def _paint_inset(p: QPainter, rect: QRect, *, dark: bool, pad: tuple[int, int, int, int]) -> None:
    l, t, r, b = pad
    rf = QRectF(rect.adjusted(l, t, r, b))
    if rf.width() < 8 or rf.height() < 8:
        return
    rad = min(16.0, rf.height() * 0.5)
    path = QPainterPath()
    path.addRoundedRect(rf, rad, rad)
    if dark:
        p.fillPath(path, QColor(0, 0, 0, 55))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
    else:
        p.fillPath(path, QColor(0, 0, 0, 18))
        p.setPen(QPen(QColor(255, 255, 255, 140), 1.0))
    p.drawPath(path)


def paint_float_nav(widget: QWidget) -> None:
    """Outer capsule + left/right page wells + soft well under Home/Theme."""
    paint_glass_chip(widget, radius=FLOAT_NAV_RADIUS)
    dark = glass_is_dark(widget)
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    wells = getattr(widget, "_page_well_rects", None)
    if callable(wells):
        for union in wells() or ():
            if union is not None and union.width() >= 8:
                _paint_inset(p, union, dark=dark, pad=(-6, -5, 6, 5))

    icons = getattr(widget, "_icon_well_rect", None)
    if callable(icons):
        ir = icons()
        if ir is not None and ir.width() >= 8:
            _paint_inset(p, ir, dark=dark, pad=(-8, -4, 8, 4))


def prepare_float_nav(frame: QFrame, *, height: int | None = None) -> None:
    frame.setObjectName("bottomNav")
    frame.setFixedHeight(int(height if height is not None else FLOAT_NAV_HEIGHT))
    # Soft corners need translucency; icon buttons stay opaque so they still click.
    frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


def _harden_nav_icon(btn: QPushButton) -> None:
    """Keep Home/Theme receiving mouse under a translucent float parent."""
    btn.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
    btn.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def make_home_button(parent: QWidget, *, side: int | None = None) -> QPushButton:
    """Center Home control — Theme lives in the top FloatTitleBar menu."""
    side = int(side if side is not None else NAV_ICON_SIDE)
    home = QPushButton(parent)
    set_home_icon(home, square=side)
    home.setFixedSize(side, side)
    _harden_nav_icon(home)
    return home


def make_home_theme_buttons(
    parent: QWidget, *, mode: str = "dark"
) -> tuple[QPushButton, QPushButton]:
    """Back-compat — Theme button unused on bottom bars (menu bar owns Theme)."""
    del mode
    home = make_home_button(parent)
    theme = QPushButton(parent)
    theme.hide()
    return home, theme


def mount_center_icon_nav(
    lay: QHBoxLayout,
    *,
    home_btn: QPushButton,
    page_btns: list[QPushButton] | tuple[QPushButton, ...],
    theme_btn: QPushButton | None = None,
    home_gap: int | None = None,
) -> tuple[list[QPushButton], list[QPushButton]]:
    """pages-left | Home | pages-right — Theme is top-bar only."""
    del theme_btn  # kept for call-site compat; never mounted
    gap = int(home_gap if home_gap is not None else HOME_GAP)
    left, right = split_page_btns(page_btns)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(4)
    for b in left:
        lay.addWidget(b)
    if left:
        lay.addSpacing(gap)
    lay.addWidget(home_btn)
    if right:
        lay.addSpacing(gap)
    for b in right:
        lay.addWidget(b)
    return left, right


def bind_split_wells(
    frame: QWidget,
    *,
    home_btn: QPushButton,
    left_btns: list[QPushButton],
    right_btns: list[QPushButton],
    theme_btn: QPushButton | None = None,
) -> None:
    """Wire paint helpers for left/right page wells + Home well."""
    del theme_btn

    def _page_wells() -> list[QRect]:
        out: list[QRect] = []
        for group in (left_btns, right_btns):
            u = page_buttons_union(group)
            if u is not None:
                out.append(u)
        return out

    def _icon_well() -> QRect | None:
        return page_buttons_union((home_btn,))

    frame._page_well_rects = _page_wells  # type: ignore[attr-defined]
    frame._icon_well_rect = _icon_well  # type: ignore[attr-defined]


def mount_page_only_nav(
    lay: QHBoxLayout,
    page_btns: list[QPushButton] | tuple[QPushButton, ...],
) -> list[QPushButton]:
    """Centered page labels only — no Home/Theme (top sub-nav)."""
    btns = list(page_btns)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(4)
    lay.addStretch(1)
    for b in btns:
        lay.addWidget(b)
    lay.addStretch(1)
    return btns


def bind_page_well(
    frame: QWidget,
    page_btns: list[QPushButton] | tuple[QPushButton, ...],
) -> None:
    """Single inset well under page labels (no center icon cluster)."""

    def _page_wells() -> list[QRect]:
        u = page_buttons_union(page_btns)
        return [u] if u is not None else []

    frame._page_well_rects = _page_wells  # type: ignore[attr-defined]
    frame._icon_well_rect = lambda: None  # type: ignore[attr-defined]


def hit_page_cluster(
    page_btns: list[QPushButton] | tuple[QPushButton, ...], pt
) -> bool:
    """True if point sits on a page label (not the center icon gap)."""
    for b in page_btns:
        if b.geometry().adjusted(-4, -4, 4, 4).contains(pt):
            return True
    return False


# Back-compat alias used by older call sites / checks
def mount_bookend_nav(
    lay: QHBoxLayout,
    *,
    home_btn: QPushButton,
    page_btns: list[QPushButton] | tuple[QPushButton, ...],
    theme_btn: QPushButton | None = None,
) -> None:
    mount_center_icon_nav(
        lay, home_btn=home_btn, page_btns=page_btns, theme_btn=theme_btn
    )


class FloatActionBar(QFrame):
    """Compact floating capsule — Home only (Theme is top FloatTitleBar menu)."""

    home_clicked = Signal()
    theme_clicked = Signal()  # unused — kept so old connect sites do not break

    def __init__(self, parent: QWidget | None = None, *, mode: str = "dark") -> None:
        super().__init__(parent)
        prepare_float_nav(self)
        set_glass_dark(self, mode != "light")
        self.home_btn = make_home_button(self)
        self.theme_btn = QPushButton(self)
        self.theme_btn.hide()
        self.home_btn.clicked.connect(self.home_clicked.emit)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(self.home_btn)
        from .motion import attach_hover_bubble

        attach_hover_bubble(self, (self.home_btn,), radius=14.0)

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        set_glass_dark(self, mode != "light")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            if self.home_btn.geometry().contains(pt):
                self.home_btn.click()
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        paint_glass_chip(self, radius=FLOAT_NAV_RADIUS)
