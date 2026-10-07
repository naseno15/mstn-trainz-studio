"""Floating glass title bar — macOS traffic lights + File/Edit/View/Tools/Theme/Lang.

Borderless window chrome: capsule sits inset from the top edges (not docked).
Dropdowns animate open with hover bubble + orange selection pill.

Uses a Tool window (not Qt.Popup) so the opening click cannot auto-dismiss
the menu — Popup was closing instantly on Windows frameless hosts.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .frost import glass_is_dark, paint_soft_shadow, set_glass_dark
from .motion import (
    apple_pop_pill,
    attach_hover_bubble,
    slide_to,
    stack_selector_chrome,
    stop_pop,
    stop_slide,
)

TITLE_BAR_H = 60  # +8 so capsule shadow can fade (was clipped at 52)
TITLE_MARGIN = 12
# Keep page content below the floating bar — no logo bleed-through.
TITLE_CONTENT_INSET = TITLE_MARGIN + TITLE_BAR_H + 6
TITLE_RADIUS = 22.0
# Room for 13px + descenders under #titleNavBtn padding (not #navBtn 10px).
MENU_BTN_H = 34
DROP_RADIUS = 16.0
EDGE_GRIP = 6


def begin_frameless_move(window: QWidget | None) -> bool:
    """Start a system move on a frameless top-level window.

    Qt ``startSystemMove`` often no-ops on maximized frameless HWND on Windows.
    Win32 ``WM_NCLBUTTONDOWN`` / ``HTCAPTION`` is the reliable path (also lets
    the user drag a maximized window onto another monitor).
    """
    if window is None:
        return False
    host = window.window() if window is not None else None
    if host is None:
        host = window
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(host.winId())
            # ReleaseCapture + WM_NCLBUTTONDOWN(HTCAPTION) — blocks until drag ends.
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, 2, 0)
            return True
        except Exception:
            pass
    wh = host.windowHandle()
    if wh is not None:
        return bool(wh.startSystemMove())
    return False


class AccentPill(QWidget):
    """Orange selector — same look as app/nav chrome pills."""

    def __init__(self, parent: QWidget | None = None, *, radius: float = 12.0) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if r.width() < 2 or r.height() < 2:
            return
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QColor("#ff7a45"))
        grad.setColorAt(0.42, QColor("#ff5a1f"))
        grad.setColorAt(1.0, QColor("#c43a10"))
        p.fillPath(path, grad)
        p.setPen(QPen(QColor(255, 214, 180, 150), 1.0))
        p.drawPath(path)


class TrafficLight(QWidget):
    """One macOS traffic-light disc — glyph appears on cluster hover."""

    clicked = Signal()

    _COLORS = {
        "close": ("#FF5F57", "#E04840"),
        "min": ("#FEBC2E", "#DEA123"),
        "zoom": ("#28C840", "#1AAB29"),
    }
    _GLYPHS = {"close": "×", "min": "−", "zoom": "+"}

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind if kind in self._COLORS else "close"
        self._hover_cluster = False
        self._pressed = False
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            {"close": "Close", "min": "Minimize", "zoom": "Maximize"}.get(self._kind, "")
        )

    def set_cluster_hover(self, on: bool) -> None:
        if self._hover_cluster == on:
            return
        self._hover_cluster = on
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fill, rim = self._COLORS[self._kind]
        c = QColor(fill)
        if self._pressed:
            c = QColor(rim)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(0, 0, 0, 40), 0.8))
        p.setBrush(c)
        p.drawEllipse(r)
        if self._hover_cluster:
            p.setPen(QPen(QColor(60, 40, 20, 200), 1.2))
            f = QFont(self.font())
            f.setPixelSize(10)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._GLYPHS[self._kind])


class TrafficLights(QWidget):
    """Close · Minimize · Zoom — left cluster, macOS order."""

    close_clicked = Signal()
    minimize_clicked = Signal()
    zoom_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(MENU_BTN_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(8)
        self.close_btn = TrafficLight("close", self)
        self.min_btn = TrafficLight("min", self)
        self.zoom_btn = TrafficLight("zoom", self)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.min_btn.clicked.connect(self.minimize_clicked.emit)
        self.zoom_btn.clicked.connect(self.zoom_clicked.emit)
        for b in (self.close_btn, self.min_btn, self.zoom_btn):
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self._set_hover(True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._set_hover(False)

    def _set_hover(self, on: bool) -> None:
        for b in (self.close_btn, self.min_btn, self.zoom_btn):
            b.set_cluster_hover(on)


class _MenuTitleBtn(QPushButton):
    """Top-level File/Edit/View/Lang label — not checkable (pill = open state)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        # titleNavBtn — compact padding; #navBtn's 10px vertical clips Lang's g.
        self.setObjectName("titleNavBtn")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(MENU_BTN_H)
        self.setMinimumWidth(52)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFlat(True)
        self.setAutoDefault(False)
        self.setDefault(False)


class GlassDropMenu(QWidget):
    """Frameless glass dropdown — Tool window (not Popup) so open-click can't kill it."""

    closed = Signal()
    item_chosen = Signal(object)  # QAction

    def __init__(self, parent: QWidget | None = None) -> None:
        # Tool + Frameless: stays until we hide it. Popup auto-closed on the same click.
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._dark = True
        self._items: list[QPushButton] = []
        self._actions: list[QAction] = []
        self._sep_count = 0
        self._pill = AccentPill(self, radius=10.0)
        self._pill.hide()
        self._body = QWidget(self)
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(10, 10, 10, 10)
        self._lay.setSpacing(2)
        self._anim: QPropertyAnimation | None = None
        self._suppress_closed = False
        self.hide()

    def set_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        set_glass_dark(self, self._dark)
        self.update()

    def clear_items(self) -> None:
        old = getattr(self._body, "_hover_bubble", None)
        if old is not None:
            old.hide()
            old.setParent(None)
            old.deleteLater()
        ctl = getattr(self._body, "_hover_ctl", None)
        if ctl is not None:
            ctl.deleteLater()
            self._body._hover_ctl = None  # type: ignore[attr-defined]
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._items.clear()
        self._actions.clear()
        self._sep_count = 0

    def populate(self, menu: QMenu) -> None:
        self.clear_items()
        self._sep_count = 0
        for act in menu.actions():
            if act.isSeparator():
                line = QFrame(self._body)
                line.setFixedHeight(1)
                line.setStyleSheet(
                    "background: rgba(255,255,255,0.14);"
                    if self._dark
                    else "background: rgba(0,0,0,0.12);"
                )
                self._lay.addWidget(line)
                self._sep_count += 1
                continue
            if not act.isVisible():
                continue
            label = act.text().replace("&", "")
            if act.isCheckable() and act.isChecked():
                label = "✓  " + label
            sc = act.shortcut().toString() if act.shortcut() else ""
            btn = QPushButton(self._body)
            # Not navBtn — theme padding on #navBtn fights fixed 34px rows.
            btn.setObjectName("menuDropItem")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.setFixedHeight(34)
            btn.setMinimumWidth(200)
            btn.setEnabled(act.isEnabled())
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                "QPushButton#menuDropItem {"
                "  background: transparent; border: none; border-radius: 8px;"
                "  padding: 4px 12px; text-align: left;"
                f"  color: {'#f2f4f7' if self._dark else '#1c1c1e'};"
                "}"
                "QPushButton#menuDropItem:hover { background: transparent; }"
                "QPushButton#menuDropItem:disabled { color: #888; }"
            )
            tip = act.toolTip() or ""
            if tip:
                btn.setToolTip(tip)
            btn.setText(f"{label}    {sc}" if sc else label)
            self._lay.addWidget(btn)
            btn.clicked.connect(lambda _=False, a=act: self._fire(a))
            btn.installEventFilter(self)
            self._items.append(btn)
            self._actions.append(act)
        attach_hover_bubble(self._body, self._items, radius=10.0, pad=1, warm=True)
        self._body._pill = self._pill  # type: ignore[attr-defined]
        self._pill.setParent(self._body)
        self._pill.lower()

    def _fire(self, act: QAction) -> None:
        btn = next((b for b, a in zip(self._items, self._actions) if a is act), None)
        if btn is not None:
            r = btn.geometry().adjusted(-2, -2, 2, 2)
            self._pill.show()
            self._pill.setGeometry(r)
            stack_selector_chrome(self._body, self._items)
            apple_pop_pill(self._pill, ms=260)
            QTimer.singleShot(140, lambda: self._trigger_and_close(act))
        else:
            self._trigger_and_close(act)

    def _trigger_and_close(self, act: QAction) -> None:
        self.hide_menu()
        if act.isEnabled():
            act.trigger()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj in self._items and event.type() == QEvent.Type.Enter:
            r = obj.geometry().adjusted(-2, -2, 2, 2)
            self._pill.show()
            if self._pill.width() > 4:
                slide_to(self._pill, r, ms=220)
            else:
                self._pill.setGeometry(r)
            stack_selector_chrome(self._body, self._items)
        return super().eventFilter(obj, event)

    def _content_size(self, anchor: QWidget) -> tuple[int, int]:
        """Explicit size — sizeHint is unreliable before the Tool is mapped."""
        pad_x, pad_y = 20, 20
        row = 34
        gap = 2
        n = len(self._items)
        seps = getattr(self, "_sep_count", 0)
        h = pad_y + n * row + max(0, n - 1) * gap + seps * (1 + gap)
        fm_w = 200
        for b in self._items:
            fm_w = max(fm_w, b.sizeHint().width())
        w = max(fm_w + pad_x, anchor.width() + 24, 220)
        return w, max(h, 48)

    def popup_below(self, anchor: QWidget) -> None:
        w, h = self._content_size(anchor)
        # Allow size to change between open/close cycles.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._body.setMinimumSize(0, 0)
        self._body.setMaximumSize(16777215, 16777215)
        self._body.setFixedSize(w, h)
        self.setFixedSize(w, h)
        g = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        end = QRect(g.x(), g.y(), w, h)
        # Slide down at FULL height — never animate height (that crushed rows on Win).
        start = QRect(g.x(), g.y() - 10, w, h)
        self.setWindowOpacity(1.0)
        self._stop_anim()
        # Remount Tool window — hide/show so the second open isn't a no-op on Win.
        self._suppress_closed = True
        self.hide()
        self._suppress_closed = False
        self.setGeometry(end)
        self._body.setGeometry(self.rect())
        self.show()
        self.raise_()
        # Optional slide: start slightly above, settle to end.
        self.setGeometry(start)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _land() -> None:
            if not self.isVisible():
                return
            self.setGeometry(end)
            self._body.setGeometry(self.rect())
            if self._items:
                self._land_pill(self._items[0])

        self._anim.finished.connect(_land)
        # Keep Python ref alive — DeleteWhenStopped left a dangling ptr (2nd open crash).
        self._anim.start()
        if self._items:
            QTimer.singleShot(
                0,
                lambda: self._land_pill(self._items[0]) if self.isVisible() and self._items else None,
            )

    def _stop_anim(self) -> None:
        anim = self._anim
        self._anim = None
        if anim is None:
            return
        try:
            from shiboken6 import isValid

            if not isValid(anim):
                return
            anim.stop()
        except RuntimeError:
            pass

    def _land_pill(self, btn: QPushButton) -> None:
        if not self.isVisible() or btn not in self._items:
            return
        r = btn.geometry().adjusted(-2, -2, 2, 2)
        self._pill.setGeometry(r)
        self._pill.show()
        stack_selector_chrome(self._body, self._items)
        apple_pop_pill(self._pill, ms=220)

    def hide_menu(self) -> None:
        """Hide without relying on Popup auto-dismiss."""
        self._stop_anim()
        if not self.isVisible():
            return
        self._suppress_closed = False
        self.hide()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if not self._suppress_closed:
            self.closed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._body.setGeometry(self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        dark = self._dark
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        full = QRectF(self.rect())
        if full.width() < 4 or full.height() < 4:
            return
        for grow, alpha in ((4.0, 30), (1.5, 50)):
            sr = full.adjusted(2.0, 3.0 + grow * 0.3, -2.0, 1.0 + grow)
            sp = QPainterPath()
            sp.addRoundedRect(sr, DROP_RADIUS, DROP_RADIUS)
            p.fillPath(sp, QColor(0, 0, 0, alpha))
        r = full.adjusted(2.5, 1.5, -2.5, -4.0)
        rad = min(DROP_RADIUS, r.width() * 0.5, r.height() * 0.5)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        fill = QLinearGradient(r.topLeft(), r.bottomLeft())
        if dark:
            fill.setColorAt(0.0, QColor(42, 48, 58, 248))
            fill.setColorAt(0.5, QColor(28, 34, 42, 252))
            fill.setColorAt(1.0, QColor(18, 22, 28, 255))
            rim = QColor(255, 255, 255, 70)
        else:
            fill.setColorAt(0.0, QColor(244, 246, 249, 248))
            fill.setColorAt(1.0, QColor(220, 226, 234, 252))
            rim = QColor(0, 0, 0, 48)
        p.fillPath(path, fill)
        p.setPen(QPen(rim, 1.0))
        p.drawPath(path)

    def global_rect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())


class FloatTitleBar(QFrame):
    """Inset glass capsule: traffic lights + File / Edit / View / Tools / Theme / Lang."""

    close_clicked = Signal()
    minimize_clicked = Signal()
    zoom_clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, mode: str = "dark") -> None:
        super().__init__(parent)
        self.setObjectName("floatTitleBar")
        self.setFixedHeight(TITLE_BAR_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        dark = mode != "light"
        set_glass_dark(self, dark)

        self._pill = AccentPill(self, radius=12.0)
        self._pill.hide()
        self._menus: dict[str, QMenu] = {}
        self._open_key: str | None = None
        # Parent to the window so the Tool is a real top-level sibling.
        host = parent.window() if parent is not None else None
        self._drop = GlassDropMenu(host if host is not None else self)
        self._drop.set_theme(dark)
        self._drop.closed.connect(self._on_drop_closed)

        lay = QHBoxLayout(self)
        # Pad clears the soft shadow room (plate inset ~5/12 inside TITLE_BAR_H).
        lay.setContentsMargins(14, 12, 16, 14)
        lay.setSpacing(6)

        self.lights = TrafficLights(self)
        self.lights.close_clicked.connect(self.close_clicked.emit)
        self.lights.minimize_clicked.connect(self.minimize_clicked.emit)
        self.lights.zoom_clicked.connect(self.zoom_clicked.emit)
        lay.addWidget(self.lights, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addSpacing(10)

        self._btns: dict[str, _MenuTitleBtn] = {}
        for key in ("File", "Edit", "View", "Tools", "Theme", "Lang"):
            btn = _MenuTitleBtn(key, self)
            btn.clicked.connect(lambda _=False, k=key: self._on_menu_clicked(k))
            self._btns[key] = btn
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)
        self._title = QLabel("", self)
        self._title.setObjectName("mutedTip")
        self._title.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        lay.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        attach_hover_bubble(
            self,
            list(self._btns.values()),
            radius=12.0,
            pad=2,
            warm=True,
        )
        self._pill.lower()
        self._filter_installed = False

    def _install_outside_filter(self) -> None:
        if self._filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._filter_installed = True

    def _remove_outside_filter(self) -> None:
        if not self._filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._filter_installed = False

    def set_theme(self, mode: str) -> None:
        dark = mode != "light"
        set_glass_dark(self, dark)
        self._drop.set_theme(dark)
        self.update()

    def set_window_title_text(self, text: str) -> None:
        t = (text or "").strip()
        if "—" in t:
            t = t.split("—", 1)[-1].strip()
        elif "-" in t and len(t) > 28:
            t = t.split("-", 1)[-1].strip()
        fm = QFontMetrics(self._title.font())
        self._title.setText(fm.elidedText(t, Qt.TextElideMode.ElideRight, 280))

    def bind_menus(self, menus: dict[str, QMenu | None]) -> None:
        self._menus = {k: v for k, v in menus.items() if v is not None}
        self.sync_titles()

    def sync_titles(self) -> None:
        for key, btn in self._btns.items():
            menu = self._menus.get(key)
            if menu is not None and menu.title():
                btn.setText(menu.title().replace("&", ""))
            else:
                btn.setText(key)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        dark = glass_is_dark(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        full = QRectF(self.rect())
        if full.width() < 4 or full.height() < 4:
            return
        side, top, bot = 8.0, 5.0, 12.0
        r = full.adjusted(side, top, -side, -bot)
        if r.width() < 8 or r.height() < 8:
            r = full.adjusted(3.5, 2.5, -3.5, -5.0)
        clip = full.adjusted(1.0, 1.0, -1.0, -1.0)
        paint_soft_shadow(
            p,
            r,
            radius=TITLE_RADIUS,
            dark=dark,
            clip=clip,
            max_spread=min(11.0, bot - 1.0),
            dy=2.0,
            peak_alpha=44.0,
            layers=12,
        )
        rad = min(TITLE_RADIUS, r.width() * 0.5, r.height() * 0.5)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        fill = QLinearGradient(r.topLeft(), r.bottomLeft())
        if dark:
            fill.setColorAt(0.0, QColor(42, 48, 58, 245))
            fill.setColorAt(0.45, QColor(28, 34, 42, 250))
            fill.setColorAt(1.0, QColor(18, 22, 28, 252))
            rim = QColor(255, 255, 255, 70)
            spec = QColor(255, 255, 255, 110)
        else:
            fill.setColorAt(0.0, QColor(244, 246, 249, 242))
            fill.setColorAt(0.5, QColor(232, 236, 242, 248))
            fill.setColorAt(1.0, QColor(214, 220, 228, 252))
            rim = QColor(255, 255, 255, 150)
            spec = QColor(255, 255, 255, 175)
        p.fillPath(path, fill)
        sheen = QLinearGradient(r.topLeft(), QRectF(r).center())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 55 if dark else 95))
        sheen.setColorAt(0.55, QColor(255, 255, 255, 0))
        p.fillPath(path, sheen)
        p.setPen(QPen(rim, 1.0))
        p.drawPath(path)
        p.setPen(QPen(spec, 1.15))
        p.drawLine(int(r.left() + rad), int(r.top() + 1), int(r.right() - rad), int(r.top() + 1))

    def reposition(self, host: QWidget | None = None) -> None:
        parent = host or self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        hint_w = max(self.sizeHint().width(), 420)
        w = min(
            max(hint_w, parent.width() - TITLE_MARGIN * 2),
            parent.width() - TITLE_MARGIN * 2,
        )
        w = max(320, w)
        self.setFixedWidth(w)
        self.setFixedHeight(TITLE_BAR_H)
        self.move(TITLE_MARGIN, TITLE_MARGIN)
        self.show()
        self.raise_()
        self._sync_open_pill(animate=False)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        # App-wide filter — never call super().eventFilter (recurses with other filters).
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        if self._open_key is None:
            return False
        try:
            drop = self._drop
            if drop is None or not drop.isVisible():
                return False
        except RuntimeError:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        gp = event.globalPosition().toPoint()
        try:
            if drop.global_rect().adjusted(-4, -4, 4, 4).contains(gp):
                return False
        except RuntimeError:
            return False
        if self._menu_key_at_global(gp) is not None:
            return False  # menu button handles toggle/switch
        self._close_menu()
        return False

    def closeEvent(self, event) -> None:  # noqa: N802
        self._remove_outside_filter()
        super().closeEvent(event)

    def _menu_key_at_global(self, gp: QPoint) -> str | None:
        for key, btn in self._btns.items():
            top = btn.mapToGlobal(QPoint(0, 0))
            if QRect(top, btn.size()).adjusted(-2, -2, 2, 2).contains(gp):
                return key
        return None

    def _on_menu_clicked(self, key: str) -> None:
        if self._open_key == key and self._drop.isVisible():
            self._close_menu()
            return
        self._open_menu(key)

    def _on_drop_closed(self) -> None:
        # Tool hide / Esc path — clear orange pill.
        if not self._drop.isVisible():
            self._reset_menu_chrome()

    def _open_menu(self, key: str) -> None:
        menu = self._menus.get(key)
        btn = self._btns.get(key)
        if menu is None or btn is None:
            return
        # Quietly hide previous without clearing pill mid-switch.
        if self._drop.isVisible():
            self._drop._suppress_closed = True  # type: ignore[attr-defined]
            self._drop.hide()
            self._drop._suppress_closed = False  # type: ignore[attr-defined]
        self._open_key = key
        ctl = getattr(self, "_hover_ctl", None)
        if ctl is not None:
            ctl.hide_now()
        self._sync_open_pill(animate=True, pop=True)
        self._drop.populate(menu)
        # Defer one tick so the mouse-release of this click can't punch through.
        QTimer.singleShot(0, lambda k=key: self._show_drop(k))

    def _show_drop(self, key: str) -> None:
        if self._open_key != key:
            return
        btn = self._btns.get(key)
        if btn is None:
            return
        self._drop.popup_below(btn)
        self._sync_open_pill(animate=False)
        self._install_outside_filter()

    def _close_menu(self) -> None:
        self._remove_outside_filter()
        if self._drop.isVisible():
            self._drop.hide_menu()
        self._reset_menu_chrome()

    def _reset_menu_chrome(self) -> None:
        self._remove_outside_filter()
        self._open_key = None
        stop_slide(self._pill)
        stop_pop(self._pill)
        self._pill.hide()

    def _sync_open_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        if self._open_key is None:
            stop_slide(self._pill)
            stop_pop(self._pill)
            self._pill.hide()
            return
        btn = self._btns.get(self._open_key)
        if btn is None:
            return
        r = btn.geometry().adjusted(-2, -2, 2, 2)
        self._pill.show()
        stack_selector_chrome(self, list(self._btns.values()))
        if animate and self._pill.width() > 8:
            anim = slide_to(self._pill, r)

            def _pop() -> None:
                if self._open_key is not None:
                    apple_pop_pill(self._pill)

            if pop:
                anim.finished.connect(_pop)
        else:
            stop_slide(self._pill)
            self._pill.setGeometry(r)
            if pop:
                QTimer.singleShot(
                    0,
                    lambda: apple_pop_pill(self._pill) if self._open_key else None,
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pt = event.position().toPoint()
        if self.lights.geometry().contains(pt):
            super().mousePressEvent(event)
            return
        for b in self._btns.values():
            if b.geometry().contains(pt):
                super().mousePressEvent(event)
                return
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if begin_frameless_move(self.window()):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.zoom_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def install_frameless(window: QWidget) -> None:
    """Strip native frame — custom title bar owns chrome."""
    flags = window.windowFlags()
    window.setWindowFlags(
        (flags & ~Qt.WindowType.WindowTitleHint & ~Qt.WindowType.WindowSystemMenuHint)
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowMinMaxButtonsHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.Window
    )


def edge_at(pos: QPoint, size: QSize, grip: int = EDGE_GRIP) -> Qt.Edge | None:
    """Which window edge the cursor is on (for startSystemResize)."""
    x, y = pos.x(), pos.y()
    w, h = size.width(), size.height()
    left = x <= grip
    right = x >= w - grip
    top = y <= grip
    bottom = y >= h - grip
    edges = Qt.Edge(0)
    if left:
        edges |= Qt.Edge.LeftEdge
    if right:
        edges |= Qt.Edge.RightEdge
    if top:
        edges |= Qt.Edge.TopEdge
    if bottom:
        edges |= Qt.Edge.BottomEdge
    return edges if edges != Qt.Edge(0) else None
