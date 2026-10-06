"""Engine Tuner bottom page nav — floating capsule + accent pill (Mesh-style)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from ..float_chrome import (
    bind_split_wells,
    make_home_button,
    mount_center_icon_nav,
    paint_float_nav,
    prepare_float_nav,
)
from ..frost import set_glass_dark
from ..icons import set_home_icon
from ..motion import apple_pop_pill, attach_hover_bubble, slide_to, stack_selector_chrome, stop_slide


class AccentPill(QWidget):
    def __init__(self, parent: QWidget | None = None, *, radius: float = 12.0) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

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


class EnginePageNav(QFrame):
    """Home center | Tuner · Simulation · Parameters · Auto Tune — Theme is top menu."""

    page_changed = Signal(str)
    home_clicked = Signal()
    theme_clicked = Signal()  # unused — MainWindow Theme menu owns appearance
    autotune_toggled = Signal(bool)

    PAGES = ("tuner", "simulation", "parameters")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_float_nav(self)
        self._pill = AccentPill(self, radius=14.0)
        self._pill.lower()
        self._page = "tuner"

        lay = QHBoxLayout(self)

        self.tuner_btn = QPushButton("Tuner")
        self.sim_btn = QPushButton("Simulation")
        self.params_btn = QPushButton("Parameters")
        self._nav_btns = (self.tuner_btn, self.sim_btn, self.params_btn)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, (b, page) in enumerate(zip(self._nav_btns, self.PAGES)):
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedWidth(120)
            b.setAutoExclusive(True)
            self._group.addButton(b, i)
            b.clicked.connect(lambda _=False, p=page: self.set_page(p, emit=True))
        self.tuner_btn.setChecked(True)

        self.auto_btn = QPushButton("Auto Tune")
        self.auto_btn.setObjectName("navBtn")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_btn.setFixedWidth(120)
        self.auto_btn.setToolTip("TEE generate · Davis resistance sidebar")
        self.auto_btn.toggled.connect(self.autotune_toggled.emit)

        self.home_btn = make_home_button(self)
        self.home_btn.clicked.connect(self.home_clicked.emit)
        left, right = mount_center_icon_nav(
            lay,
            home_btn=self.home_btn,
            page_btns=self._nav_btns,
        )
        # Auto Tune sits immediately right of Parameters (not a page — no orange pill)
        lay.addWidget(self.auto_btn)
        bind_split_wells(
            self,
            home_btn=self.home_btn,
            left_btns=left,
            right_btns=[*right, self.auto_btn],
        )
        attach_hover_bubble(
            self,
            [*self._nav_btns, self.auto_btn, self.home_btn],
            radius=14.0,
        )

        QTimer.singleShot(0, lambda: self._sync_pill(False))

    def set_autotune_checked(self, on: bool) -> None:
        self.auto_btn.blockSignals(True)
        self.auto_btn.setChecked(bool(on))
        self.auto_btn.blockSignals(False)

    def set_home_mode(self, *, cdp: bool) -> None:
        """CDP session: Home becomes ← (returns to Packages)."""
        set_home_icon(self.home_btn, back=bool(cdp))

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        set_glass_dark(self, mode != "light")

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        paint_float_nav(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            if self.home_btn.geometry().contains(pt):
                self.home_btn.click()
                event.accept()
                return
        super().mousePressEvent(event)

    def set_page(self, page: str, *, emit: bool = False, animate: bool = True) -> None:
        if page not in self.PAGES:
            page = "tuner"
        changed = page != self._page
        self._page = page
        for b, p in zip(self._nav_btns, self.PAGES):
            b.blockSignals(True)
            b.setChecked(p == page)
            b.blockSignals(False)
        self._stack_pill()
        self._sync_pill(animate, pop=changed and emit)
        if emit and changed:
            self.page_changed.emit(page)

    def _stack_pill(self) -> None:
        self._pill.show()
        stack_selector_chrome(
            self,
            [*self._nav_btns, self.auto_btn, self.home_btn],
        )

    def _sync_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        btn = next((b for b in self._nav_btns if b.isChecked()), self.tuner_btn)
        r = btn.geometry().adjusted(-2, -2, 2, 2)
        if animate and self._pill.width() > 8:
            anim = slide_to(self._pill, r)
            if pop:
                anim.finished.connect(lambda: apple_pop_pill(self._pill))
        else:
            stop_slide(self._pill)
            self._pill.setGeometry(r)
            if pop:
                QTimer.singleShot(0, lambda: apple_pop_pill(self._pill))
        self._stack_pill()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_pill(False)
