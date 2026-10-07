"""HOME hub — glassmorphism studio picker (Mesh / Sounds / Engine / Assets / TexMesh)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .frost import set_glass_dark
from .icons import ensure_material_icons, glyph, icon_font
from .motion import attach_hover_bubble
from .theme import app_font, palette


def _glass_blur_backdrop(width: int, height: int, *, dark: bool, accent: QColor) -> QPixmap:
    """Tiny painted plate → smooth upscale = soft glassian blur wash."""
    if width < 2 or height < 2:
        return QPixmap()
    src_w, src_h = 72, 44
    img = QImage(src_w, src_h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    qp = QPainter(img)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    base = QLinearGradient(0, 0, 0, src_h)
    if dark:
        base.setColorAt(0.0, QColor(44, 52, 64))
        base.setColorAt(0.35, QColor(18, 22, 28))
        base.setColorAt(0.72, QColor(10, 12, 16))
        base.setColorAt(1.0, QColor(4, 6, 8))
    else:
        base.setColorAt(0.0, QColor(252, 253, 255))
        base.setColorAt(0.40, QColor(238, 242, 248))
        base.setColorAt(1.0, QColor(220, 226, 234))
    qp.fillRect(0, 0, src_w, src_h, base)

    if dark:
        orbs = [
            (QPointF(src_w * 0.16, src_h * 0.18), src_w * 0.62, QColor(255, 255, 255, 48)),
            (QPointF(src_w * 0.86, src_h * 0.24), src_w * 0.70, QColor(accent.red(), accent.green(), accent.blue(), 72)),
            (QPointF(src_w * 0.52, src_h * 0.92), src_w * 0.78, QColor(70, 110, 150, 50)),
            (QPointF(src_w * 0.08, src_h * 0.78), src_w * 0.50, QColor(255, 255, 255, 22)),
            (QPointF(src_w * 0.70, src_h * 0.62), src_w * 0.40, QColor(accent.red(), accent.green(), accent.blue(), 28)),
        ]
    else:
        orbs = [
            (QPointF(src_w * 0.18, src_h * 0.16), src_w * 0.58, QColor(255, 255, 255, 220)),
            (QPointF(src_w * 0.88, src_h * 0.28), src_w * 0.64, QColor(accent.red(), accent.green(), accent.blue(), 55)),
            (QPointF(src_w * 0.48, src_h * 0.90), src_w * 0.70, QColor(180, 205, 225, 80)),
            (QPointF(src_w * 0.72, src_h * 0.55), src_w * 0.36, QColor(255, 255, 255, 140)),
        ]
    qp.setPen(Qt.PenStyle.NoPen)
    for center, radius, color in orbs:
        rg = QRadialGradient(center, radius)
        rg.setColorAt(0.0, color)
        mid = QColor(color)
        mid.setAlpha(max(0, color.alpha() // 3))
        rg.setColorAt(0.55, mid)
        clear = QColor(color)
        clear.setAlpha(0)
        rg.setColorAt(1.0, clear)
        qp.setBrush(rg)
        qp.drawEllipse(center, radius, radius)

    sheen = QLinearGradient(0, 0, 0, src_h * 0.50)
    sheen.setColorAt(0.0, QColor(255, 255, 255, 70 if dark else 140))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    qp.fillRect(0, 0, src_w, int(src_h * 0.50), sheen)
    qp.end()

    return QPixmap.fromImage(
        img.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def _paint_home_glass(
    widget: QWidget,
    *,
    radius: float,
    dark: bool,
    hover: bool = False,
    accent: bool = False,
    lift: float = 0.0,
    lift_room: float = 0.0,
    shadow_room: float = 8.0,
    side_pad: float = 5.0,
) -> None:
    """Frost plate for HOME — soft shadow, translucent fill, specular rim.

    Lift/shadow stay inside ``widget.rect()`` — Qt clips paint outside the
    widget, which was cutting the raised card and drop shadow.
    """
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    full = QRectF(widget.rect())
    if full.width() < 4 or full.height() < 4:
        return

    # Reserved air: top for lift, bottom for shadow — plate never leaves full.
    top_room = max(0.0, float(lift_room))
    bot_room = max(6.0, float(shadow_room))
    side = max(3.0, float(side_pad))
    ly = min(max(0.0, float(lift)), max(0.0, top_room - 1.0))

    # Constant-size plate: rise into top_room; bottom inset grows by the same.
    plate_top = side * 0.4 + top_room - ly
    plate_bot = bot_room + ly
    r = full.adjusted(side, plate_top, -side, -plate_bot)
    if r.width() < 8 or r.height() < 8:
        r = full.adjusted(4, 4, -4, -6)

    shadow_scale = 1.0 if dark else 0.40
    glow = 1.45 if hover else 1.0
    # Soft contact shadow under the plate — clamped inside the widget.
    inner = full.adjusted(1.0, 1.0, -1.0, -1.0)
    for grow, alpha in ((5.0 + ly * 0.4, 24), (2.8 + ly * 0.25, 42), (1.0, 58)):
        sr = QRectF(r).adjusted(-1.5, 2.0 + ly * 0.15, 1.5, 3.0 + grow + ly * 0.35)
        sr = sr.intersected(inner)
        if sr.width() < 4 or sr.height() < 4:
            continue
        sp = QPainterPath()
        sp.addRoundedRect(sr, radius + 1.0, radius + 1.0)
        p.fillPath(sp, QColor(0, 0, 0, int(alpha * shadow_scale * glow)))

    rad = min(float(radius), r.width() * 0.5, r.height() * 0.5)
    path = QPainterPath()
    path.addRoundedRect(r, rad, rad)

    fill = QLinearGradient(r.topLeft(), r.bottomLeft())
    if dark:
        # Airier glass — backdrop orbs read through (not a solid slab).
        fill.setColorAt(0.0, QColor(255, 255, 255, 58 if hover else 42))
        fill.setColorAt(0.22, QColor(56, 64, 76, 88 if hover else 72))
        fill.setColorAt(0.62, QColor(28, 34, 42, 102 if hover else 88))
        fill.setColorAt(1.0, QColor(14, 18, 24, 120 if hover else 105))
        rim_a = 110 if hover else 78
        spec_a = 150 if hover else 115
        sheen0 = QColor(255, 255, 255, 100 if hover else 78)
    else:
        fill.setColorAt(0.0, QColor(255, 255, 255, 200 if hover else 175))
        fill.setColorAt(0.40, QColor(250, 252, 255, 150))
        fill.setColorAt(1.0, QColor(230, 236, 244, 165))
        rim_a = 210 if hover else 175
        spec_a = 235 if hover else 200
        sheen0 = QColor(255, 255, 255, 160 if hover else 130)
    p.fillPath(path, fill)

    if accent or hover:
        wash = QLinearGradient(r.topLeft(), r.bottomRight())
        wash.setColorAt(0.0, QColor(255, 90, 31, 36 if dark else 26))
        wash.setColorAt(0.55, QColor(255, 90, 31, 0))
        wash.setColorAt(1.0, QColor(255, 90, 31, 22 if dark else 16))
        p.fillPath(path, wash)

    sheen = QLinearGradient(r.topLeft(), QRectF(r).center())
    sheen.setColorAt(0.0, sheen0)
    sheen.setColorAt(0.55, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)

    if hover or accent:
        p.setPen(QPen(QColor(255, 140, 90, 160 if dark else 120), 1.2))
    else:
        p.setPen(QPen(QColor(255, 255, 255, rim_a), 1.05))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, spec_a), 1.25))
    p.drawLine(int(r.left() + rad), int(r.top() + 1), int(r.right() - rad), int(r.top() + 1))


class HomeGlassFrame(QFrame):
    """Painted frost shell used by logo plate, studio cards, drop zone."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = 22.0,
        dark: bool = True,
        lift_room: float = 0.0,
        shadow_room: float = 8.0,
        side_pad: float = 5.0,
    ) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self._dark = bool(dark)
        self._hover = False
        self._accent = False
        self._lift = 0.0
        self._lift_room = float(lift_room)
        self._shadow_room = float(shadow_room)
        self._side_pad = float(side_pad)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        set_glass_dark(self, self._dark)

    def set_dark(self, dark: bool) -> None:
        dark = bool(dark)
        if dark == self._dark:
            return
        self._dark = dark
        set_glass_dark(self, dark)
        self.update()

    def set_accent(self, on: bool) -> None:
        on = bool(on)
        if on == self._accent:
            return
        self._accent = on
        self.update()

    def set_lift(self, px: float) -> None:
        px = max(0.0, float(px))
        if abs(px - self._lift) < 0.05:
            return
        self._lift = px
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        _paint_home_glass(
            self,
            radius=self._radius,
            dark=self._dark,
            hover=self._hover,
            accent=self._accent,
            lift=self._lift,
            lift_room=self._lift_room,
            shadow_room=self._shadow_room,
            side_pad=self._side_pad,
        )


class HomeIconBadge(QWidget):
    """Circular glass icon — glow ring + Material glyph."""

    def __init__(
        self,
        icon_name: str,
        *,
        dark: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._dark = bool(dark)
        self._hover = False
        self.setFixedSize(72, 72)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    def set_hover(self, on: bool) -> None:
        on = bool(on)
        if on == self._hover:
            return
        self._hover = on
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        full = QRectF(self.rect())
        c = full.center()
        # Soft accent halo
        halo_r = 34.0 if self._hover else 30.0
        rg = QRadialGradient(c, halo_r)
        a0 = 70 if self._hover else 42
        rg.setColorAt(0.0, QColor(255, 90, 31, a0))
        rg.setColorAt(0.55, QColor(255, 90, 31, a0 // 3))
        rg.setColorAt(1.0, QColor(255, 90, 31, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rg)
        p.drawEllipse(c, halo_r, halo_r)

        disc_r = 26.0
        disc = QRectF(c.x() - disc_r, c.y() - disc_r, disc_r * 2, disc_r * 2)
        glass = QLinearGradient(disc.topLeft(), disc.bottomLeft())
        if self._dark:
            glass.setColorAt(0.0, QColor(255, 255, 255, 55))
            glass.setColorAt(0.45, QColor(40, 46, 56, 140))
            glass.setColorAt(1.0, QColor(18, 22, 28, 170))
            rim = QColor(255, 255, 255, 90 if self._hover else 60)
        else:
            glass.setColorAt(0.0, QColor(255, 255, 255, 230))
            glass.setColorAt(1.0, QColor(230, 236, 242, 210))
            rim = QColor(255, 255, 255, 200)
        path = QPainterPath()
        path.addEllipse(disc)
        p.fillPath(path, glass)
        p.setPen(QPen(rim, 1.1))
        p.drawPath(path)
        # Specular arc
        p.setPen(QPen(QColor(255, 255, 255, 120 if self._dark else 200), 1.2))
        p.drawArc(disc.adjusted(3, 3, -3, -3), 40 * 16, 100 * 16)

        g = glyph(self._icon_name) if ensure_material_icons() else ""
        if g:
            p.setFont(icon_font(30))
            p.setPen(QColor("#ff5a1f"))
            p.drawText(full, int(Qt.AlignmentFlag.AlignCenter), g)


class HomeStudioCard(HomeGlassFrame):
    """Clickable glass studio tile — centered icon · title · tag · CTA."""

    _LIFT_PX = 6.0
    _LIFT_MS = 240
    _LIFT_ROOM = 8.0
    _SHADOW_ROOM = 12.0
    _SIDE_PAD = 6.0
    _INNER = 16

    def __init__(
        self,
        *,
        title: str,
        blurb: str,
        icon_name: str,
        on_click: Callable[[], None],
        dark: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            radius=22.0,
            dark=dark,
            lift_room=self._LIFT_ROOM,
            shadow_room=self._SHADOW_ROOM,
            side_pad=self._SIDE_PAD,
        )
        self.setObjectName("homeStudioCard")
        self._on_click = on_click
        inn = self._INNER
        self._base_margins = (
            int(self._SIDE_PAD + inn),
            int(self._LIFT_ROOM + inn),
            int(self._SIDE_PAD + inn),
            int(self._SHADOW_ROOM + inn - 2),
        )
        self._lift_anim: QVariantAnimation | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 5-up row still has side air on ≥1280; keep titles (Texture / Mesh) unclipped.
        self.setFixedWidth(220)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(*self._base_margins)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        badge = HomeIconBadge(icon_name, dark=dark)
        self._icon_lab = badge
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title_src = title
        self._blurb_src = blurb
        self._cta_src = "Open  →"

        t = QLabel(title)
        t.setObjectName("homeCardTitle")
        t.setFont(app_font(15, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t.setProperty("mstn_i18n_src", title)

        b = QLabel(blurb)
        b.setObjectName("homeCardBlurb")
        b.setWordWrap(True)
        b.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        b.setFont(app_font(11, QFont.Weight.Medium))
        b.setProperty("mstn_i18n_src", blurb)

        cta = QLabel(self._cta_src)
        cta.setObjectName("homeCardCta")
        cta.setFont(app_font(11, QFont.Weight.DemiBold))
        cta.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        cta.setProperty("mstn_i18n_src", self._cta_src)

        self._title_lab = t
        self._blurb_lab = b
        self._cta_lab = cta

        lay.addWidget(t)
        lay.addWidget(b)
        lay.addSpacing(4)
        lay.addWidget(cta)

    def retranslate(self) -> None:
        from .i18n import t

        self._title_lab.setText(t(self._title_src))
        self._blurb_lab.setText(t(self._blurb_src))
        self._cta_lab.setText(t(self._cta_src))
        self._title_lab.setFont(app_font(15, QFont.Weight.Bold))
        self._blurb_lab.setFont(app_font(11, QFont.Weight.Medium))
        self._cta_lab.setFont(app_font(11, QFont.Weight.DemiBold))

    def set_dark(self, dark: bool) -> None:
        super().set_dark(dark)
        self._icon_lab.set_dark(dark)

    def _apply_lift_amount(self, lift: float) -> None:
        lay = self.layout()
        if lay is None:
            return
        l, t, r, b = self._base_margins
        li = int(round(max(0.0, float(lift))))
        lay.setContentsMargins(l, t - li, r, b + li)

    def _animate_lift(self, target: float) -> None:
        target = max(0.0, float(target))
        prev = self._lift_anim
        if prev is not None:
            prev.stop()
            self._lift_anim = None
        start = float(self._lift)
        if abs(start - target) < 0.05:
            self.set_lift(target)
            self._apply_lift_amount(target)
            return
        # Low-end: snap lift — QVariantAnimation×5 cards was HOME hover stutter.
        try:
            from ..util.hw import prefer_instant_panels

            if prefer_instant_panels():
                self.set_lift(target)
                self._apply_lift_amount(target)
                self._hover = target > 0.0
                self.update()
                return
        except Exception:
            pass
        anim = QVariantAnimation(self)
        anim.setDuration(self._LIFT_MS)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if target > start else QEasingCurve.Type.InOutCubic
        )

        rising = target > start

        def _tick(value: object) -> None:
            lift = float(value)
            self.set_lift(lift)
            self._apply_lift_amount(lift)
            if rising:
                self._hover = True
            elif lift < 0.8:
                self._hover = False
            self.update()

        def _done() -> None:
            if self._lift_anim is anim:
                self._lift_anim = None
            if target <= 0.0:
                self._hover = False
                self.update()

        anim.valueChanged.connect(_tick)
        anim.finished.connect(_done)
        self._lift_anim = anim
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._icon_lab.set_hover(True)
        self.raise_()
        self._animate_lift(self._LIFT_PX)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._icon_lab.set_hover(False)
        # Keep hover tint until lift eases down (see _animate_lift).
        self._animate_lift(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._on_click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class HomeDropZone(HomeGlassFrame):
    """Glass drop target — title + supported extensions."""

    def __init__(
        self,
        on_drop: Callable[[list[Path]], None],
        *,
        dark: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, radius=18.0, dark=dark, shadow_room=10.0, side_pad=6.0)
        self._on_drop = on_drop
        self._drag_over = False
        self.setObjectName("homeDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(72)
        self.setMaximumWidth(860)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setObjectName("homeDropIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(28, 28)
        icon.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if ensure_material_icons() and glyph("upload_file"):
            icon.setFont(icon_font(18))
            icon.setText(glyph("upload_file"))
        head.addWidget(icon)

        self._drop_title_src = "Drop files"
        title = QLabel(self._drop_title_src)
        title.setObjectName("homeDropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(app_font(14, QFont.Weight.DemiBold))
        title.setProperty("mstn_i18n_src", self._drop_title_src)
        self._drop_title_lab = title
        head.addWidget(title)

        # Short hint — full extension list was visually noisy.
        exts = QLabel(".trainzmesh  ·  .fbx  ·  .wav  ·  .cdp  ·  .mtzs  ·  …")
        exts.setObjectName("homeDropTypes")
        exts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exts.setFont(app_font(11, QFont.Weight.Medium))

        lay.addLayout(head)
        lay.addWidget(exts)

    def retranslate(self) -> None:
        from .i18n import t

        self._drop_title_lab.setText(t(self._drop_title_src))
        self._drop_title_lab.setFont(app_font(14, QFont.Weight.DemiBold))

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self._hover = active
        self._accent = active
        self.setProperty("dragOver", active)
        sty = self.style()
        sty.unpolish(self)
        sty.polish(self)
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self._on_drop(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._drag_over:
            color = QColor("#ff5a1f")
            color.setAlpha(200)
        else:
            color = QColor("#98989d")
            color.setAlpha(120 if self._dark else 90)
        pen = QPen(color)
        pen.setWidthF(1.6)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([5.0, 4.5])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = self.rect().adjusted(10, 8, -10, -12)
        painter.drawRoundedRect(r, 14, 14)


class HomePage(QFrame):
    """HOME root — glassian blur stage + frost studio hub."""

    def __init__(
        self,
        *,
        logo: QLabel,
        on_mesh: Callable[[], None],
        on_sounds: Callable[[], None],
        on_engine: Callable[[], None],
        on_assets: Callable[[], None],
        on_texmesh: Callable[[], None],
        on_drop: Callable[[list[Path]], None],
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self._frost: QPixmap | None = None
        self._frost_key: tuple[int, int, str] | None = None
        self._glass_kids: list[HomeGlassFrame] = []
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        lay.setContentsMargins(40, 28, 40, 24)

        dark = self._theme != "light"

        # Brand mark floats — no heavy glass plate (keeps hero clean).
        logo.setObjectName("sideLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._home_logo = logo

        self._brand_src = "MSTN Trainz Studio"
        self._sub_src = "Meshes · sounds · engine · assets · maps"
        self._copy_src = "Copyright MSTN Production"

        brand = QLabel(self._brand_src)
        brand.setObjectName("homeBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFont(app_font(30, QFont.Weight.Bold))
        brand.setProperty("mstn_i18n_src", self._brand_src)
        self._brand_lab = brand

        sub = QLabel(self._sub_src)
        sub.setObjectName("homeSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(app_font(12, QFont.Weight.Medium))
        sub.setProperty("mstn_i18n_src", self._sub_src)
        self._sub_lab = sub

        card_host = QWidget()
        card_host.setObjectName("homeCardHost")
        card_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        card_host.setAutoFillBackground(False)
        row = QHBoxLayout(card_host)
        row.setContentsMargins(16, 20, 16, 22)
        row.setSpacing(16)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards = (
            (
                "Mesh Studio",
                "Mesh · FBX · lamps",
                "layers",
                on_mesh,
            ),
            (
                "Sounds Studio",
                "Loop · waveform · export",
                "graphic_eq",
                on_sounds,
            ),
            (
                "Engine Tuner",
                "Curves · throttle · sim",
                "tune",
                on_engine,
            ),
            (
                "Assets Tools",
                "CDP · config · KUID",
                "inventory_2",
                on_assets,
            ),
            (
                "Texture / Mesh",
                "Maps · LM · materials",
                "texture",
                on_texmesh,
            ),
        )
        self._studio_cards: list[HomeStudioCard] = []
        for title, blurb, icon_name, on_click in cards:
            card = HomeStudioCard(
                title=title,
                blurb=blurb,
                icon_name=icon_name,
                on_click=on_click,
                dark=dark,
            )
            self._glass_kids.append(card)
            self._studio_cards.append(card)
            row.addWidget(card)

        set_glass_dark(card_host, dark)
        attach_hover_bubble(
            card_host,
            self._studio_cards,
            radius=24.0,
            pad=3,
            hide_ms=140,
            pop_on_arrive=False,
            slide_ms=400,
            warm=True,
        )
        self._card_host = card_host

        drop = HomeDropZone(on_drop, dark=dark)
        self._glass_kids.append(drop)
        self._drop_zone = drop

        copy = QLabel(self._copy_src)
        copy.setObjectName("homeCopy")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy.setFont(app_font(10, QFont.Weight.Normal))
        copy.setProperty("mstn_i18n_src", self._copy_src)
        self._copy_lab = copy

        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(brand)
        lay.addWidget(sub)
        lay.addSpacing(10)
        lay.addWidget(card_host, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(drop, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(copy)

    def retranslate(self) -> None:
        """Apply current language to HOME chrome (cards, drop zone, brand)."""
        from .i18n import t

        self._brand_lab.setText(t(self._brand_src))
        self._sub_lab.setText(t(self._sub_src))
        self._copy_lab.setText(t(self._copy_src))
        self._brand_lab.setFont(app_font(30, QFont.Weight.Bold))
        self._sub_lab.setFont(app_font(12, QFont.Weight.Medium))
        self._copy_lab.setFont(app_font(10, QFont.Weight.Normal))
        for card in self._studio_cards:
            card.retranslate()
        self._drop_zone.retranslate()

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        if mode == self._theme:
            return
        self._theme = mode
        self._frost = None
        self._frost_key = None
        dark = mode != "light"
        for kid in self._glass_kids:
            kid.set_dark(dark)
        host = getattr(self, "_card_host", None)
        if host is not None:
            set_glass_dark(host, dark)
            bubble = getattr(host, "_hover_bubble", None)
            if bubble is not None:
                set_glass_dark(bubble, dark)
                bubble.update()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._frost = None
        self._frost_key = None

    def _ensure_frost(self) -> QPixmap:
        key = (self.width(), self.height(), self._theme)
        if self._frost is not None and self._frost_key == key:
            return self._frost
        pal = palette(self._theme)
        self._frost = _glass_blur_backdrop(
            self.width(),
            self.height(),
            dark=self._theme != "light",
            accent=QColor(pal.accent),
        )
        self._frost_key = key
        return self._frost

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pm = self._ensure_frost()
        if not pm.isNull():
            painter.drawPixmap(self.rect(), pm)
        else:
            painter.fillRect(self.rect(), QColor(palette(self._theme).bg))
        veil = QLinearGradient(QPointF(0, 0), QPointF(0, self.height()))
        dark = self._theme != "light"
        if dark:
            veil.setColorAt(0.0, QColor(255, 255, 255, 14))
            veil.setColorAt(0.45, QColor(12, 14, 18, 36))
            veil.setColorAt(1.0, QColor(0, 0, 0, 70))
        else:
            veil.setColorAt(0.0, QColor(255, 255, 255, 80))
            veil.setColorAt(0.55, QColor(255, 255, 255, 28))
            veil.setColorAt(1.0, QColor(220, 226, 232, 55))
        painter.fillRect(QRectF(self.rect()), veil)


def build_home_page(
    *,
    logo: QLabel,
    on_mesh: Callable[[], None],
    on_sounds: Callable[[], None],
    on_engine: Callable[[], None],
    on_assets: Callable[[], None],
    on_texmesh: Callable[[], None],
    on_drop: Callable[[list[Path]], None],
    theme_mode: str = "dark",
) -> HomePage:
    return HomePage(
        logo=logo,
        on_mesh=on_mesh,
        on_sounds=on_sounds,
        on_engine=on_engine,
        on_assets=on_assets,
        on_texmesh=on_texmesh,
        on_drop=on_drop,
        theme_mode=theme_mode,
    )
