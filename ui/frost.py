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


def paint_glass_chip(widget: QWidget, radius: float = 22.0) -> None:
    """Floating glass pill — theme-aware (``glassDark`` property)."""
    dark = glass_is_dark(widget)
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    full = QRectF(widget.rect())
    if full.width() < 4 or full.height() < 4:
        return
    shadow_scale = 1.0 if dark else 0.72
    for grow, alpha in ((5.0, 22), (2.5, 40), (0.8, 55)):
        sr = full.adjusted(3.0, 4.0 + grow * 0.3, -3.0, 1.0 + grow)
        sp = QPainterPath()
        sp.addRoundedRect(sr, radius, radius)
        p.fillPath(sp, QColor(0, 0, 0, int(alpha * shadow_scale)))

    r = full.adjusted(3.5, 2.5, -3.5, -5.0)
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


def _paint_frost_glass(
    widget: QWidget,
    *,
    radius: float,
    frost: QPixmap | None,
    dark: bool,
) -> None:
    """Shared glass plate — soft shadow + frost + light tint."""
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    full = QRectF(widget.rect())
    if full.width() < 4 or full.height() < 4:
        return
    for grow, alpha in ((6.0, 18), (3.5, 32), (1.5, 48)):
        sr = full.adjusted(4.0 - grow * 0.2, 5.0, -4.0 + grow * 0.2, 2.0 + grow)
        spath = QPainterPath()
        spath.addRoundedRect(sr, radius + 1.0, radius + 1.0)
        p.fillPath(spath, QColor(0, 0, 0, alpha if dark else max(14, alpha // 2)))

    r = full.adjusted(4.0, 3.0, -4.0, -6.0)
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


class FrostGlassFrame(QFrame):
    """Floating frost panel (sidebar / Editor / Settings)."""

    def __init__(self, parent: QWidget | None = None, *, radius: float = 14.0) -> None:
        super().__init__(parent)
        self._frost: QPixmap | None = None
        self._radius = float(radius)
        self._dark = True
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_frost(self, pm: QPixmap | None, *, dark: bool = True) -> None:
        self._frost = pm
        self._dark = bool(dark)
        self.update()

    def set_dark(self, dark: bool) -> None:
        """Retint glass plate — drop stale frost so light/dark never mix."""
        dark = bool(dark)
        if dark == self._dark and self._frost is None:
            return
        self._dark = dark
        self._frost = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        _paint_frost_glass(
            self, radius=self._radius, frost=self._frost, dark=self._dark
        )
