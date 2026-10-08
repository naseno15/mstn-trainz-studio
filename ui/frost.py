"""Frost glass panels — tiny module so HOME boot need not import Editor."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

# Layout insets for FrostGlassFrame — must cover plate pad + soft shadow room.
# Qt clips paint outside the widget; short margins cut the fade into a hard edge.
FROST_CONTENT_MARGINS = (28, 24, 28, 30)  # L,T,R,B — was 18/16/18/18


def make_frost_pixmap(src: QImage) -> QPixmap:
    """Cheap frosted backdrop — downscale / upscale (no QGraphicsBlurEffect)."""
    if src is None or src.isNull():
        return QPixmap()
    img = src.convertToFormat(QImage.Format.Format_RGB32)
    cur = img
    for _ in range(4):
        tw = max(8, cur.width() // 5)
        th = max(8, cur.height() // 5)
        cur = cur.scaled(
            tw,
            th,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    out_w = max(120, img.width() // 2)
    out_h = max(120, img.height() // 2)
    cur = cur.scaled(
        out_w,
        out_h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QPixmap.fromImage(cur)


def glass_is_dark(widget: QWidget) -> bool:
    """Read ``glassDark`` dynamic property (default dark)."""
    val = widget.property("glassDark")
    return True if not isinstance(val, bool) else val


def set_glass_dark(widget: QWidget, dark: bool) -> None:
    widget.setProperty("glassDark", bool(dark))
    widget.update()


def prepare_frost_scroll(area: QScrollArea) -> None:
    """Stop QScrollArea viewport from painting QPalette.Base (white/black slabs on theme flip)."""
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    area.setAutoFillBackground(False)
    vp = area.viewport()
    if vp is not None:
        vp.setAutoFillBackground(False)
        vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    body = area.widget()
    if body is not None:
        body.setAutoFillBackground(False)
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def paint_soft_shadow(
    p: QPainter,
    plate: QRectF,
    *,
    radius: float,
    dark: bool,
    clip: QRectF,
    max_spread: float = 14.0,
    dy: float = 2.5,
    peak_alpha: float = 38.0,
    layers: int = 14,
) -> None:
    """Contact shadow clamped inside ``clip`` — wide fade, no hard widget cut.

    Many thin rings (not 3 stepped slabs) so the falloff reads smooth instead
    of banded / pixel-y. Qt still clips paint outside the widget; callers must
    keep ``plate`` inset enough that ``max_spread`` fits in ``clip``.
    """
    if plate.width() < 4 or plate.height() < 4 or layers < 1:
        return
    scale = 1.0 if dark else 0.55
    n = max(1, int(layers))
    spread = max(4.0, float(max_spread))
    for i in range(n, 0, -1):
        t = i / n  # 1 = outer
        grow = spread * t
        # Ease-out alpha: near plate denser, outer rings nearly gone.
        fall = (1.0 - t) ** 1.55
        alpha = int(peak_alpha * fall * scale)
        if alpha < 2:
            continue
        sr = QRectF(plate).adjusted(
            -grow * 0.9,
            dy * 0.25,
            grow * 0.9,
            dy + grow,
        )
        sr = sr.intersected(clip)
        if sr.width() < 4 or sr.height() < 4:
            continue
        sp = QPainterPath()
        rad = min(radius + grow * 0.35, sr.width() * 0.5, sr.height() * 0.5)
        sp.addRoundedRect(sr, rad, rad)
        p.fillPath(sp, QColor(0, 0, 0, alpha))


def _glass_plate_rect(
    full: QRectF,
    *,
    side: float,
    top: float,
    bottom: float,
) -> QRectF:
    """Plate inset that never leaves ``full`` (shadow air stays inside)."""
    r = full.adjusted(side, top, -side, -bottom)
    if r.width() < 8 or r.height() < 8:
        return full.adjusted(4.0, 3.0, -4.0, -6.0)
    return r


def paint_glass_chip(widget: QWidget, radius: float = 22.0) -> None:
    """Floating glass pill — theme-aware (``glassDark`` property)."""
    dark = glass_is_dark(widget)
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    full = QRectF(widget.rect())
    if full.width() < 4 or full.height() < 4:
        return
    # Room for a wide soft halo — was ~5px bottom and got clipped hard.
    side, top, bot = 8.0, 5.0, 12.0
    r = _glass_plate_rect(full, side=side, top=top, bottom=bot)
    clip = full.adjusted(1.0, 1.0, -1.0, -1.0)
    paint_soft_shadow(
        p,
        r,
        radius=float(radius),
        dark=dark,
        clip=clip,
        max_spread=min(11.0, bot - 1.0),
        dy=2.0,
        peak_alpha=40.0,
        layers=12,
    )

    rad = min(float(radius), r.width() * 0.5, r.height() * 0.5)
    path = QPainterPath()
    path.addRoundedRect(r, rad, rad)

    fill = QLinearGradient(r.topLeft(), r.bottomLeft())
    if dark:
        fill.setColorAt(0.0, QColor(255, 255, 255, 42))
        fill.setColorAt(0.18, QColor(48, 54, 64, 155))
        fill.setColorAt(0.55, QColor(28, 34, 42, 168))
        fill.setColorAt(1.0, QColor(16, 20, 26, 185))
        rim = QColor(255, 255, 255, 58)
        spec = QColor(255, 255, 255, 100)
        sheen0 = QColor(255, 255, 255, 70)
    else:
        # Soft gray chip — sits above #d8dce3 stage, not blown white.
        fill.setColorAt(0.0, QColor(246, 248, 251, 200))
        fill.setColorAt(0.35, QColor(236, 240, 246, 195))
        fill.setColorAt(0.75, QColor(220, 226, 234, 205))
        fill.setColorAt(1.0, QColor(204, 212, 222, 215))
        rim = QColor(255, 255, 255, 140)
        spec = QColor(255, 255, 255, 170)
        sheen0 = QColor(255, 255, 255, 90)
    p.fillPath(path, fill)

    sheen = QLinearGradient(r.topLeft(), QRectF(r).center())
    sheen.setColorAt(0.0, sheen0)
    sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)

    p.setPen(QPen(rim, 1.0))
    p.drawPath(path)
    p.setPen(QPen(spec, 1.15))
    p.drawLine(int(r.left() + rad), int(r.top() + 1), int(r.right() - rad), int(r.top() + 1))


def _paint_frost_glass_to(
    p: QPainter,
    full: QRectF,
    *,
    radius: float,
    frost: QPixmap | None,
    dark: bool,
) -> None:
    """Shared glass plate onto an existing painter — soft shadow + frost + tint."""
    if full.width() < 4 or full.height() < 4:
        return
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # Match FROST_CONTENT_MARGINS air: side/top/bot leave room for a full fade.
    side, top, bot = 14.0, 11.0, 16.0
    r = _glass_plate_rect(full, side=side, top=top, bottom=bot)
    clip = full.adjusted(1.0, 1.0, -1.0, -1.0)
    paint_soft_shadow(
        p,
        r,
        radius=float(radius),
        dark=dark,
        clip=clip,
        max_spread=min(14.0, bot - 1.5),
        dy=2.5,
        peak_alpha=36.0,
        layers=14,
    )

    rad = min(radius, r.width() * 0.5, r.height() * 0.5)
    path = QPainterPath()
    path.addRoundedRect(r, rad, rad)

    p.setClipPath(path)
    if frost is not None and not frost.isNull():
        p.drawPixmap(r.toRect(), frost)
    else:
        p.fillPath(
            path,
            QColor(30, 34, 40, 210) if dark else QColor(232, 236, 242, 220),
        )
    tint = QLinearGradient(r.topLeft(), r.bottomLeft())
    if dark:
        tint.setColorAt(0.0, QColor(255, 255, 255, 28))
        tint.setColorAt(0.12, QColor(36, 42, 50, 110))
        tint.setColorAt(0.55, QColor(18, 22, 28, 140))
        tint.setColorAt(1.0, QColor(10, 12, 16, 165))
    else:
        tint.setColorAt(0.0, QColor(255, 255, 255, 110))
        tint.setColorAt(0.45, QColor(240, 243, 247, 100))
        tint.setColorAt(1.0, QColor(210, 216, 224, 130))
    p.fillPath(path, tint)
    sheen = QLinearGradient(r.topLeft(), QRectF(r).center())
    sheen.setColorAt(0.0, QColor(255, 255, 255, 55 if dark else 70))
    sheen.setColorAt(0.55, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)
    p.setClipping(False)

    p.setPen(QPen(QColor(255, 255, 255, 55 if dark else 110), 1.0))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 90 if dark else 140), 1.2))
    y = r.top() + 1.0
    p.drawLine(
        int(r.left() + rad),
        int(y),
        int(r.right() - rad),
        int(y),
    )


def _paint_frost_glass(
    widget: QWidget,
    *,
    radius: float,
    frost: QPixmap | None,
    dark: bool,
) -> None:
    """Shared glass plate — soft shadow + frost + light tint."""
    p = QPainter(widget)
    _paint_frost_glass_to(
        p, QRectF(widget.rect()), radius=radius, frost=frost, dark=dark
    )


def bake_frost_plate(
    width: int,
    height: int,
    *,
    radius: float,
    frost: QPixmap | None,
    dark: bool,
    dpr: float = 1.0,
) -> QPixmap:
    """Bake full glass (14-ring shadow) once for motion-lod blit."""
    w = max(1, int(width))
    h = max(1, int(height))
    scale = max(1.0, float(dpr))
    pm = QPixmap(max(1, int(w * scale)), max(1, int(h * scale)))
    pm.setDevicePixelRatio(scale)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    _paint_frost_glass_to(
        p, QRectF(0.0, 0.0, float(w), float(h)), radius=radius, frost=frost, dark=dark
    )
    p.end()
    return pm


class FrostGlassFrame(QFrame):
    """Floating frost panel (sidebar / Editor / Settings)."""

    def __init__(self, parent: QWidget | None = None, *, radius: float = 14.0) -> None:
        super().__init__(parent)
        self._frost: QPixmap | None = None
        self._radius = float(radius)
        self._dark = True
        self._motion_lod = False
        self._lod_pm: QPixmap | None = None
        self._paint_plate = True
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_frost(self, pm: QPixmap | None, *, dark: bool = True) -> None:
        self._frost = pm
        self._dark = bool(dark)
        # Mid-slide: keep lod plate; fresh frost applies on end_motion_lod.
        if not self._motion_lod:
            self.update()

    def set_paint_plate(self, on: bool) -> None:
        """QML GlassPlate owns the dock face. Skip this widget's own plate."""
        self._paint_plate = bool(on)
        self.update()

    def set_dark(self, dark: bool) -> None:
        """Retint glass plate — drop stale frost so light/dark never mix."""
        dark = bool(dark)
        if dark == self._dark and self._frost is None:
            return
        self._dark = dark
        self._frost = None
        if self._motion_lod:
            self.end_motion_lod()
            return
        self.update()

    def begin_motion_lod(self) -> None:
        """Cache full glass once — later paints blit only (silk dock/hub slides)."""
        w, h = self.width(), self.height()
        if w < 4 or h < 4:
            self._motion_lod = False
            self._lod_pm = None
            return
        self._lod_pm = bake_frost_plate(
            w,
            h,
            radius=self._radius,
            frost=self._frost,
            dark=self._dark,
            dpr=float(self.devicePixelRatioF()),
        )
        self._motion_lod = True

    def end_motion_lod(self) -> None:
        """Drop plate cache and redraw live glass (full soft shadow again)."""
        self._motion_lod = False
        self._lod_pm = None
        self.update()

    def in_motion_lod(self) -> bool:
        return bool(self._motion_lod)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if not self._paint_plate:
            return
        if self._motion_lod and self._lod_pm is not None and not self._lod_pm.isNull():
            p = QPainter(self)
            p.drawPixmap(0, 0, self._lod_pm)
            return
        _paint_frost_glass(
            self, radius=self._radius, frost=self._frost, dark=self._dark
        )
