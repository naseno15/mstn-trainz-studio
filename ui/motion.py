"""Lightweight Qt motion helpers — no extra deps."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QHelpEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QWidget,
)

# Pill / hover-bubble travel — deliberately soft (was ~200ms + OutBack snap).
PILL_SLIDE_MS = 420
HOVER_BUBBLE_MS = 440
SCRUB_LERP = 0.16  # per 8ms tick — lower = silkier finger-follow


def _ensure_opacity(w: QWidget) -> QGraphicsOpacityEffect:
    eff = w.graphicsEffect()
    if isinstance(eff, QGraphicsOpacityEffect):
        return eff
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(1.0)
    w.setGraphicsEffect(eff)
    return eff


def fade_widget(w: QWidget, start: float, end: float, ms: int = 220) -> QPropertyAnimation:
    """Soft opacity fade on any widget."""
    eff = _ensure_opacity(w)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade_stack_to(stack: QStackedWidget, index: int, ms: int = 220) -> None:
    """Switch stack page.

    ponytail: never QGraphicsOpacityEffect on a stack that hosts QOpenGLWidget
    or floating chrome siblings — opacity redirect buries top/bottom bars and
    can freeze the GL widget (see HANDOFF). Instant swap is enough.
    """
    del ms  # API kept for call sites
    if index < 0 or index >= stack.count():
        return
    # drop leftover effect from older builds that faded the whole stack
    if stack.graphicsEffect() is not None:
        stack.setGraphicsEffect(None)
    stack.setCurrentIndex(index)


def fade_stack_page(stack: QStackedWidget, index: int, ms: int = 380) -> None:
    """Soft crossfade between form / side-panel stack pages (never GL hosts).

    Fades the *page widgets*, not the QStackedWidget itself — safe for frost
    sidebars. Call sites with OpenGL must keep using ``fade_stack_to``.
    """
    if index < 0 or index >= stack.count():
        return
    if index == stack.currentIndex():
        return
    prev_anim = getattr(stack, "_page_fade", None)
    if prev_anim is not None:
        prev_anim.stop()

    def _clear_fx(w: QWidget | None) -> None:
        if w is not None and w.graphicsEffect() is not None:
            w.setGraphicsEffect(None)

    # Interrupt mid-fade — never leave a page stuck at opacity 0.
    for i in range(stack.count()):
        _clear_fx(stack.widget(i))

    prev = stack.currentWidget()
    half = max(140, int(ms) // 2)

    def _enter() -> None:
        stack.setCurrentIndex(index)
        _clear_fx(prev)
        nxt = stack.currentWidget()
        if nxt is None:
            stack._page_fade = None  # type: ignore[attr-defined]
            return
        anim = fade_widget(nxt, 0.0, 1.0, half)
        stack._page_fade = anim  # type: ignore[attr-defined]

        def _done() -> None:
            _clear_fx(nxt)
            if getattr(stack, "_page_fade", None) is anim:
                stack._page_fade = None  # type: ignore[attr-defined]

        anim.finished.connect(_done)

    if prev is None:
        _enter()
        return
    out = fade_widget(prev, 1.0, 0.0, half)
    stack._page_fade = out  # type: ignore[attr-defined]
    out.finished.connect(_enter)


def pulse_checkbox(cb: QAbstractButton, ms: int = 160) -> None:
    """Brief scale flash via geometry nudge (stylesheet-friendly)."""
    geo = cb.geometry()
    if geo.width() < 8 or geo.height() < 8:
        return
    mid = QRect(geo)
    mid.adjust(-2, -1, 2, 1)
    anim = QPropertyAnimation(cb, b"geometry", cb)
    anim.setDuration(ms)
    anim.setKeyValueAt(0.0, geo)
    anim.setKeyValueAt(0.45, mid)
    anim.setKeyValueAt(1.0, geo)
    anim.setEasingCurve(QEasingCurve.Type.OutBack)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def animate_nav_check(btn: QAbstractButton, checked: bool, ms: int = 180) -> None:
    """Springy width / opacity nudge when a bottom-nav pill is checked."""
    eff = _ensure_opacity(btn)
    group = QParallelAnimationGroup(btn)

    op = QPropertyAnimation(eff, b"opacity", btn)
    op.setDuration(ms)
    op.setStartValue(0.72 if checked else 1.0)
    op.setEndValue(1.0)
    op.setEasingCurve(QEasingCurve.Type.OutCubic)
    group.addAnimation(op)

    # width hint: grow slightly when checked
    base_w = max(btn.sizeHint().width(), btn.width(), 88)
    target_w = base_w + (10 if checked else 0)
    btn.setMinimumWidth(target_w if checked else 88)
    w_anim = QPropertyAnimation(btn, b"minimumWidth", btn)
    w_anim.setDuration(ms)
    w_anim.setStartValue(btn.minimumWidth())
    w_anim.setEndValue(target_w if checked else 88)
    w_anim.setEasingCurve(QEasingCurve.Type.OutBack)
    group.addAnimation(w_anim)

    group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def stop_slide(widget: QWidget) -> None:
    """Kill an in-flight slide_to so scrub can take over geometry."""
    anim = getattr(widget, "_slide_anim", None)
    if anim is not None:
        anim.stop()
        widget._slide_anim = None  # type: ignore[attr-defined]


def stop_pop(widget: QWidget) -> None:
    """Kill apple_pop geometry anim — must not fight slide_to across rows."""
    anim = getattr(widget, "_pop_anim", None)
    if anim is not None:
        anim.stop()
        widget._pop_anim = None  # type: ignore[attr-defined]


def slide_to(
    widget: QWidget,
    target: QRect,
    ms: int = PILL_SLIDE_MS,
    *,
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
) -> QPropertyAnimation:
    """Smooth geometry slide (nav / PBR pill indicator)."""
    stop_pop(widget)
    stop_slide(widget)
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(ms)
    anim.setStartValue(widget.geometry())
    anim.setEndValue(target)
    anim.setEasingCurve(easing)
    widget._slide_anim = anim  # type: ignore[attr-defined]

    def _clear() -> None:
        if getattr(widget, "_slide_anim", None) is anim:
            widget._slide_anim = None  # type: ignore[attr-defined]

    anim.finished.connect(_clear)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


class HoverBubble(QWidget):
    """Translucent glass bubble — hover follower (selected stays orange AccentPill)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = 14.0,
        warm: bool = False,
    ) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self._warm = bool(warm)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if r.width() < 2 or r.height() < 2:
            return
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        dark = _glass_dark_of(self)
        # Soft frosted bubble — never solid orange (selection keeps AccentPill).
        fill = QLinearGradient(r.topLeft(), r.bottomLeft())
        if self._warm:
            if dark:
                fill.setColorAt(0.0, QColor(255, 170, 120, 70))
                fill.setColorAt(0.40, QColor(255, 255, 255, 42))
                fill.setColorAt(1.0, QColor(255, 90, 31, 28))
                rim = QColor(255, 180, 140, 110)
                inner_rim = QColor(255, 255, 255, 40)
            else:
                fill.setColorAt(0.0, QColor(255, 140, 90, 48))
                fill.setColorAt(0.45, QColor(255, 255, 255, 70))
                fill.setColorAt(1.0, QColor(255, 90, 31, 22))
                rim = QColor(255, 120, 70, 90)
                inner_rim = QColor(255, 255, 255, 120)
        elif dark:
            fill.setColorAt(0.0, QColor(255, 255, 255, 52))
            fill.setColorAt(0.45, QColor(255, 255, 255, 30))
            fill.setColorAt(1.0, QColor(255, 255, 255, 16))
            rim = QColor(255, 255, 255, 72)
            inner_rim = QColor(255, 255, 255, 30)
        else:
            fill.setColorAt(0.0, QColor(0, 0, 0, 28))
            fill.setColorAt(0.45, QColor(0, 0, 0, 18))
            fill.setColorAt(1.0, QColor(0, 0, 0, 10))
            rim = QColor(0, 0, 0, 40)
            inner_rim = QColor(255, 255, 255, 90)
        p.fillPath(path, fill)
        p.setPen(QPen(rim, 1.0))
        p.drawPath(path)
        inner = r.adjusted(1.2, 1.2, -1.2, -1.2)
        if inner.width() > 4 and inner.height() > 4:
            ip = QPainterPath()
            ip.addRoundedRect(inner, max(2.0, self._radius - 1.5), max(2.0, self._radius - 1.5))
            p.setPen(QPen(inner_rim, 1.0))
            p.drawPath(ip)


class HoverBubbleController(QObject):
    """Move a HoverBubble under the hovered item — smooth slide, including across rows."""

    def __init__(
        self,
        host: QWidget,
        buttons: list[QWidget] | tuple[QWidget, ...],
        bubble: HoverBubble,
        *,
        pad: int = 2,
        hide_ms: int = 50,
        pop_on_arrive: bool = True,
        slide_ms: int | None = None,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._buttons = list(buttons)
        self._bubble = bubble
        self._pad = int(pad)
        self._pop_on_arrive = bool(pop_on_arrive)
        self._slide_ms = int(slide_ms) if slide_ms is not None else HOVER_BUBBLE_MS
        self._current: QWidget | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(max(0, int(hide_ms)))
        self._hide_timer.timeout.connect(self._hide_now)
        for b in self._buttons:
            b.installEventFilter(self)
        host.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if obj in self._buttons:
            if et == QEvent.Type.Enter:
                self._hide_timer.stop()
                self._move_to(obj)
            elif et == QEvent.Type.Leave:
                self._hide_timer.start()
        elif obj is self._host and et == QEvent.Type.Leave:
            # Leaving the bar entirely — cancel if still over a child.
            if self._host.rect().contains(self._host.mapFromGlobal(QCursor.pos())):
                return False
            self._hide_timer.start()
        return False

    def hide_now(self) -> None:
        self._hide_timer.stop()
        self._hide_now()

    def _hide_now(self) -> None:
        self._current = None
        stop_pop(self._bubble)
        stop_slide(self._bubble)
        self._bubble.hide()

    def _target_rect(self, btn: QWidget) -> QRect:
        """Map item rect into host coords — works for grid rows, not only peers."""
        top_left = btn.mapTo(self._host, QPoint(0, 0))
        return QRect(top_left, btn.size()).adjusted(
            -self._pad, -self._pad, self._pad, self._pad
        )

    def _move_to(self, btn: QWidget) -> None:
        if getattr(self._host, "_drag", False):
            return
        target = self._target_rect(btn)
        if target.width() < 4 or target.height() < 4:
            return
        same = self._current is btn and self._bubble.isVisible()
        self._current = btn
        # Kill in-flight pop so row jumps never snap from a mid-pop rect.
        stop_pop(self._bubble)
        was_visible = self._bubble.isVisible() and self._bubble.width() >= 4
        self._bubble.show()
        # Keep orange selector under bubble; buttons stay on top via host stack.
        self._bubble.raise_()
        accent = getattr(self._host, "_pill", None)
        if accent is not None:
            accent.lower()
            self._bubble.raise_()
        for b in self._buttons:
            b.raise_()
        if same:
            return
        # Distance-aware duration — tall row jumps get a bit more time, still one slide.
        dist = 0.0
        if was_visible:
            c0 = self._bubble.geometry().center()
            c1 = target.center()
            dist = ((c0.x() - c1.x()) ** 2 + (c0.y() - c1.y()) ** 2) ** 0.5
        ms = self._slide_ms
        if dist > 120:
            ms = min(720, int(self._slide_ms + dist * 0.35))
        if not was_visible:
            # First show / after hide: ease in from a slightly smaller rect (no teleport).
            start = QRect(target)
            start.adjust(10, 8, -10, -8)
            if start.width() < 8 or start.height() < 8:
                start = QRect(target)
            self._bubble.setGeometry(start)
        anim = slide_to(
            self._bubble,
            target,
            ms,
            easing=QEasingCurve.Type.OutCubic,
        )
        if self._pop_on_arrive:
            anim.finished.connect(lambda: apple_pop_pill(self._bubble, ms=280))


def attach_hover_bubble(
    host: QWidget,
    buttons: list[QWidget] | tuple[QWidget, ...],
    *,
    radius: float = 14.0,
    pad: int = 2,
    hide_ms: int = 50,
    pop_on_arrive: bool = True,
    slide_ms: int | None = None,
    warm: bool = False,
) -> HoverBubble:
    """Wire translucent hover bubble under menu items (orange pill = selection)."""
    bubble = HoverBubble(host, radius=radius, warm=warm)
    ctl = HoverBubbleController(
        host,
        buttons,
        bubble,
        pad=pad,
        hide_ms=hide_ms,
        pop_on_arrive=pop_on_arrive,
        slide_ms=slide_ms,
    )
    host._hover_bubble = bubble  # type: ignore[attr-defined]
    host._hover_ctl = ctl  # type: ignore[attr-defined]
    return bubble


def short_glass_tip(tip: str) -> str:
    """Keep tip label short — first clause before an em/en dash."""
    t = (tip or "").strip()
    if not t:
        return ""
    for sep in (" — ", " – ", " - "):
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    return t


def _glass_dark_of(widget: QWidget | None) -> bool:
    """Resolve glassDark from widget, then ancestors (default dark)."""
    w = widget
    while w is not None:
        val = w.property("glassDark")
        if isinstance(val, bool):
            return val
        w = w.parentWidget()
    return True


class GlassTipBubble(QWidget):
    """Glassmorphism text tip with a caret pointing at the hovered icon."""

    _PAD_X = 12
    _PAD_Y = 7
    _CARET = 7
    _RADIUS = 10.0
    # Cap width so long glossary tips wrap to ~2–3 lines (was one giant strip).
    _MAX_INNER = 260
    _TEXT_FLAGS = int(
        Qt.AlignmentFlag.AlignLeft
        | Qt.AlignmentFlag.AlignVCenter
        | Qt.TextFlag.TextWordWrap
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._caret_down = True
        self._font = self._tip_font()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    @staticmethod
    def _tip_font() -> QFont:
        # Smaller + Medium vs UI 13px DemiBold buttons — tip is chrome, not a header.
        try:
            from .i18n import ui_font

            return ui_font(point_size=9, weight=QFont.Weight.Medium)
        except Exception:
            f = QFont()
            f.setFamilies(["Noto Sans", "Segoe UI"])
            f.setPointSize(9)
            f.setWeight(QFont.Weight.Medium)
            return f

    def set_tip(self, text: str, *, caret_down: bool = True) -> None:
        self._font = self._tip_font()
        self._text = short_glass_tip(text)
        self._caret_down = caret_down
        fm = QFontMetrics(self._font)
        natural = max(24, fm.horizontalAdvance(self._text))
        inner_w = min(natural, self._MAX_INNER)
        br = fm.boundingRect(QRect(0, 0, inner_w, 10_000), self._TEXT_FLAGS, self._text)
        tw = max(24, min(br.width(), self._MAX_INNER))
        th = max(fm.height(), br.height())
        self.resize(
            tw + self._PAD_X * 2,
            th + self._PAD_Y * 2 + self._CARET,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dark = _glass_dark_of(self)
        caret = self._CARET
        if self._caret_down:
            body = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - caret - 0.5)
        else:
            body = QRectF(0.5, caret + 0.5, self.width() - 1.0, self.height() - caret - 1.0)
        path = QPainterPath()
        path.addRoundedRect(body, self._RADIUS, self._RADIUS)
        cx = self.width() * 0.5
        tri = QPainterPath()
        if self._caret_down:
            y0 = body.bottom() - 1.0
            tri.moveTo(cx - caret, y0)
            tri.lineTo(cx, self.height() - 0.5)
            tri.lineTo(cx + caret, y0)
            tri.closeSubpath()
        else:
            y1 = body.top() + 1.0
            tri.moveTo(cx - caret, y1)
            tri.lineTo(cx, 0.5)
            tri.lineTo(cx + caret, y1)
            tri.closeSubpath()
        path = path.united(tri)

        fill = QLinearGradient(body.topLeft(), body.bottomLeft())
        if dark:
            fill.setColorAt(0.0, QColor(36, 40, 48, 220))
            fill.setColorAt(0.55, QColor(28, 32, 40, 210))
            fill.setColorAt(1.0, QColor(22, 26, 34, 200))
            rim = QColor(255, 255, 255, 70)
            ink = QColor(255, 255, 255, 235)
        else:
            fill.setColorAt(0.0, QColor(255, 255, 255, 230))
            fill.setColorAt(0.55, QColor(248, 248, 250, 220))
            fill.setColorAt(1.0, QColor(240, 240, 244, 210))
            rim = QColor(0, 0, 0, 36)
            ink = QColor(28, 28, 30, 235)
        p.fillPath(path, fill)
        p.setPen(QPen(rim, 1.0))
        p.drawPath(path)
        p.setFont(self._font)
        p.setPen(ink)
        text_rect = body.adjusted(
            self._PAD_X - 0.5, self._PAD_Y - 0.5, -(self._PAD_X - 0.5), -(self._PAD_Y - 0.5)
        )
        p.drawText(text_rect.toRect(), self._TEXT_FLAGS, self._text)


# Capsule / scrub controls — host HoverBubble already covers them.
_SKIP_BUTTON_LIFT = frozenset(
    {
        "navBtn",
        "titleNavBtn",
        "navIconBtn",
        "segBtn",
        "sideTab",
        "pkgCrumbBtn",
        "meshInfoToggle",
        "panelEdgeBtn",
    }
)


def _qt_alive(w: QWidget | None) -> bool:
    """False when the C++ QWidget was already deleteLater'd."""
    if w is None:
        return False
    try:
        w.isVisible()
        return True
    except RuntimeError:
        return False


class ButtonHoverChrome(QObject):
    """App-wide hover chrome: glass tip · soft bubble · emboss lift (no layout shift)."""

    _TIP_MS = 160
    _HIDE_MS = 80
    _HL_PAD = 3
    _HL_MS = 280

    def __init__(self) -> None:
        super().__init__()
        self._btn: QWidget | None = None
        self._qt_tip_owner: QWidget | None = None
        self._installed = False
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(self._TIP_MS)
        self._tip_timer.timeout.connect(self._show_tip)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self._HIDE_MS)
        self._hide_timer.timeout.connect(self._hide_now)

    def install(self, app: QApplication) -> None:
        if self._installed:
            return
        app.installEventFilter(self)
        self._installed = True

    def set_tip(self, btn: QWidget, tip: str, *, highlight: bool = True) -> None:
        # Store English (or source) tip; translate at show time so Lang swap works.
        text = (tip or "").strip()
        if not text:
            return
        btn.setProperty("glassTip", text)
        btn.setProperty("glassTipHighlight", bool(highlight))
        btn.setToolTip("")  # suppress native Qt tip — we draw our own

    def clear(self) -> None:
        """Force-hide bubble/tip — call when buttons are rebuilt/destroyed."""
        self._tip_timer.stop()
        self._hide_timer.stop()
        self._qt_tip_owner = None
        self._hide_now()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        # Native QToolTip is a flat rect that fades in Qt's own style.
        # Every tooltip in the app uses the same caret bubble instead.
        if et == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            self._on_qt_tooltip(obj, event)
            return True
        if obj is self._qt_tip_owner and et in (
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.HideToParent,
            QEvent.Type.Wheel,
            QEvent.Type.MouseButtonPress,
        ):
            self._qt_tip_owner = None
            self._hide_tip_only()
        if not isinstance(obj, (QPushButton, QToolButton)):
            return False
        # Hide / destroy must clear chrome even if the button is already disabled.
        if et in (QEvent.Type.Hide, QEvent.Type.HideToParent, QEvent.Type.Destroy):
            if self._btn is obj or (
                self._btn is not None and not _qt_alive(self._btn)
            ):
                self.clear()
            return False
        if not obj.isEnabled() or not obj.isVisible():
            return False
        if et == QEvent.Type.Enter:
            self._on_enter(obj)
        elif et == QEvent.Type.Leave:
            self._on_leave(obj)
        elif et == QEvent.Type.MouseButtonPress:
            self._tip_timer.stop()
            self._hide_now()
        return False

    def _on_enter(self, btn: QWidget) -> None:
        self._hide_timer.stop()
        if self._btn is not None and self._btn is not btn:
            try:
                self._set_lift(self._btn, False)
            except RuntimeError:
                pass
        if not _qt_alive(btn):
            self.clear()
            return
        self._btn = btn
        # ponytail: QSS emboss only — never move button geometry (layout must stay still)
        self._set_lift(btn, True)
        self._show_highlight(btn)
        if self._tip_text(btn):
            if self._tip_visible():
                self._tip_timer.stop()
                self._show_tip()
            else:
                self._tip_timer.start()
        else:
            self._tip_timer.stop()
            self._hide_tip_only()

    def _on_leave(self, btn: QWidget) -> None:
        if self._btn is not btn:
            # Stale pointer after rebuild — still clear overlays.
            if self._btn is not None and not _qt_alive(self._btn):
                self.clear()
            return
        self._tip_timer.stop()
        try:
            self._set_lift(btn, False)
        except RuntimeError:
            pass
        self._hide_timer.start()

    def _tip_text(self, btn: QWidget) -> str:
        raw = str(btn.property("glassTip") or "")
        try:
            from .i18n import translate_tip

            raw = translate_tip(raw)
        except Exception:
            pass
        return short_glass_tip(raw)

    def _tip_visible(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        for win in app.topLevelWidgets():
            tip = getattr(win, "_icon_glass_tip", None)
            if isinstance(tip, GlassTipBubble) and tip.isVisible():
                return True
        return False

    def _host_covers(self, btn: QWidget) -> bool:
        """True when a nav HoverBubbleController already highlights this button."""
        p = btn.parentWidget()
        while p is not None:
            ctl = getattr(p, "_hover_ctl", None)
            if ctl is not None and btn in getattr(ctl, "_buttons", ()):
                return True
            p = p.parentWidget()
        return False

    def _want_highlight(self, btn: QWidget) -> bool:
        prop = btn.property("glassTipHighlight")
        if prop is False:
            return False
        return not self._host_covers(btn)

    def _can_lift(self, btn: QWidget) -> bool:
        if btn.objectName() in _SKIP_BUTTON_LIFT:
            return False
        if self._host_covers(btn):
            return False
        if btn.property("glassTipHighlight") is False:
            return False
        return True

    def _polish(self, btn: QWidget) -> None:
        style = btn.style()
        if style is not None:
            style.unpolish(btn)
            style.polish(btn)
        btn.update()

    def _set_lift(self, btn: QWidget | None, on: bool) -> None:
        """Emboss-only lift — never changes geometry / layout."""
        if btn is None:
            return
        if on and not self._can_lift(btn):
            return
        if bool(btn.property("chromeLift")) == on:
            return
        btn.setProperty("chromeLift", on)
        self._polish(btn)

    def _overlays(self, window: QWidget) -> tuple[HoverBubble, GlassTipBubble]:
        hl = getattr(window, "_icon_glass_hl", None)
        tip = getattr(window, "_icon_glass_tip", None)
        if not isinstance(hl, HoverBubble):
            hl = HoverBubble(window, radius=12.0)
            window._icon_glass_hl = hl  # type: ignore[attr-defined]
        if not isinstance(tip, GlassTipBubble):
            tip = GlassTipBubble(window)
            window._icon_glass_tip = tip  # type: ignore[attr-defined]
        return hl, tip

    def _btn_rect_in_window(self, btn: QWidget) -> QRect | None:
        window = btn.window()
        if window is None:
            return None
        br = QRect(btn.mapTo(window, QPoint(0, 0)), btn.size())
        if br.width() < 4 or br.height() < 4:
            return None
        return br

    def _soft_slide_bubble(self, bubble: QWidget, target: QRect, *, first: bool) -> None:
        """Ease bubble onto the button — soft OutCubic, no hard pop."""
        stop_slide(bubble)
        bubble.show()
        bubble.raise_()
        if first or bubble.width() < 4:
            # Arrive from slightly below (lift illusion) without moving the button.
            start = QRect(target)
            start.translate(0, 6)
            start.adjust(3, 2, -3, -2)
            if start.width() < 4 or start.height() < 4:
                start = QRect(target)
            bubble.setGeometry(start)
        slide_to(
            bubble,
            target,
            self._HL_MS,
            easing=QEasingCurve.Type.OutCubic,
        )

    def _show_highlight(self, btn: QWidget) -> None:
        window = btn.window()
        if window is None:
            return
        hl, _tip = self._overlays(window)
        dark = _glass_dark_of(btn)
        hl.setProperty("glassDark", dark)
        if not self._want_highlight(btn):
            stop_slide(hl)
            hl.hide()
            return
        br = self._btn_rect_in_window(btn)
        if br is None:
            return
        target = br.adjusted(-self._HL_PAD, -self._HL_PAD, self._HL_PAD, self._HL_PAD)
        first = not hl.isVisible() or hl.width() < 4
        self._soft_slide_bubble(hl, target, first=first)
        # Keep label above bubble; do not change geometry / layout.
        btn.raise_()

    def _show_tip(self) -> None:
        btn = self._btn
        if btn is None or not btn.isVisible():
            return
        text = self._tip_text(btn)
        if not text:
            self._hide_tip_only()
            return
        window = btn.window()
        if window is None:
            return
        _hl, tip = self._overlays(window)
        tip.setProperty("glassDark", _glass_dark_of(btn))
        br = self._btn_rect_in_window(btn)
        if br is None:
            return
        self._place_tip(window, tip, text, br)

    def _place_tip(self, window: QWidget, tip: GlassTipBubble, text: str, anchor: QRect) -> None:
        """Pop the bubble out of the anchor. Never morph size while sliding sideways."""
        tip.setProperty("glassDark", _glass_dark_of(window))
        tip.set_tip(text, caret_down=True)
        tx = anchor.center().x() - tip.width() // 2
        ty = anchor.top() - tip.height() - 6
        caret_down = True
        if ty < 4:
            tip.set_tip(text, caret_down=False)
            ty = anchor.bottom() + 6
            caret_down = False
        tx = max(4, min(tx, window.width() - tip.width() - 4))
        ty = max(4, min(ty, window.height() - tip.height() - 4))
        target = QRect(tx, ty, tip.width(), tip.height())
        key = (tip._text, tx, ty, caret_down)
        if tip.isVisible() and getattr(tip, "_place_key", None) == key:
            return
        tip._place_key = key  # type: ignore[attr-defined]
        self._pop_bubble(tip, target, caret_down=caret_down)

    def _pop_bubble(self, tip: GlassTipBubble, target: QRect, *, caret_down: bool) -> None:
        """Grow from the caret so the tip reads as a bubble, not a sliding strip."""
        stop_slide(tip)
        stop_pop(tip)
        anchor = QPoint(
            target.center().x(),
            target.bottom() if caret_down else target.top(),
        )
        start = QRect(0, 0, max(18, target.width() // 3), max(14, target.height() // 3))
        start.moveLeft(anchor.x() - start.width() // 2)
        if caret_down:
            start.moveBottom(anchor.y())
        else:
            start.moveTop(anchor.y())
        tip.setGeometry(start)
        tip.show()
        tip.raise_()
        # Opacity lives on the tip only — never on MainWindow (GL freeze).
        eff = _ensure_opacity(tip)
        eff.setOpacity(0.0)
        op = QPropertyAnimation(eff, b"opacity", tip)
        op.setDuration(120)
        op.setStartValue(0.0)
        op.setEndValue(1.0)
        op.setEasingCurve(QEasingCurve.Type.OutCubic)
        geo = QPropertyAnimation(tip, b"geometry", tip)
        geo.setDuration(170)
        geo.setStartValue(start)
        geo.setEndValue(target)
        geo.setEasingCurve(QEasingCurve.Type.OutBack)
        tip._slide_anim = geo  # type: ignore[attr-defined]
        tip._pop_anim = op  # type: ignore[attr-defined]

        def _clear_geo() -> None:
            if getattr(tip, "_slide_anim", None) is geo:
                tip._slide_anim = None  # type: ignore[attr-defined]

        def _clear_op() -> None:
            if getattr(tip, "_pop_anim", None) is op:
                tip._pop_anim = None  # type: ignore[attr-defined]

        geo.finished.connect(_clear_geo)
        op.finished.connect(_clear_op)
        geo.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        op.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _qt_tip_target(self, obj: QWidget, event: QHelpEvent) -> tuple[str, QRect | None]:
        """Tooltip string plus the rect (in obj coords) the caret should point at."""
        parent = obj.parentWidget()
        if isinstance(parent, QAbstractItemView) and obj is parent.viewport():
            idx = parent.indexAt(event.pos())
            if not idx.isValid():
                return "", None
            raw = idx.data(Qt.ItemDataRole.ToolTipRole)
            return str(raw or "").strip(), parent.visualRect(idx)
        if isinstance(obj, QMenu):
            act = obj.actionAt(event.pos())
            if act is None:
                return "", None
            text = (act.toolTip() or "").strip()
            label = act.text().split("\t", 1)[0].replace("&", "").strip()
            if not text or text == label:
                return "", None
            return text, obj.actionGeometry(act)
        text = (obj.toolTip() or "").strip()
        if isinstance(obj, QAbstractButton):
            label = obj.text().replace("&", "").split("\t", 1)[0].strip()
            if text == label:
                return "", None
        elif isinstance(obj, QLabel) and text == obj.text().strip():
            return "", None
        if not text:
            return "", None
        return text, QRect(0, 0, obj.width(), obj.height())

    def _on_qt_tooltip(self, obj: QWidget, event: QEvent) -> None:
        if not isinstance(event, QHelpEvent):
            return
        # Icon chrome already draws this button's tip on hover.
        if str(obj.property("glassTip") or "").strip():
            return
        window = obj.window()
        if window is None:
            return
        text, local = self._qt_tip_target(obj, event)
        text = short_glass_tip(text)
        if not text or local is None or local.width() < 2 or local.height() < 2:
            if self._qt_tip_owner is obj:
                self._qt_tip_owner = None
                self._hide_tip_only()
            return
        anchor = QRect(obj.mapTo(window, local.topLeft()), local.size())
        _hl, tip = self._overlays(window)
        self._qt_tip_owner = obj
        self._place_tip(window, tip, text, anchor)

    def _hide_tip_only(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        for win in app.topLevelWidgets():
            tip = getattr(win, "_icon_glass_tip", None)
            if isinstance(tip, GlassTipBubble):
                stop_slide(tip)
                stop_pop(tip)
                tip._place_key = None  # type: ignore[attr-defined]
                tip.hide()

    def _hide_now(self) -> None:
        btn = self._btn
        self._btn = None
        # Always hide overlays first — lift on a deleted button must not abort cleanup.
        app = QApplication.instance()
        if app is not None:
            for win in app.topLevelWidgets():
                hl = getattr(win, "_icon_glass_hl", None)
                tip = getattr(win, "_icon_glass_tip", None)
                if isinstance(hl, HoverBubble):
                    stop_slide(hl)
                    hl.hide()
                if isinstance(tip, GlassTipBubble):
                    stop_slide(tip)
                    stop_pop(tip)
                    tip._place_key = None  # type: ignore[attr-defined]
                    tip.hide()
        if _qt_alive(btn):
            try:
                self._set_lift(btn, False)
            except RuntimeError:
                pass


_BUTTON_HOVER: ButtonHoverChrome | None = None


def install_button_hover_chrome(app: QApplication | None = None) -> ButtonHoverChrome:
    """Install app-wide button hover bubble + emboss lift (idempotent)."""
    global _BUTTON_HOVER
    if _BUTTON_HOVER is None:
        _BUTTON_HOVER = ButtonHoverChrome()
    inst = app or QApplication.instance()
    if isinstance(inst, QApplication):
        _BUTTON_HOVER.install(inst)
    return _BUTTON_HOVER


def clear_button_hover_chrome() -> None:
    """Hide stuck hover bubble/tip (sidebar rebuild, page swap, etc.)."""
    if _BUTTON_HOVER is not None:
        _BUTTON_HOVER.clear()


def attach_glass_tip(
    btn: QWidget,
    tip: str,
    *,
    highlight: bool = True,
) -> None:
    """Custom glass tip for an icon/text button (hover chrome is app-wide)."""
    chrome = install_button_hover_chrome()
    chrome.set_tip(btn, tip, highlight=highlight)


def stack_selector_chrome(host: QWidget, buttons: list | tuple) -> None:
    """Z-order: orange pill (bottom) → hover bubble → labels/icons."""
    pill = getattr(host, "_pill", None)
    hover = getattr(host, "_hover_bubble", None)
    if pill is not None:
        pill.lower()
    if hover is not None and hover.isVisible():
        hover.raise_()
    for b in buttons:
        if b is not None:
            b.raise_()


def lerp_pill_rects(rects: list[QRect], x: float) -> QRect:
    """Pill geometry that tracks x between adjacent rects (scrub)."""
    if not rects:
        return QRect()
    if len(rects) == 1:
        return QRect(rects[0])
    centers = [float(r.center().x()) for r in rects]
    x = max(centers[0], min(centers[-1], float(x)))
    for i in range(len(centers) - 1):
        c0, c1 = centers[i], centers[i + 1]
        if x > c1 and i < len(centers) - 2:
            continue
        t = 0.0 if c1 == c0 else (x - c0) / (c1 - c0)
        t = max(0.0, min(1.0, t))
        r0, r1 = rects[i], rects[i + 1]
        return QRect(
            round(r0.x() + (r1.x() - r0.x()) * t),
            round(r0.y() + (r1.y() - r0.y()) * t),
            round(r0.width() + (r1.width() - r0.width()) * t),
            round(r0.height() + (r1.height() - r0.height()) * t),
        )
    return QRect(rects[-1])


def lerp_pill_rect(buttons: list, x: int, pad: int = 2) -> QRect:
    """Pill geometry from live button widgets."""
    if not buttons:
        return QRect()
    rects = [b.geometry().adjusted(-pad, -pad, pad, pad) for b in buttons]
    return lerp_pill_rects(rects, float(x))


def nearest_index_at_x(rects: list[QRect], x: float) -> int:
    """Index of rect whose center is closest to x."""
    if not rects:
        return 0
    best_i, best_d = 0, 1e18
    for i, r in enumerate(rects):
        d = abs(float(r.center().x()) - float(x))
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def apple_pop_pill(pill: QWidget, ms: int = 380) -> None:
    """Apple-style select pop (geometry only).

    ponytail: no QGraphicsBlurEffect — blur blanks pills that are children of
    QOpenGLWidget (top/bottom chrome), leaving a black selector.
    Skip while a slide is in flight — pop+slide fighting geometry feels stuttery.
    """
    if getattr(pill, "_slide_anim", None) is not None:
        return
    geo = pill.geometry()
    if geo.width() < 4 or geo.height() < 4:
        return
    stop_pop(pill)
    if pill.graphicsEffect() is not None:
        pill.setGraphicsEffect(None)
    popped = QRect(geo).adjusted(-7, -4, 7, 4)
    geo_anim = QPropertyAnimation(pill, b"geometry", pill)
    geo_anim.setDuration(ms)
    geo_anim.setKeyValueAt(0.0, geo)
    geo_anim.setKeyValueAt(0.32, popped)
    geo_anim.setKeyValueAt(1.0, geo)
    geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)
    pill._pop_anim = geo_anim  # type: ignore[attr-defined]

    def _clear() -> None:
        if getattr(pill, "_pop_anim", None) is geo_anim:
            pill._pop_anim = None  # type: ignore[attr-defined]

    geo_anim.finished.connect(_clear)
    geo_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def animate_max_height(
    widget: QWidget,
    target: int,
    ms: int = 240,
    *,
    on_done=None,
) -> QPropertyAnimation:
    """Animate maximumHeight (collapse / expand panels)."""
    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(ms)
    anim.setStartValue(widget.maximumHeight())
    anim.setEndValue(max(0, int(target)))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_done is not None:
        anim.finished.connect(on_done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def animate_geometry(
    widget: QWidget,
    target: QRect,
    ms: int = 220,
    *,
    on_tick=None,
    on_done=None,
    min_frame_ms: int | None = None,
) -> QPropertyAnimation:
    """Slide a floating panel (Editor dock overlay) — does not resize GL.

    ``on_tick`` capped ~60Hz (16ms) so chrome tracks without layout storms.
    Low-end stays at 32ms. Per-frame (0) was silky on paper but janked frost hosts.
    """
    from time import monotonic

    if min_frame_ms is None:
        try:
            from ..util.hw import prefer_instant_panels

            min_frame_ms = 32 if prefer_instant_panels() else 16
        except Exception:
            min_frame_ms = 16

    prev = getattr(widget, "_geo_anim", None)
    if prev is not None:
        prev.stop()
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(ms)
    anim.setStartValue(widget.geometry())
    anim.setEndValue(QRect(target))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._geo_anim = anim  # type: ignore[attr-defined]
    last = {"t": 0.0}
    throttle = max(0, int(min_frame_ms))

    def _tick(_v=None) -> None:
        if on_tick is None:
            return
        if throttle > 0:
            now = monotonic()
            if (now - last["t"]) * 1000.0 < throttle:
                return
            last["t"] = now
        on_tick()

    def _finish() -> None:
        if getattr(widget, "_geo_anim", None) is anim:
            widget._geo_anim = None  # type: ignore[attr-defined]
        if on_tick is not None:
            on_tick()
        if on_done is not None:
            on_done()

    if on_tick is not None:
        anim.valueChanged.connect(_tick)
    anim.finished.connect(_finish)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def animate_max_width(
    widget: QWidget,
    target: int,
    ms: int = 280,
    *,
    on_tick=None,
    on_done=None,
    min_frame_ms: int = 32,
) -> QPropertyAnimation:
    """Animate maximumWidth (slide sidebar / dock in or out).

    ``on_tick`` is throttled — callers that resize heavy widgets (matplotlib)
    should not run every animation frame.
    """
    from time import monotonic

    prev = getattr(widget, "_max_w_anim", None)
    if prev is not None:
        prev.stop()
    anim = QPropertyAnimation(widget, b"maximumWidth", widget)
    anim.setDuration(ms)
    anim.setStartValue(int(widget.maximumWidth()))
    anim.setEndValue(max(0, int(target)))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._max_w_anim = anim  # type: ignore[attr-defined]
    last = {"t": 0.0}

    def _tick(_v=None) -> None:
        if on_tick is None:
            return
        now = monotonic()
        if (now - last["t"]) * 1000.0 < min_frame_ms:
            return
        last["t"] = now
        on_tick()

    def _finish() -> None:
        if getattr(widget, "_max_w_anim", None) is anim:
            widget._max_w_anim = None  # type: ignore[attr-defined]
        if on_tick is not None:
            on_tick()
        if on_done is not None:
            on_done()

    if on_tick is not None:
        anim.valueChanged.connect(_tick)
    anim.finished.connect(_finish)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def animate_splitter_sizes(
    split: QWidget,
    target_sizes: list[int],
    ms: int = 280,
    *,
    on_tick=None,
    on_done=None,
    min_frame_ms: int = 32,
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
) -> QVariantAnimation:
    """Lerp QSplitter.setSizes. Throttled — heavy layouts stutter if every frame."""
    from PySide6.QtWidgets import QSplitter
    from time import monotonic

    if not isinstance(split, QSplitter):
        return QVariantAnimation(split)
    prev = getattr(split, "_sizes_anim", None)
    if prev is not None:
        prev.stop()
    start = [int(x) for x in split.sizes()]
    end = [int(x) for x in target_sizes]
    if len(start) != len(end):
        split.setSizes(end)
        if on_tick is not None:
            on_tick()
        if on_done is not None:
            on_done()
        return QVariantAnimation(split)
    if start == end:
        if on_done is not None:
            on_done()
        return QVariantAnimation(split)

    anim = QVariantAnimation(split)
    anim.setDuration(max(1, int(ms)))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(easing)
    last = {"t": 0.0}

    def _apply(t: float) -> None:
        # Keep integer sizes monotonic toward end to avoid 1px flicker.
        t = max(0.0, min(1.0, float(t)))
        split.setSizes([int(round(a + (b - a) * t)) for a, b in zip(start, end)])
        if on_tick is not None:
            on_tick()

    def _on_val(v) -> None:
        now = monotonic()
        if now - last["t"] < (min_frame_ms / 1000.0) and float(v) < 0.999:
            return
        last["t"] = now
        _apply(float(v))

    def _finish() -> None:
        _apply(1.0)
        if getattr(split, "_sizes_anim", None) is anim:
            split._sizes_anim = None  # type: ignore[attr-defined]
        if on_done is not None:
            on_done()

    anim.valueChanged.connect(_on_val)
    anim.finished.connect(_finish)
    split._sizes_anim = anim  # type: ignore[attr-defined]
    anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade_overlay(overlay: QWidget, show: bool, ms: int = 200) -> None:
    """Show or hide a full-window overlay with a soft fade."""
    if show:
        overlay.setVisible(True)
        overlay.raise_()
        fade_widget(overlay, 0.0, 1.0, ms)
    else:
        anim = fade_widget(overlay, 1.0, 0.0, ms)

        def _hide() -> None:
            overlay.setVisible(False)
            # restore opacity for next show
            eff = overlay.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                eff.setOpacity(1.0)

        anim.finished.connect(_hide)


# Hub page directions — kept for call-site / test API; fade cover ignores them.
HUB_DIR_LEFT = "left"
HUB_DIR_RIGHT = "right"
HUB_DIR_UP = "up"
HUB_DIR_DOWN = "down"


def _downscale_snap(pm: QPixmap, max_edge: int = 1440) -> QPixmap:
    """Cheaper per-frame blit — full-res grab is the main hitch on big monitors."""
    if pm.isNull():
        return pm
    w, h = pm.width(), pm.height()
    edge = max(w, h)
    if edge <= max_edge:
        return pm
    scale = max_edge / float(edge)
    return pm.scaled(
        max(2, int(w * scale)),
        max(2, int(h * scale)),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class HubRevealOverlay(QWidget):
    """HOME↔studio cover — soft fade (optional tiny popup lift).

    ponytail: never put QGraphicsOpacityEffect on MainWindow / stacks that host
    QOpenGLWidget. Sibling cover only: grab → switch under → fade cover away.
    Silk: paint is one downscaled pixmap blit + opacity (no soft-shadow rings).
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("hubRevealOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()
        self._from_pm = QPixmap()
        self._progress = 0.0
        self._anim: QVariantAnimation | None = None
        self._on_done: Callable[[], None] | None = None

    def is_playing(self) -> bool:
        return self._anim is not None and self.isVisible()

    def stop(self) -> None:
        anim = self._anim
        if anim is not None:
            anim.stop()
            self._anim = None
        self.hide()
        self._from_pm = QPixmap()
        self._progress = 0.0

    def play(
        self,
        from_pm: QPixmap,
        *,
        direction: str = HUB_DIR_LEFT,  # noqa: ARG002 — API compat; fade ignores dir
        label: str = "",  # noqa: ARG002 — API compat; no caption plate
        accent: QColor | None = None,  # noqa: ARG002
        ink: QColor | None = None,  # noqa: ARG002
        dark: bool = True,  # noqa: ARG002
        ms: int = 260,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Cover with ``from_pm``, then fade it away to reveal the page under."""
        del direction, label, accent, ink, dark
        if from_pm.isNull() or from_pm.width() < 8:
            if on_done is not None:
                on_done()
            return
        self.stop()
        # Downscale once — painting full 4K grab every tick is the stutter.
        self._from_pm = _downscale_snap(from_pm)
        self._on_done = on_done
        self._progress = 0.0
        if self.width() < 8:
            parent = self.parentWidget()
            if parent is not None:
                self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.update()

        anim = QVariantAnimation(self)
        anim.setDuration(max(160, int(ms)))
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_tick)
        anim.finished.connect(self._finish)
        self._anim = anim
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _on_tick(self, value) -> None:  # noqa: ANN001
        self._progress = float(value)
        self.update()

    def _finish(self) -> None:
        cb = self._on_done
        self._anim = None
        self._on_done = None
        self.hide()
        self._from_pm = QPixmap()
        self._progress = 0.0
        if cb is not None:
            cb()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ARG002, ANN001
        if self._from_pm.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        t = max(0.0, min(1.0, self._progress))
        op = 1.0 - t
        if op < 0.01:
            return
        w, h = float(self.width()), float(self.height())
        if w < 2 or h < 2:
            return
        # Soft popup dismiss: tiny lift + scale while fading (not a directional wipe).
        scale = 1.0 + 0.018 * t
        sw, sh = w * scale, h * scale
        ox = (w - sw) * 0.5
        oy = (h - sh) * 0.5 - h * 0.006 * t
        p.setOpacity(op)
        p.drawPixmap(
            QRectF(ox, oy, sw, sh),
            self._from_pm,
            QRectF(self._from_pm.rect()),
        )


def animate_window_quit(
    window: QWidget,
    on_done: Callable[[], None],
    *,
    ms: int = 280,
) -> None:
    """Compositor fade + slight shrink on quit.

    Uses windowOpacity / geometry only — never QGraphicsOpacityEffect on
    MainWindow or GL hosts (that freezes the view — see HANDOFF).
    """
    if window is None:
        on_done()
        return
    prev = getattr(window, "_quit_anim", None)
    if isinstance(prev, QParallelAnimationGroup) and prev.state() == QParallelAnimationGroup.State.Running:
        return

    group = QParallelAnimationGroup(window)
    window._quit_anim = group  # type: ignore[attr-defined]

    op = QPropertyAnimation(window, b"windowOpacity", window)
    op.setDuration(ms)
    op.setStartValue(float(window.windowOpacity()))
    op.setEndValue(0.0)
    op.setEasingCurve(QEasingCurve.Type.InCubic)
    group.addAnimation(op)

    if not window.isMaximized() and not window.isFullScreen():
        geo = QRect(window.geometry())
        dx = max(10, geo.width() // 36)
        dy = max(8, geo.height() // 36)
        # Shrink + sink a touch — macOS-ish close settle.
        end = geo.adjusted(dx, dy + 10, -dx, -dy + 4)
        geo_anim = QPropertyAnimation(window, b"geometry", window)
        geo_anim.setDuration(ms)
        geo_anim.setStartValue(geo)
        geo_anim.setEndValue(end)
        geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        group.addAnimation(geo_anim)

    def _finish() -> None:
        if getattr(window, "_quit_anim", None) is group:
            window._quit_anim = None  # type: ignore[attr-defined]
        on_done()

    group.finished.connect(_finish)
    group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)


def animate_language_swap(root: QWidget, apply_fn: Callable[[], None], *, ms: int = 320) -> None:
    """Soft fade on text chrome, swap strings mid-way, fade back.

    Never puts QGraphicsOpacityEffect on MainWindow or any widget that hosts
    QOpenGLWidget (that freezes the GL view — see HANDOFF).
    """
    from PySide6.QtOpenGLWidgets import QOpenGLWidget

    if root is None:
        apply_fn()
        return

    # Skip if a swap is already running on this root
    prev = getattr(root, "_lang_swap_anim", None)
    if isinstance(prev, QParallelAnimationGroup) and prev.state() == QParallelAnimationGroup.State.Running:
        prev.stop()

    gl_widgets = set(root.findChildren(QOpenGLWidget))

    def _touches_gl(w: QWidget) -> bool:
        if w in gl_widgets:
            return True
        for gl in gl_widgets:
            p = gl.parentWidget()
            while p is not None:
                if p is w:
                    return True
                p = p.parentWidget()
        return False

    targets: list[QWidget] = []
    for w in root.findChildren(QWidget):
        if not w.isVisible():
            continue
        if _touches_gl(w):
            continue
        # Labels / buttons / menu bar — text carriers only
        if w.__class__.__name__ in {
            "QLabel",
            "QPushButton",
            "QToolButton",
            "QCheckBox",
            "QRadioButton",
            "QGroupBox",
            "QMenuBar",
            "QStatusBar",
        } or w.objectName() in {"navIconBtn", "iconBtn", "accentIconBtn"}:
            targets.append(w)
        if len(targets) >= 48:
            break

    if not targets:
        apply_fn()
        return

    group = QParallelAnimationGroup(root)
    root._lang_swap_anim = group  # type: ignore[attr-defined]
    half = max(80, ms // 2)
    applied = {"done": False}

    def _mid() -> None:
        if applied["done"]:
            return
        applied["done"] = True
        apply_fn()

    for w in targets:
        eff = _ensure_opacity(w)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(ms)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.45, 0.12)
        anim.setKeyValueAt(0.55, 0.12)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(anim)

    QTimer.singleShot(half, _mid)

    def _cleanup() -> None:
        if not applied["done"]:
            _mid()
        for w in targets:
            if w.graphicsEffect() is not None:
                # leave effect at 1.0 — removing mid-frame can flash
                eff = w.graphicsEffect()
                if isinstance(eff, QGraphicsOpacityEffect):
                    eff.setOpacity(1.0)
        if getattr(root, "_lang_swap_anim", None) is group:
            root._lang_swap_anim = None  # type: ignore[attr-defined]

    group.finished.connect(_cleanup)
    group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
