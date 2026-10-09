"""Assets Studio bottom + top page nav — floating capsule + accent pill + scrub."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from ..float_chrome import (
    FLOAT_NAV_HEIGHT_TALL,
    HOME_GAP_TALL,
    NAV_ICON_SIDE_TALL,
    bind_page_well,
    bind_split_wells,
    hit_page_cluster,
    make_home_button,
    mount_center_icon_nav,
    mount_page_only_nav,
    paint_float_nav,
    prepare_float_nav,
)
from ..frost import set_glass_dark
from ..motion import (
    SCRUB_LERP,
    apple_pop_pill,
    attach_hover_bubble,
    lerp_pill_rects,
    nearest_index_at_x,
    slide_to,
    stack_selector_chrome,
    stop_slide,
)


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


class _ScrubPillNav(QFrame):
    """Accent pill + Mesh-style press-drag scrub (shared by bottom / top bars)."""

    page_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_float_nav(self)
        self._pill = AccentPill(self, radius=14.0)
        self._pill.lower()
        self._page = ""
        self._committed = ""
        self._nav_btns: list[QPushButton] = []
        self._pages: tuple[str, ...] = ()
        self._drag = False
        self._drag_rects: list = []
        self._scrub_x = 0.0
        self._scrub_target = 0.0
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setInterval(8)
        self._scrub_timer.timeout.connect(self._tick_scrub)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        paint_float_nav(self)

    def eventFilter(self, obj, event) -> bool:
        if obj in self._nav_btns:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                local = obj.mapTo(self, event.position().toPoint())
                self._begin_scrub(local.x())
                return True
            if et == QEvent.Type.MouseButtonRelease and self._drag:
                return True
        return super().eventFilter(obj, event)

    def _stack_pill(self) -> None:
        self._pill.show()
        stack_selector_chrome(self, self._nav_btns)

    def _snapshot_rects(self) -> list:
        return [b.geometry().adjusted(-2, -2, 2, 2) for b in self._nav_btns]

    def _page_at_x(self, x: float) -> str:
        rects = self._drag_rects or self._snapshot_rects()
        return self._pages[nearest_index_at_x(rects, x)]

    def _begin_scrub(self, x: int) -> None:
        ctl = getattr(self, "_hover_ctl", None)
        if ctl is not None:
            ctl.hide_now()
        self._drag = True
        self._drag_rects = self._snapshot_rects()
        stop_slide(self._pill)
        self._scrub_x = (
            float(self._pill.geometry().center().x()) if self._pill.width() > 8 else float(x)
        )
        self._scrub_target = float(x)
        self._stack_pill()
        self.grabMouse()
        if not self._scrub_timer.isActive():
            self._scrub_timer.start()
        self._tick_scrub()

    def _tick_scrub(self) -> None:
        if not self._drag_rects:
            return
        self._scrub_x += (self._scrub_target - self._scrub_x) * SCRUB_LERP
        if abs(self._scrub_target - self._scrub_x) < 0.4:
            self._scrub_x = self._scrub_target
        self._pill.setGeometry(lerp_pill_rects(self._drag_rects, self._scrub_x))
        if not self._drag and abs(self._scrub_target - self._scrub_x) < 0.4:
            self._scrub_timer.stop()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            if not hit_page_cluster(self._nav_btns, pt):
                super().mousePressEvent(event)
                return
            self._begin_scrub(int(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag:
            self._scrub_target = float(event.position().x())
            if not self._scrub_timer.isActive():
                self._scrub_timer.start()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag and event.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.releaseMouse()
            x = float(event.position().x())
            page = self._page_at_x(x)
            idx = self._pages.index(page)
            if self._drag_rects:
                self._scrub_target = float(self._drag_rects[idx].center().x())
                self._scrub_x = self._scrub_target
            self._scrub_timer.stop()
            self._drag_rects = []
            self._apply_page(page, animate=True, emit=True, commit=True, pop=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _normalize_page(self, page: str) -> str:
        if page not in self._pages:
            return self._pages[0] if self._pages else page
        return page

    def _apply_page(
        self,
        page: str,
        *,
        animate: bool,
        emit: bool,
        commit: bool,
        pop: bool = False,
    ) -> None:
        page = self._normalize_page(page)
        self._page = page
        for b, p in zip(self._nav_btns, self._pages):
            b.blockSignals(True)
            b.setChecked(p == page)
            b.blockSignals(False)
        self._stack_pill()
        self._sync_pill(animate, pop=pop and commit)
        if commit:
            changed = page != self._committed
            self._committed = page
            if emit and changed:
                self.page_changed.emit(page)

    def set_page(self, page: str, *, emit: bool = False, animate: bool = True) -> None:
        page = self._normalize_page(page)
        # Same page: never stop_slide — would kill an in-flight click/scrub anim
        if page == self._page and page == self._committed:
            return
        self._apply_page(page, animate=animate, emit=emit, commit=True, pop=False)

    def _sync_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        btn = next((b for b in self._nav_btns if b.isChecked()), self._nav_btns[0])
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
        if not self._drag:
            self._sync_pill(False)


class AssetsPageNav(_ScrubPillNav):
    """Home center | suite pages — Assets or Texture & Mesh Lods tools."""

    home_clicked = Signal()
    theme_clicked = Signal()  # unused — MainWindow Theme menu owns appearance

    # suite → (pages, labels, widths)
    # texmesh order: Mesh Lods · Texture Params | Home | Texture Editor · Texture Denoiser
    SUITE_PAGES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[int, ...]]] = {
        "assets": (
            ("packages", "config", "kuid", "export"),
            ("Packages", "Config", "KUID", "Export"),
            (92, 92, 92, 92),
        ),
        "texmesh": (
            ("meshops", "texture", "parameter", "denoise"),
            # Two-line labels — long names were clipping inside the pill.
            (
                "Mesh\nLods",
                "Texture\nParams",
                "Texture\nEditor",
                "Texture\nDenoiser",
            ),
            (88, 92, 92, 108),
        ),
    }
    # Back-compat aliases used by older checks / callers.
    PAGES = SUITE_PAGES["assets"][0]
    LABELS = SUITE_PAGES["assets"][1]
    WIDTHS = SUITE_PAGES["assets"][2]

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        suite: str = "assets",
    ) -> None:
        super().__init__(parent)
        self._suite = suite if suite in self.SUITE_PAGES else "assets"
        pages, labels, widths = self.SUITE_PAGES[self._suite]
        self.PAGES = pages
        self.LABELS = labels
        self.WIDTHS = widths
        self._pages = pages
        self._page = pages[0]
        self._committed = pages[0]

        lay = QHBoxLayout(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        tall = self._suite == "texmesh"
        if tall:
            # Two-line labels — taller capsule + bigger Home (other suites stay 72).
            self.setFixedHeight(FLOAT_NAV_HEIGHT_TALL)
        for i, (page, label, width) in enumerate(zip(pages, labels, widths)):
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedWidth(width)
            if "\n" in label:
                b.setMinimumHeight(44)
            b.setAutoExclusive(True)
            self._group.addButton(b, i)
            b.installEventFilter(self)
            self._nav_btns.append(b)
        self._nav_btns[0].setChecked(True)

        self.home_btn = make_home_button(
            self, side=NAV_ICON_SIDE_TALL if tall else None
        )
        self.home_btn.clicked.connect(self.home_clicked.emit)
        left, right = mount_center_icon_nav(
            lay,
            home_btn=self.home_btn,
            page_btns=self._nav_btns,
            home_gap=HOME_GAP_TALL if tall else None,
        )
        bind_split_wells(
            self,
            home_btn=self.home_btn,
            left_btns=left,
            right_btns=right,
        )
        attach_hover_bubble(
            self,
            [*self._nav_btns, self.home_btn],
            radius=14.0,
        )
        QTimer.singleShot(0, lambda: self._sync_pill(False))

    def _normalize_page(self, page: str) -> str:
        if self._suite == "assets" and page in (
            "texture",
            "parameter",
            "denoise",
            "meshops",
            "texmesh",
        ):
            return "packages"
        if page not in self._pages:
            return self._pages[0]
        return page

    def _stack_pill(self) -> None:
        self._pill.show()
        stack_selector_chrome(self, [*self._nav_btns, self.home_btn])

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        set_glass_dark(self, mode != "light")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            if self.home_btn.geometry().contains(pt):
                self.home_btn.click()
                event.accept()
                return
        super().mousePressEvent(event)


class AssetsSubNav(_ScrubPillNav):
    """Top bar — Mesh Lods | Texture Params | Texture Editor | Texture Denoiser."""

    PAGES = ("meshops", "texture", "parameter", "denoise")
    LABELS = (
        "Mesh\nLods",
        "Texture\nParams",
        "Texture\nEditor",
        "Texture\nDenoiser",
    )
    WIDTHS = (88, 92, 92, 108)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages = self.PAGES
        self._page = "meshops"
        self._committed = "meshops"

        lay = QHBoxLayout(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, (page, label, width) in enumerate(zip(self.PAGES, self.LABELS, self.WIDTHS)):
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedWidth(width)
            if "\n" in label:
                b.setMinimumHeight(44)
            b.setAutoExclusive(True)
            self._group.addButton(b, i)
            b.installEventFilter(self)
            self._nav_btns.append(b)
        self._nav_btns[0].setChecked(True)

        btns = mount_page_only_nav(lay, self._nav_btns)
        bind_page_well(self, btns)
        attach_hover_bubble(self, self._nav_btns, radius=14.0)
        QTimer.singleShot(0, lambda: self._sync_pill(False))

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        set_glass_dark(self, mode != "light")
