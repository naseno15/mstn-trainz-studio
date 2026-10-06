"""Assets Tools host — native Packages · Texture · LM · KUID (no exe launch)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QVBoxLayout,
    QWidget,
)

from ...io.cdp import format_bytes
from ...io.chump import (
    chump_to_text,
    pack_text_to_chump_file,
    read_chump,
    text_to_chump,
    write_chump,
)
from ...io.lm import LmFile, LmMesh, format_lm_txt, read_lm_txt, write_lm_txt
from ...io.image_prep import process_image
from ...io.texture import (
    IMAGE_EXTS,
    check_texture_txt,
    default_texture_keys,
    format_report,
    format_texture_txt,
    keys_for_image,
    material_family,
    parse_texture_txt,
    probe_image,
    scan_folder,
    sort_texture_paths,
    write_texture_txt,
)
from ...io.ve39 import fix_ve39, scan_ve39
from ..code_edit import CodeEdit, apply_code_edit_theme
from ..frost import (
    FrostGlassFrame,
    glass_is_dark,
    prepare_frost_scroll,
    set_glass_dark,
)
from ..motion import (
    animate_splitter_sizes,
    apple_pop_pill,
    attach_hover_bubble,
    clear_button_hover_chrome,
    fade_widget,
    slide_to,
    stack_selector_chrome,
    stop_slide,
)

# Texture / Mesh right props column — wider than Packages viewer rail.
_RIGHT_DOCK_MIN = 480
_RIGHT_DOCK_MAX = 780
_RIGHT_DOCK_DEFAULT = 600
# Longer + InOutCubic + frozen page paint = silk (setSizes every frame was janky).
_DOCK_ANIM_MS = 560
_DOCK_TICK_MS = 24
from ..smooth_scroll import enable_smooth_scroll_area, enable_smooth_table
from ..theme import app_font
from .kuid import count_kuids, describe_kuid, normalize_list
from .nav import AccentPill, AssetsPageNav, AssetsSubNav
from .packages import PackagesPage
from .sidebar import AssetsSidebar


class _PageSlideHost(QWidget):
    """Horizontal page strip — Texture ↔ Mesh Ops (clipped scroll, animated)."""

    def __init__(self, pages: list[QWidget], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pages = list(pages)
        self._index = 0
        self._anim: QPropertyAnimation | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        self._strip = QWidget()
        strip_lay = QHBoxLayout(self._strip)
        strip_lay.setContentsMargins(0, 0, 0, 0)
        strip_lay.setSpacing(0)
        for page in self._pages:
            page.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            strip_lay.addWidget(page)
        self._scroll.setWidget(self._strip)
        # After setWidget — QScrollArea turns autofill on the body (dark Base slabs).
        prepare_frost_scroll(self._scroll)
        root.addWidget(self._scroll, 1)

    def set_index(self, index: int, *, animate: bool = True) -> None:
        index = max(0, min(int(index), len(self._pages) - 1))
        changed = index != self._index
        self._index = index
        self._sync_geometry(animate=animate and changed)

    def _sync_geometry(self, *, animate: bool) -> None:
        vp = self._scroll.viewport()
        w = max(1, vp.width())
        h = max(1, vp.height())
        n = max(1, len(self._pages))
        for page in self._pages:
            page.setFixedSize(w, h)
        self._strip.resize(w * n, h)
        bar = self._scroll.horizontalScrollBar()
        target = self._index * w
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        if animate and abs(bar.value() - target) > 2:
            anim = QPropertyAnimation(bar, b"value", self)
            anim.setDuration(420)
            anim.setStartValue(bar.value())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            def _clear(a: QPropertyAnimation = anim) -> None:
                if self._anim is a:
                    self._anim = None

            self._anim = anim
            anim.finished.connect(_clear)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        else:
            bar.setValue(target)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_geometry(animate=False)

_LM_MESH_EXTS = {".trainzmesh", ".im", ".fbx"}
_LM_CALC_POINTS = ("center", "near", "far")
_LM_COL_LOD, _LM_COL_WIDTH, _LM_COL_NAME = 0, 1, 2
_LM_ROLE_SOURCE = int(Qt.ItemDataRole.UserRole)

_TEX_OMIT = "—"
_TEX_TILE_OPTS = ("st", "s", "t", "none", _TEX_OMIT)
_TEX_USAGE_OPTS = (_TEX_OMIT, "albedo", "normal", "parameter")
_TEX_NORMAL_OPTS = (_TEX_OMIT, "none", "normalmap")
_TEX_COMPRESS_OPTS = (_TEX_OMIT, "none", "dxt1", "dxt3", "dxt5")
_TEX_ROLE_PATH = int(Qt.ItemDataRole.UserRole)
_TEX_ROLE_FAMILY = int(Qt.ItemDataRole.UserRole) + 1
_TEX_ROLE_MAP = int(Qt.ItemDataRole.UserRole) + 2
_TEX_COL_NAME, _TEX_COL_DIMS, _TEX_COL_CH, _TEX_COL_SIZE, _TEX_COL_STATUS = 0, 1, 2, 3, 4
_TEX_ROLE_COLORS = {
    "albedo": ("#30d158", QColor(48, 209, 88, 36)),
    "normal": ("#64d2ff", QColor(100, 210, 255, 36)),
    "parameter": ("#ff9f0a", QColor(255, 159, 10, 36)),
}
_TEX_ROLE_BADGE = {"albedo": "A", "normal": "N", "parameter": "P"}
_PREP_RESIZE_OPTS = ("%", "exact", "max", "PoT")
_PREP_RESIZE_MAP = {"%": "percentage", "exact": "exact", "max": "max", "PoT": "pot"}
_PREP_MAP_OPTS = ("auto", "albedo", "normal", "param")
_PREP_MAP_MODE = {"auto": "auto", "albedo": "albedo", "normal": "normal", "param": "parameter"}
_PREP_FMT_OPTS = ("SAME", "PNG", "TGA", "JPG")


class _TexNameCell(QWidget):
    """Finder-style badge + title / subtitle for Texture rows."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        badge: str,
        color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(10)
        mark = QLabel(badge)
        mark.setObjectName("pkgFinderBadge")
        mark.setFixedSize(28, 28)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            f"QLabel#pkgFinderBadge {{"
            f"background: {color}33; color: {color}; border-radius: 8px;"
            f"font-weight: 700; font-size: 12px;}}"
        )
        lay.addWidget(mark)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("pkgFinderTitle")
        t.setFont(app_font(12, QFont.Weight.DemiBold))
        text.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("pkgFinderSub")
            s.setFont(app_font(10, QFont.Weight.Normal))
            text.addWidget(s)
        lay.addLayout(text, 1)


class _TexPrepWorker(QThread):
    """Resize / VE39 scan+fix / catalog (probe+VE39) off the UI thread."""

    line = Signal(str)
    catalog_row = Signal(object)  # dict: path + probe + ve39
    finished_counts = Signal(int, int)

    def __init__(self, kind: str, paths: list[Path], opts: dict, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._paths = list(paths)
        self._opts = dict(opts)

    def run(self) -> None:
        ok = fail = 0
        if self._kind == "resize":
            for path in self._paths:
                if self.isInterruptionRequested():
                    break
                good, out, msg = process_image(path, **self._opts)
                if good:
                    ok += 1
                    self.line.emit(f"OK  {path.name} → {out.parent.name}/{out.name}  {msg}")
                else:
                    fail += 1
                    self.line.emit(f"FAIL  {path.name}  {msg}")
        elif self._kind == "catalog":
            for path in self._paths:
                if self.isInterruptionRequested():
                    break
                probe = probe_image(path)
                ve = scan_ve39(path)
                status = "—"
                if probe.error and not (probe.width and probe.height):
                    fail += 1
                    status = "ERR"
                    self.line.emit(f"ERR  {path.name}  {probe.error}")
                elif ve.get("error"):
                    fail += 1
                    status = "ERR"
                    self.line.emit(f"ERR  {path.name}  {ve['error']}")
                elif ve.get("uniform"):
                    ok += 1
                    status = f"VE39 {ve.get('color_hex', '')}".strip()
                    self.line.emit(
                        f"UNIFORM  {path.name}  {ve.get('size', '')}  {ve.get('color_hex', '')}"
                    )
                else:
                    status = "OK"
                    self.line.emit(
                        f"ok  {path.name}  {probe.dims}  {probe.channel_label}  "
                        f"{format_bytes(probe.file_bytes)}"
                    )
                self.catalog_row.emit(
                    {
                        "path": path,
                        "dims": probe.dims,
                        "channels": probe.channel_label,
                        "bytes": probe.file_bytes,
                        "status": status,
                        "uniform": bool(ve.get("uniform")),
                        "error": probe.error or ve.get("error") or "",
                    }
                )
        elif self._kind == "ve39_scan":
            for path in self._paths:
                if self.isInterruptionRequested():
                    break
                row = scan_ve39(path)
                if row["error"]:
                    fail += 1
                    self.line.emit(f"ERR  {path.name}  {row['error']}")
                    continue
                if row["uniform"]:
                    ok += 1
                    self.line.emit(
                        f"UNIFORM  {path.name}  {row['size']}  {row['color_hex']}"
                    )
                else:
                    self.line.emit(f"ok  {path.name}  {row['size']}  not uniform")
        else:  # ve39_fix
            for path in self._paths:
                if self.isInterruptionRequested():
                    break
                good, msg = fix_ve39(path, **self._opts)
                if good:
                    ok += 1
                    self.line.emit(f"FIXED  {path.name}  {msg}")
                elif msg.startswith("not uniform"):
                    self.line.emit(f"skip  {path.name}  {msg}")
                else:
                    fail += 1
                    self.line.emit(f"FAIL  {path.name}  {msg}")
        self.finished_counts.emit(ok, fail)


def _lm_drop_paths(urls: list) -> tuple[list[Path], list[Path]]:
    """Split local drop URLs into mesh files vs *.lm.txt."""
    meshes: list[Path] = []
    lms: list[Path] = []
    for url in urls:
        if not url.isLocalFile():
            continue
        raw = url.toLocalFile()
        if not raw:
            continue
        p = Path(raw)
        name = p.name.lower()
        if name.endswith(".lm.txt") or name.endswith(".lm"):
            lms.append(p)
        elif p.suffix.lower() in _LM_MESH_EXTS:
            meshes.append(p)
    return meshes, lms


def _lm_accept_drag(event: QDragEnterEvent | QDragMoveEvent) -> bool:
    if not event.mimeData().hasUrls():
        return False
    meshes, lms = _lm_drop_paths(event.mimeData().urls())
    return bool(meshes or lms)


def _tex_drop_paths(urls: list) -> tuple[list[Path], list[Path]]:
    """Split local drop URLs into images vs *.texture.txt."""
    images: list[Path] = []
    texts: list[Path] = []
    for url in urls:
        if not url.isLocalFile():
            continue
        raw = url.toLocalFile()
        if not raw:
            continue
        p = Path(raw)
        name = p.name.lower()
        if name.endswith(".texture.txt") or (
            p.suffix.lower() == ".texture" and not name.endswith(".texture.txt")
        ):
            texts.append(p)
        elif p.suffix.lower() in IMAGE_EXTS:
            images.append(p)
    return images, texts


def _tex_accept_drag(event: QDragEnterEvent | QDragMoveEvent) -> bool:
    if not event.mimeData().hasUrls():
        return False
    images, texts = _tex_drop_paths(event.mimeData().urls())
    return bool(images or texts)


class _LmDropZone(QFrame):
    """Visible dashed rail — drop .trainzmesh / .im / .fbx / .lm.txt."""

    paths_dropped = Signal(object)
    lm_dropped = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_over = False
        self.setObjectName("homeDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(88)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(6)
        title = QLabel("Drop mesh files")
        title.setObjectName("homeDropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(app_font(15, QFont.Weight.DemiBold))
        exts = QLabel(".trainzmesh   ·   .im   ·   .fbx   ·   .lm.txt")
        exts.setObjectName("homeDropTypes")
        exts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exts.setFont(app_font(12, QFont.Weight.Medium))
        lay.addWidget(title)
        lay.addWidget(exts)

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self.setProperty("dragOver", active)
        sty = self.style()
        sty.unpolish(self)
        sty.polish(self)
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _lm_accept_drag(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _lm_accept_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        meshes, lms = _lm_drop_paths(event.mimeData().urls() if event.mimeData().hasUrls() else [])
        if lms:
            self.lm_dropped.emit(lms[0])
            event.acceptProposedAction()
            return
        if meshes:
            self.paths_dropped.emit(meshes)
            event.acceptProposedAction()
            return
        event.ignore()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._drag_over:
            color = QColor("#ff5a1f")
        else:
            color = QColor("#98989d")
            color.setAlpha(170)
        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([6.0, 5.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(4, 4, -4, -4), 16, 16)


class _TexDropTable(QTableWidget):
    """Image table — drop target (rail removed) · Finder-style name cells."""

    images_dropped = Signal(object)
    texture_dropped = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 5, parent)
        self.setAcceptDrops(True)
        self._drag_over = False

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _tex_accept_drag(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _tex_accept_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        images, texts = _tex_drop_paths(
            event.mimeData().urls() if event.mimeData().hasUrls() else []
        )
        if texts:
            self.texture_dropped.emit(texts[0])
            event.acceptProposedAction()
            return
        if images:
            self.images_dropped.emit(images)
            event.acceptProposedAction()
            return
        event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        empty = self.rowCount() == 0
        if not empty and not self._drag_over:
            return
        if self._drag_over:
            color = QColor("#ff5a1f")
        else:
            color = QColor("#98989d")
            color.setAlpha(160)
        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([6.0, 5.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = self.viewport().rect().adjusted(6, 6, -6, -6)
        painter.drawRoundedRect(r, 14, 14)
        if empty:
            painter.setPen(QColor("#98989d"))
            painter.setFont(app_font(14, QFont.Weight.DemiBold))
            painter.drawText(
                r,
                int(Qt.AlignmentFlag.AlignCenter),
                "Drop image files here\n.tga · .png · .bmp · .jpg · .dds · .texture.txt",
            )


class _LmDropTable(QTableWidget):
    """Mesh list — same drop types as the rail above."""

    paths_dropped = Signal(object)
    lm_dropped = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self.setAcceptDrops(True)
        self._drag_over = False

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _lm_accept_drag(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _lm_accept_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        meshes, lms = _lm_drop_paths(event.mimeData().urls() if event.mimeData().hasUrls() else [])
        if lms:
            self.lm_dropped.emit(lms[0])
            event.acceptProposedAction()
            return
        if meshes:
            self.paths_dropped.emit(meshes)
            event.acceptProposedAction()
            return
        event.ignore()


def _set_disabled_dim(widget: QWidget, enabled: bool, *, opacity: float = 0.42) -> None:
    """Fade custom-painted controls when disabled (QSS alone misses AccentPill / glass)."""
    if enabled:
        if isinstance(widget.graphicsEffect(), QGraphicsOpacityEffect):
            widget.setGraphicsEffect(None)
        return
    fx = widget.graphicsEffect()
    if not isinstance(fx, QGraphicsOpacityEffect):
        fx = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(fx)
    fx.setOpacity(opacity)


class _ScrollResizeSync(QObject):
    """Debounced remasure when a QScrollArea viewport changes width."""

    def __init__(self, callback, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cb = callback
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._cb)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        del obj
        if event.type() == QEvent.Type.Resize:
            self._timer.start()
        return False


class _SegPills(QFrame):
    """Segmented pills with accent-slide (same motion language as nav / LM calcPoint)."""

    changed = Signal(str)

    def __init__(
        self,
        options: tuple[str, ...],
        *,
        value: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("lmCalcSeg")
        self._options = options
        self._value = value if value in options else options[0]
        self._pill = AccentPill(self, radius=10.0)
        self._pill.lower()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for i, label in enumerate(options):
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            if label == self._value:
                btn.setChecked(True)
            self._group.addButton(btn, i)
            btn.clicked.connect(lambda _=False, v=label: self._pick(v, emit=True))
            lay.addWidget(btn)
            self._buttons.append(btn)
        attach_hover_bubble(self, self._buttons, radius=10.0, pad=1)
        QTimer.singleShot(0, lambda: self._sync_pill(False))

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        # Soft mist track — paint_glass_chip reads near-black on frost side panels.
        dark = glass_is_dark(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if r.width() < 4 or r.height() < 4:
            return
        path = QPainterPath()
        path.addRoundedRect(r, 12.0, 12.0)
        if dark:
            fill = QLinearGradient(r.topLeft(), r.bottomLeft())
            fill.setColorAt(0.0, QColor(255, 255, 255, 38))
            fill.setColorAt(1.0, QColor(255, 255, 255, 18))
            p.fillPath(path, fill)
            p.setPen(QPen(QColor(255, 255, 255, 48), 1.0))
        else:
            fill = QLinearGradient(r.topLeft(), r.bottomLeft())
            fill.setColorAt(0.0, QColor(255, 255, 255, 230))
            fill.setColorAt(1.0, QColor(236, 240, 245, 210))
            p.fillPath(path, fill)
            p.setPen(QPen(QColor(0, 0, 0, 36), 1.0))
        p.drawPath(path)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() != QEvent.Type.EnabledChange:
            return
        on = self.isEnabled()
        for b in self._buttons:
            b.setEnabled(on)
            b.setCursor(
                Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor
            )
        # Hide orange AccentPill — custom paint ignores QSS :disabled.
        # Parent lmField applies opacity; don't double-dim here.
        if on:
            self._sync_pill(False)
        else:
            self._pill.hide()
        ctl = getattr(self, "_hover_ctl", None)
        if ctl is not None and not on:
            ctl.hide_now()
        self.update()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value not in self._options:
            value = self._options[0]
        self._pick(value, emit=False)

    def _pick(self, value: str, *, emit: bool) -> None:
        if not self.isEnabled():
            return
        changed = value != self._value
        self._value = value
        for b, v in zip(self._buttons, self._options):
            b.blockSignals(True)
            b.setChecked(v == value)
            b.blockSignals(False)
        self._sync_pill(True, pop=changed and emit)
        if emit and changed:
            self.changed.emit(value)

    def _sync_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        btn = next((b for b in self._buttons if b.isChecked()), self._buttons[0])
        r = btn.geometry().adjusted(-1, -1, 1, 1)
        if animate and self._pill.width() > 6:
            anim = slide_to(self._pill, r)
            if pop:
                anim.finished.connect(lambda: apple_pop_pill(self._pill))
        else:
            stop_slide(self._pill)
            self._pill.setGeometry(r)
        self._pill.show()
        stack_selector_chrome(self, self._buttons)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_pill(False)


class _LmCalcSeg(_SegPills):
    """calcPoint — center | near | far."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(_LM_CALC_POINTS, value="center", parent=parent)


class AssetsStudioHost(QWidget):
    status = Signal(str)
    enginespec_open = Signal(str, str, str)
    mesh_open = Signal(str)

    def __init__(
        self,
        *,
        on_home: Callable[[], None],
        on_theme: Callable[[], None] | None = None,
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_home = on_home
        self._on_theme = on_theme
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self._page = "packages"
        self._sub_page = "texture"
        self._chump_path: Path | None = None
        self._build()

    def set_theme(self, mode: str) -> None:
        from ..theme import qpalette_for

        self._theme = mode if mode in ("dark", "light") else "dark"
        dark = self._theme != "light"
        self.setPalette(qpalette_for(self._theme))
        self.sidebar.set_theme(self._theme)
        self._nav.set_theme(self._theme)
        if hasattr(self, "_sub_nav"):
            self._sub_nav.set_theme(self._theme)
        for panel in self.findChildren(FrostGlassFrame):
            panel.set_frost(None, dark=dark)
        for seg in self.findChildren(_SegPills):
            set_glass_dark(seg, dark)
        if hasattr(self, "packages_page"):
            self.packages_page.set_theme(self._theme)
        apply_code_edit_theme(self, self._theme)

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(True)  # right dock animates open/shut
        split.setHandleWidth(6)
        self._main_split = split

        self.sidebar = AssetsSidebar()
        self.sidebar.set_theme(self._theme)
        self.sidebar.native_action.connect(self._on_native)
        split.addWidget(self.sidebar)

        mid_host = QWidget()
        mid = QVBoxLayout(mid_host)
        mid.setContentsMargins(10, 0, 0, 0)
        mid.setSpacing(8)

        self.path_lab = QLabel("Assets Tools — native writers")
        self.path_lab.setObjectName("mutedTip")
        mid.addWidget(self.path_lab)

        # Right props dock — sibling of left sidebar (Mesh Studio editor dock).
        # Built before pages so Texture / Mesh Ops can mount into it.
        self._right_dock_host = QWidget()
        self._right_dock_host.setMinimumWidth(0)
        self._right_dock_host.setMaximumWidth(_RIGHT_DOCK_MAX)
        self._right_dock_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        dock_lay = QVBoxLayout(self._right_dock_host)
        dock_lay.setContentsMargins(10, 0, 0, 0)
        dock_lay.setSpacing(0)
        self._right_dock = QStackedWidget()
        self._right_dock.setObjectName("assetsRightDock")
        self._right_dock.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        dock_lay.addWidget(self._right_dock, 1)
        self._right_dock_host.hide()
        self._dock_width_saved = _RIGHT_DOCK_DEFAULT
        self._dock_animating = False

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_packages_page())  # 0
        self._stack.addWidget(self._build_config_page())  # 1
        self._stack.addWidget(self._build_texmesh_page())  # 2 Texture / Mesh
        self._stack.addWidget(self._build_kuid_page())  # 3
        mid.addWidget(self._stack, 1)
        apply_code_edit_theme(self, self._theme)

        nav_wrap = QHBoxLayout()
        nav_wrap.addStretch(1)
        self._nav = AssetsPageNav()
        self._nav.page_changed.connect(self._on_page)
        self._nav.home_clicked.connect(self._on_home)
        self._nav.theme_clicked.connect(self._theme_clicked)
        self._nav.set_theme(self._theme)
        nav_wrap.addWidget(self._nav)
        nav_wrap.addStretch(1)
        mid.addLayout(nav_wrap)

        split.addWidget(mid_host)
        split.addWidget(self._right_dock_host)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        # Start with dock collapsed — Texture / Mesh opens it with a slide.
        split.setSizes([400, 1420, 0])
        root.addWidget(split, 1)

    def _glass(self) -> QFrame:
        f = QFrame()
        f.setObjectName("glassPanel")
        return f

    def _title(self, text: str) -> QLabel:
        t = QLabel(text)
        t.setObjectName("welcomeTitle")
        t.setFont(app_font(16, QFont.Weight.Bold))
        return t

    # ── pages ────────────────────────────────────────────────

    def _build_packages_page(self) -> QWidget:
        self.packages_page = PackagesPage()
        self.packages_page.set_theme(self._theme)
        self.packages_page.status.connect(self._msg)
        self.packages_page.enginespec_open.connect(self.enginespec_open.emit)
        self.packages_page.mesh_open.connect(self.mesh_open.emit)
        self.sidebar.mount_packages_queue(self.packages_page.queue_rail)
        return self.packages_page

    def show_packages(self) -> None:
        self._on_page("packages")

    def _build_config_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        pl.addWidget(self._title("Config / chump"))
        tip = QLabel(
            "Edit config.chump as text (ChumpLib-style), save binary, "
            "or pack / export config.txt."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        pl.addWidget(tip)
        self.chump_edit = CodeEdit(syntax="trainzconfig")
        self.chump_edit.setPlaceholderText(
            'Open config.chump — edit like config.txt\n'
            'username  "My Asset"\nkind  "traincar"\nkuid  <kuid:1:2>\n…'
        )
        pl.addWidget(self.chump_edit, 1)
        lay.addWidget(panel, 1)
        return page

    def _build_texmesh_page(self) -> QWidget:
        """Grouped hub — top sub-nav Texture | Mesh Ops + slide content."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        nav_wrap = QHBoxLayout()
        nav_wrap.addStretch(1)
        self._sub_nav = AssetsSubNav()
        self._sub_nav.page_changed.connect(self._on_sub_page)
        self._sub_nav.set_theme(self._theme)
        nav_wrap.addWidget(self._sub_nav)
        nav_wrap.addStretch(1)
        lay.addLayout(nav_wrap)

        self._sub_slide = _PageSlideHost(
            [self._build_texture_page(), self._build_meshops_page()]
        )
        lay.addWidget(self._sub_slide, 1)
        return page

    def _build_texture_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        pl.addWidget(self._title("Texture.txt"))
        tip = QLabel(
            "Drop PBR maps onto the table — groups albedo/normal/parameter. "
            "Dims · channels · size · VE39 auto-scan. "
            "Double-click a row to select the whole set."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        pl.addWidget(tip)

        mid = QSplitter(Qt.Orientation.Vertical)
        mid.setChildrenCollapsible(False)
        mid.setHandleWidth(6)

        list_host = QWidget()
        lh = QVBoxLayout(list_host)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(4)
        list_lab = QLabel("Images · PBR sets — drop files onto the table")
        list_lab.setObjectName("mutedTip")
        lh.addWidget(list_lab)
        self.tex_list = _TexDropTable()
        self.tex_list.setObjectName("pkgFinder")
        self.tex_list.setHorizontalHeaderLabels(
            ["Name", "Dims", "Ch", "Size", "Status"]
        )
        hdr = self.tex_list.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(_TEX_COL_NAME, hdr.ResizeMode.Stretch)
        # Wide enough for 4096×4096 / RGB (no α) / 48.0 MB (was eliding to "11…").
        for col, w in (
            (_TEX_COL_DIMS, 118),
            (_TEX_COL_CH, 114),
            (_TEX_COL_SIZE, 96),
            (_TEX_COL_STATUS, 72),
        ):
            hdr.setSectionResizeMode(col, hdr.ResizeMode.Fixed)
            self.tex_list.setColumnWidth(col, w)
        self.tex_list.verticalHeader().setVisible(False)
        self.tex_list.setShowGrid(False)
        self.tex_list.setWordWrap(False)
        self.tex_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tex_list.setAlternatingRowColors(False)
        self.tex_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tex_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tex_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tex_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tex_list.setToolTip(
            "A/N/P badge = albedo / normal / parameter. "
            "Double-click a row = select whole PBR set. Drop images here."
        )
        enable_smooth_table(self.tex_list)
        self.tex_list.images_dropped.connect(self._tex_add_from_paths)
        self.tex_list.texture_dropped.connect(self._tex_load_path)
        self.tex_list.itemSelectionChanged.connect(self._tex_list_selection_changed)
        self.tex_list.cellDoubleClicked.connect(self._tex_list_dbl)
        self._tex_paths: list[Path] = []
        self._tex_meta: dict[Path, dict] = {}
        self._tex_select_guard = False
        lh.addWidget(self.tex_list, 1)
        mid.addWidget(list_host)

        prev_host = QWidget()
        ph = QVBoxLayout(prev_host)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(4)
        prev_row = QHBoxLayout()
        prev_lab = QLabel("texture.txt preview")
        prev_lab.setObjectName("mutedTip")
        prev_row.addWidget(prev_lab)
        prev_row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._tex_refresh_preview)
        prev_row.addWidget(refresh)
        ph.addLayout(prev_row)

        # preview | check/scan side-by-side (was stacked)
        twin = QSplitter(Qt.Orientation.Horizontal)
        twin.setChildrenCollapsible(False)
        twin.setHandleWidth(6)
        self.tex_preview = CodeEdit(syntax="trainzconfig")
        self.tex_preview.setReadOnly(True)
        self.tex_preview.setPlaceholderText("Drop an image → preview")
        twin.addWidget(self.tex_preview)
        self.tex_log = CodeEdit(syntax="plain")
        self.tex_log.setReadOnly(True)
        self.tex_log.setPlaceholderText("Check / scan results…")
        twin.addWidget(self.tex_log)
        twin.setStretchFactor(0, 1)
        twin.setStretchFactor(1, 1)
        twin.setSizes([420, 420])
        ph.addWidget(twin, 1)
        mid.addWidget(prev_host)
        mid.setStretchFactor(0, 1)
        mid.setStretchFactor(1, 1)
        mid.setSizes([320, 400])
        pl.addWidget(mid, 1)
        lay.addWidget(panel, 1)

        # Full-height right dock (sibling of left sidebar — not under path/nav).
        props = FrostGlassFrame(radius=14.0)
        props.setObjectName("sidePanel")
        props.setMinimumWidth(0)
        props.setMaximumWidth(16777215)
        props.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        props.set_dark(self._theme != "light")
        self._tex_props = props
        pr = QVBoxLayout(props)
        pr.setContentsMargins(16, 14, 16, 16)
        pr.setSpacing(8)

        props_title = QLabel("Texture Params")
        props_title.setObjectName("welcomeTitle")
        props_title.setFont(app_font(14, QFont.Weight.DemiBold))
        self._tex_props_title = props_title
        pr.addWidget(props_title)

        # Lazy import — SideTabStrip lives in app.py (avoid circular at module load).
        from ..app import SideTabStrip

        self._tex_side_tabs = SideTabStrip(("Texture Params", "Resize → _prep"))
        self._tex_side_tabs.index_changed.connect(self._tex_on_side_tab)
        pr.addWidget(self._tex_side_tabs)

        self._tex_side_stack = QStackedWidget()
        self._tex_side_stack.setObjectName("editorTabStack")

        # ── tab 0: Texture Params ────────────────────────────
        params_page = QWidget()
        params_page.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        pbl = QVBoxLayout(params_page)
        pbl.setContentsMargins(0, 0, 0, 0)
        pbl.setSpacing(10)

        self.tex_primary = QLineEdit()
        self.tex_primary.setPlaceholderText("body_albedo.tga")
        self.tex_primary.textChanged.connect(lambda _="": self._tex_refresh_preview())
        self.tex_alpha = QLineEdit()
        self.tex_alpha.setPlaceholderText("optional alpha map…")
        self.tex_alpha.textChanged.connect(lambda _="": self._tex_refresh_preview())

        self.tex_tile = _SegPills(_TEX_TILE_OPTS, value="st")
        self.tex_tile.changed.connect(lambda _="": self._tex_refresh_preview())
        self.tex_usage = _SegPills(_TEX_USAGE_OPTS, value=_TEX_OMIT)
        self.tex_usage.changed.connect(lambda _="": self._tex_on_usage_changed())
        self.tex_normal = _SegPills(_TEX_NORMAL_OPTS, value=_TEX_OMIT)
        self.tex_normal.changed.connect(lambda _="": self._tex_refresh_preview())
        self.tex_compress = _SegPills(_TEX_COMPRESS_OPTS, value=_TEX_OMIT)
        self.tex_compress.changed.connect(lambda _="": self._tex_refresh_preview())

        pbl.addWidget(self._lm_field("Primary", self.tex_primary))
        pbl.addWidget(self._lm_field("Alpha", self.tex_alpha))
        pbl.addWidget(self._lm_field("Tile", self.tex_tile))
        pbl.addWidget(self._lm_field("UsageHint", self.tex_usage))
        pbl.addWidget(self._lm_field("NormalMapHint", self.tex_normal))
        pbl.addWidget(self._lm_field("Compression", self.tex_compress))
        self._tex_side_stack.addWidget(params_page)

        # ── tab 1: Batch Resize → _prep/ ──────────────────────
        prep_page = QWidget()
        prep_page.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        prep_bl = QVBoxLayout(prep_page)
        prep_bl.setContentsMargins(0, 0, 0, 0)
        prep_bl.setSpacing(10)

        prep_title = QLabel("Batch Resize → _prep/")
        prep_title.setObjectName("welcomeTitle")
        prep_title.setFont(app_font(13, QFont.Weight.DemiBold))
        prep_bl.addWidget(prep_title)
        prep_tip = QLabel(
            "Scales images from the list into a sibling _prep/ folder "
            "(keeps originals). Map type picks the filter; format / PoT / "
            "flip-green apply when you run Resize → _prep…. "
            "VE39 scan/fix are separate and always available."
        )
        prep_tip.setObjectName("mutedTip")
        prep_tip.setWordWrap(True)
        prep_bl.addWidget(prep_tip)

        self.prep_enabled = QCheckBox("Use these settings for Resize → _prep…")
        self.prep_enabled.setChecked(False)  # default OFF — opt-in
        self.prep_enabled.setToolTip(
            "On = use Map / Resize / Format for sidebar Resize → _prep…"
        )
        self.prep_enabled.toggled.connect(self._prep_set_enabled)
        prep_bl.addWidget(self.prep_enabled)

        self.prep_map = _SegPills(_PREP_MAP_OPTS, value="auto")
        self.prep_resize = _SegPills(_PREP_RESIZE_OPTS, value="max")
        self.prep_resize.changed.connect(lambda _="": self._prep_sync_spins())
        self.prep_fmt = _SegPills(_PREP_FMT_OPTS, value="SAME")
        self.prep_map_field = self._lm_field("Map", self.prep_map)
        self.prep_resize_field = self._lm_field("Resize", self.prep_resize)
        self.prep_fmt_field = self._lm_field("Format", self.prep_fmt)
        prep_bl.addWidget(self.prep_map_field)
        prep_bl.addWidget(self.prep_resize_field)
        prep_bl.addWidget(self.prep_fmt_field)

        self.prep_percent = self._prep_spin(1, 100, 50, suffix="%")
        self.prep_w = self._prep_spin(1, 16384, 1024, suffix="px")
        self.prep_h = self._prep_spin(1, 16384, 1024, suffix="px")
        self.prep_max = self._prep_spin(1, 16384, 2048, suffix="px")
        self.prep_percent_field = self._lm_field("Percent", self.prep_percent)
        self.prep_exact_field = QFrame()
        self.prep_exact_field.setObjectName("lmField")
        ex = QVBoxLayout(self.prep_exact_field)
        ex.setContentsMargins(12, 10, 12, 10)
        ex.setSpacing(6)
        ex_lab = QLabel("Exact W × H")
        ex_lab.setObjectName("lmFieldLabel")
        ex.addWidget(ex_lab)
        ex_row = QHBoxLayout()
        ex_row.setSpacing(6)
        ex_row.addWidget(self.prep_w, 1)
        ex_row.addWidget(self.prep_h, 1)
        ex.addLayout(ex_row)
        self.prep_max_field = self._lm_field("Max dim", self.prep_max)
        prep_bl.addWidget(self.prep_percent_field)
        prep_bl.addWidget(self.prep_exact_field)
        prep_bl.addWidget(self.prep_max_field)

        self.prep_flip_green = QCheckBox("Flip green (DX ↔ GL)")
        self.prep_flip_green.setObjectName("mutedTip")
        prep_bl.addWidget(self.prep_flip_green)
        self.prep_pot_down = QCheckBox("PoT round down")
        self.prep_pot_down.setChecked(True)
        self.prep_pot_down.setObjectName("mutedTip")
        prep_bl.addWidget(self.prep_pot_down)
        self._tex_side_stack.addWidget(prep_page)

        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_lay.addWidget(self._tex_side_stack)
        scroll.setWidget(body)
        prepare_frost_scroll(scroll)
        enable_smooth_scroll_area(scroll)
        self._tex_side_scroll = scroll
        self._tex_side_scroll_body = body
        # Remeasure when dock width changes — word-wrap tip height depends on width.
        sync_filt = _ScrollResizeSync(self._tex_sync_side_scroll, scroll)
        scroll.viewport().installEventFilter(sync_filt)
        self._tex_scroll_resize_filt = sync_filt
        pr.addWidget(scroll, 1)
        self._right_dock.addWidget(props)  # index 0 — Texture
        self._tex_source_dir: Path | None = None
        self._tex_prep_worker: _TexPrepWorker | None = None
        self._prep_sync_spins()
        self._prep_set_enabled()
        self._tex_on_side_tab(0)
        self._tex_refresh_preview()
        QTimer.singleShot(0, self._tex_sync_side_scroll)
        return page

    def _tex_on_side_tab(self, index: int) -> None:
        idx = int(index)
        stack = self._tex_side_stack
        # Instant swap — fade_stack_page + QGraphicsOpacityEffect on frost
        # side panels crashes Win / leaves options stuck invisible (opacity 0).
        for i in range(stack.count()):
            page = stack.widget(i)
            if page is not None and page.graphicsEffect() is not None:
                page.setGraphicsEffect(None)
        stack.setCurrentIndex(idx)
        titles = ("Texture Params", "Batch Resize → _prep/")
        self._tex_props_title.setText(titles[max(0, min(idx, len(titles) - 1))])
        self._tex_sync_side_scroll()
        QTimer.singleShot(0, self._tex_sync_side_scroll)

    def _tex_page_need_height(self, page: QWidget, width: int) -> int:
        """Content height at ``width`` — word-wrapped tips need heightForWidth."""
        lay = page.layout()
        if lay is None:
            return max(page.sizeHint().height(), page.minimumSizeHint().height(), 1)
        m = lay.contentsMargins()
        inner = max(1, int(width) - m.left() - m.right())
        total = m.top() + m.bottom()
        spaced = False
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is None or not w.isVisibleTo(page):
                continue
            if spaced:
                total += lay.spacing()
            spaced = True
            if isinstance(w, QLabel) and w.wordWrap():
                total += max(int(w.heightForWidth(inner)), w.sizeHint().height())
            else:
                total += max(w.sizeHint().height(), w.minimumSizeHint().height())
        return max(total, page.sizeHint().height(), page.minimumSizeHint().height(), 1)

    def _tex_sync_side_scroll(self, *_args) -> None:
        """Size scroll body to active tab so the wheel/bar can move (Mesh sidebar)."""
        stack = getattr(self, "_tex_side_stack", None)
        body = getattr(self, "_tex_side_scroll_body", None)
        scroll = getattr(self, "_tex_side_scroll", None)
        if stack is None or body is None:
            return
        cur = stack.currentWidget()
        if cur is None:
            return
        vw = max(1, scroll.viewport().width()) if scroll is not None else max(1, cur.width())
        for i in range(stack.count()):
            page = stack.widget(i)
            if page is None:
                continue
            if page is cur:
                page.setMinimumHeight(0)
                page.updateGeometry()
                need = self._tex_page_need_height(page, vw)
                page.setMinimumHeight(need)
            else:
                page.setMinimumHeight(0)
        stack.setMinimumHeight(cur.minimumHeight())
        stack.updateGeometry()
        body.setMinimumHeight(max(cur.minimumHeight(), 1))
        body.adjustSize()

    def _prep_spin(self, lo: int, hi: int, value: int, *, suffix: str = "") -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(value)
        if suffix:
            sp.setSuffix(f" {suffix}" if not suffix.startswith("%") else suffix)
        sp.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        return sp

    def _prep_sync_spins(self) -> None:
        mode = self.prep_resize.value()
        self.prep_percent_field.setVisible(mode == "%")
        self.prep_exact_field.setVisible(mode == "exact")
        self.prep_max_field.setVisible(mode == "max")
        self.prep_pot_down.setVisible(mode == "PoT")
        self._prep_apply_enabled_state()

    def _prep_set_enabled(self, _on: bool = True) -> None:
        self._prep_apply_enabled_state()

    def _prep_apply_enabled_state(self) -> None:
        on = bool(self.prep_enabled.isChecked())
        # Field cards — dim here; SegPills changeEvent dims chips + hides accent pill.
        dim_cards = (
            self.prep_map_field,
            self.prep_resize_field,
            self.prep_fmt_field,
            self.prep_percent_field,
            self.prep_exact_field,
            self.prep_max_field,
            self.prep_flip_green,
            self.prep_pot_down,
        )
        for w in dim_cards:
            w.setEnabled(on)
            _set_disabled_dim(w, on)
        for w in (
            self.prep_map,
            self.prep_resize,
            self.prep_fmt,
            self.prep_percent,
            self.prep_w,
            self.prep_h,
            self.prep_max,
        ):
            w.setEnabled(on)
        self.sidebar.set_action_enabled("tex_resize", on)
        self._tex_sync_side_scroll()

    def _lm_field(self, label: str, widget: QWidget) -> QFrame:
        box = QFrame()
        box.setObjectName("lmField")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lab = QLabel(label)
        lab.setObjectName("lmFieldLabel")
        lay.addWidget(lab)
        lay.addWidget(widget)
        return box

    def _lm_spin(self, *, lo: float, hi: float, value: float, step: float = 0.01) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(3)
        sp.setSingleStep(step)
        sp.setValue(value)
        sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        sp.valueChanged.connect(lambda _=0.0: self._lm_refresh_preview())
        return sp

    def _build_meshops_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        pl.addWidget(self._title("LM.txt LOD"))
        tip = QLabel(
            "Drop meshes → Save all writes one .lm.txt each. "
            "Tick LOD to combine those rows into a shared LOD table instead."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        pl.addWidget(tip)

        self.lm_drop = _LmDropZone()
        self.lm_drop.paths_dropped.connect(self._lm_add_from_paths)
        self.lm_drop.lm_dropped.connect(self._lm_load_path)
        pl.addWidget(self.lm_drop)

        mid = QSplitter(Qt.Orientation.Vertical)
        mid.setChildrenCollapsible(False)
        mid.setHandleWidth(6)

        table_host = QWidget()
        th = QVBoxLayout(table_host)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(4)
        table_lab = QLabel("Mesh files")
        table_lab.setObjectName("mutedTip")
        th.addWidget(table_lab)
        self.lm_table = _LmDropTable()
        self.lm_table.setHorizontalHeaderLabels(["LOD", "Width", "Mesh file"])
        self.lm_table.horizontalHeader().setStretchLastSection(True)
        self.lm_table.setColumnWidth(_LM_COL_LOD, 48)
        self.lm_table.setColumnWidth(_LM_COL_WIDTH, 72)
        self.lm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        enable_smooth_table(self.lm_table)
        self.lm_table.paths_dropped.connect(self._lm_add_from_paths)
        self.lm_table.lm_dropped.connect(self._lm_load_path)
        self.lm_table.itemChanged.connect(lambda _=None: self._lm_refresh_preview())
        th.addWidget(self.lm_table, 1)
        mid.addWidget(table_host)

        prev_host = QWidget()
        ph = QVBoxLayout(prev_host)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(4)
        prev_row = QHBoxLayout()
        prev_lab = QLabel("lm.txt preview")
        prev_lab.setObjectName("mutedTip")
        prev_row.addWidget(prev_lab)
        prev_row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._lm_refresh_preview)
        prev_row.addWidget(refresh)
        ph.addLayout(prev_row)
        self.lm_preview = CodeEdit(syntax="trainzconfig")
        self.lm_preview.setReadOnly(True)
        self.lm_preview.setPlaceholderText("Drop meshes or Add row → preview")
        ph.addWidget(self.lm_preview, 1)
        mid.addWidget(prev_host)
        mid.setStretchFactor(0, 1)
        mid.setStretchFactor(1, 1)
        mid.setSizes([400, 400])
        pl.addWidget(mid, 1)
        lay.addWidget(panel, 1)

        # Full-height right dock (sibling of left sidebar — not under path/nav).
        props = FrostGlassFrame(radius=14.0)
        props.setObjectName("sidePanel")
        props.setMinimumWidth(0)
        props.setMaximumWidth(16777215)
        props.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        props.set_dark(self._theme != "light")
        self._lm_props = props
        pr = QVBoxLayout(props)
        pr.setContentsMargins(16, 16, 16, 16)
        pr.setSpacing(10)
        props_title = QLabel(".lm.txt params")
        props_title.setObjectName("welcomeTitle")
        props_title.setFont(app_font(14, QFont.Weight.DemiBold))
        pr.addWidget(props_title)

        self.lm_offset = self._lm_spin(lo=0.0, hi=1.0, value=0.01)
        self.lm_calc = _LmCalcSeg()
        self.lm_calc.changed.connect(lambda _="": self._lm_refresh_preview())
        self.lm_mult = self._lm_spin(lo=0.0, hi=10.0, value=1.0, step=0.1)
        self.lm_anim = self._lm_spin(lo=0.0, hi=1.0, value=0.0)
        self.lm_render = self._lm_spin(lo=0.0, hi=1.0, value=0.0)
        self.lm_att = self._lm_spin(lo=0.0, hi=1.0, value=0.06)

        pr.addWidget(self._lm_field("offset", self.lm_offset))
        pr.addWidget(self._lm_field("calcPoint", self.lm_calc))
        pr.addWidget(self._lm_field("multiplier", self.lm_mult))
        pr.addWidget(self._lm_field("animCutOff", self.lm_anim))
        pr.addWidget(self._lm_field("renderCutOff", self.lm_render))
        pr.addWidget(self._lm_field("attachCutOff", self.lm_att))
        pr.addStretch(1)
        self._right_dock.addWidget(props)  # index 1 — Mesh Ops
        return page

    def _build_kuid_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        pl.addWidget(self._title("KUID"))
        tip = QLabel("Paste CM text → normalize. Hex + hash-XX from public KUID format.")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        pl.addWidget(tip)
        self.kuid_in = CodeEdit(syntax="trainzconfig")
        self.kuid_in.setPlaceholderText("Paste KUIDs or CM dependency text…")
        pl.addWidget(self.kuid_in, 1)
        self.kuid_out = CodeEdit(syntax="trainzconfig")
        self.kuid_out.setReadOnly(True)
        self.kuid_out.setPlaceholderText("Normalized / hash output…")
        pl.addWidget(self.kuid_out, 1)
        self.kuid_count = QLabel("0 KUIDs")
        self.kuid_count.setObjectName("mutedTip")
        pl.addWidget(self.kuid_count)
        lay.addWidget(panel, 1)
        return page

    # ── nav / theme ──────────────────────────────────────────

    def _theme_clicked(self) -> None:
        if self._on_theme is not None:
            self._on_theme()

    def _dock_target_sizes(self, *, open_dock: bool) -> list[int]:
        split = self._main_split
        sizes = [int(x) for x in split.sizes()]
        while len(sizes) < 3:
            sizes.append(0)
        total = max(1, sum(sizes) or int(split.width()) or 1800)
        left = sizes[0] if sizes[0] > 80 else min(400, total // 5)
        if open_dock:
            right = int(self._dock_width_saved or _RIGHT_DOCK_DEFAULT)
            right = max(_RIGHT_DOCK_MIN, min(_RIGHT_DOCK_MAX, right))
            mid = max(240, total - left - right)
            # If mid got crushed, shrink right toward min.
            if mid < 240:
                right = max(_RIGHT_DOCK_MIN, total - left - 240)
                mid = max(240, total - left - right)
            return [left, mid, right]
        # Collapse dock — give its width to the mid column (bars stay centered smoothly).
        right = sizes[2]
        if right > 40:
            self._dock_width_saved = right
        return [left, max(240, total - left), 0]

    def _relayout_nav_bars(self) -> None:
        """Snap top/bottom pills after layout (nav resizeEvent also covers live anim)."""
        nav = getattr(self, "_nav", None)
        if nav is not None and not getattr(nav, "_drag", False):
            nav._sync_pill(False)
        sub = getattr(self, "_sub_nav", None)
        if sub is not None and sub.isVisible() and not getattr(sub, "_drag", False):
            sub._sync_pill(False)

    def _freeze_page_paint(self, freeze: bool) -> None:
        """Skip repainting heavy stack pages while the dock width lerps (kills hitch)."""
        stack = getattr(self, "_stack", None)
        if stack is None:
            return
        stack.setUpdatesEnabled(not freeze)
        if not freeze:
            stack.update()

    def _run_dock_anim(self, target: list[int], *, on_done) -> None:
        split = self._main_split
        self._dock_animating = True
        self._freeze_page_paint(True)

        def _finish() -> None:
            self._freeze_page_paint(False)
            self._dock_animating = False
            self._relayout_nav_bars()
            if on_done is not None:
                on_done()

        animate_splitter_sizes(
            split,
            target,
            ms=_DOCK_ANIM_MS,
            min_frame_ms=_DOCK_TICK_MS,
            easing=QEasingCurve.Type.InOutCubic,
            on_done=_finish,
        )

    def _sync_right_dock(self, *, animate: bool = True, after=None) -> None:
        """Show/hide Texture · Mesh Ops props — silk slide; ``after`` runs when settled."""
        host = getattr(self, "_right_dock_host", None)
        dock = getattr(self, "_right_dock", None)
        split = getattr(self, "_main_split", None)
        if host is None or dock is None or split is None:
            if after is not None:
                after()
            return

        want_open = self._page == "texmesh"
        if want_open:
            dock.setCurrentIndex(0 if self._sub_page == "texture" else 1)
            cur = [int(x) for x in split.sizes()]
            already_open = (not host.isHidden()) and len(cur) >= 3 and cur[2] >= 80
            if already_open and not self._dock_animating:
                host.setMinimumWidth(_RIGHT_DOCK_MIN)
                QTimer.singleShot(0, self._tex_sync_side_scroll)
                if after is not None:
                    after()
                return
            host.setMinimumWidth(0)
            host.show()
            target = self._dock_target_sizes(open_dock=True)
            if not animate:
                split.setSizes(target)
                host.setMinimumWidth(_RIGHT_DOCK_MIN)
                self._relayout_nav_bars()
                QTimer.singleShot(0, self._tex_sync_side_scroll)
                if after is not None:
                    after()
                return
            if self._dock_animating:
                if after is not None:
                    after()
                return
            if len(cur) >= 3 and cur[2] < 40:
                left, mid, _ = self._dock_target_sizes(open_dock=False)
                split.setSizes([left, mid, 0])

            def _opened() -> None:
                host.setMinimumWidth(_RIGHT_DOCK_MIN)
                QTimer.singleShot(0, self._tex_sync_side_scroll)
                if after is not None:
                    after()

            self._run_dock_anim(target, on_done=_opened)
            return

        host.setMinimumWidth(0)
        target = self._dock_target_sizes(open_dock=False)
        if not animate or host.isHidden():
            split.setSizes(target)
            host.hide()
            self._relayout_nav_bars()
            if after is not None:
                after()
            return
        if self._dock_animating:
            if after is not None:
                after()
            return
        cur_right = split.sizes()[2] if len(split.sizes()) >= 3 else 0
        if cur_right < 8:
            host.hide()
            if after is not None:
                after()
            return

        def _closed() -> None:
            host.hide()
            if after is not None:
                after()

        self._run_dock_anim(target, on_done=_closed)

    def _reveal_sub_nav(self) -> None:
        """Fade top Texture | Mesh Ops bar after the dock has settled (avoids double jank)."""
        sub = getattr(self, "_sub_nav", None)
        if sub is None:
            return
        fade_widget(sub, 0.05, 1.0, 280)
        QTimer.singleShot(0, lambda: sub._sync_pill(False) if hasattr(sub, "_sync_pill") else None)

    def _on_page(self, page: str) -> None:
        # Bottom group + legacy aliases
        if page in ("texture", "meshops"):
            self._sub_page = page
            page = "texmesh"
        idx = {
            "packages": 0,
            "config": 1,
            "texmesh": 2,
            "kuid": 3,
        }.get(page, 0)
        prev = getattr(self, "_page", None)
        changed = prev != page
        entering_tex = page == "texmesh" and prev != "texmesh"
        leaving_tex = prev == "texmesh" and page != "texmesh"
        self._page = page
        # Freeze before the stack swap so the first dock frame isn't a heavy paint.
        if changed and (entering_tex or leaving_tex):
            clear_button_hover_chrome()
            self._freeze_page_paint(True)
        self._stack.setCurrentIndex(idx)
        # Pill slide — no-op if scrub already committed this page
        self._nav.set_page(page, emit=False, animate=True)

        if page == "texmesh":
            self._sub_nav.set_page(self._sub_page, emit=False, animate=(prev == "texmesh"))
            self._sub_slide.set_index(
                0 if self._sub_page == "texture" else 1,
                animate=(prev == "texmesh"),
            )
            label = "Texture" if self._sub_page == "texture" else "Mesh Ops"
        else:
            label = {
                "packages": "Packages",
                "config": "Config",
                "kuid": "KUID",
            }.get(page, page)

        # Defer sidebar rebuild + sub-nav fade until dock motion finishes —
        # running them in parallel with setSizes was the hitch.
        def _after_dock() -> None:
            if page == "texmesh":
                self.sidebar.set_page(self._sub_page, animate=entering_tex)
                if entering_tex:
                    self._reveal_sub_nav()
            else:
                self.sidebar.set_page(page, animate=leaving_tex or changed)

        self._sync_right_dock(animate=changed, after=_after_dock)
        msg = f"Assets Tools — {label}"
        self.path_lab.setText(msg)
        self.status.emit(msg)

    def _on_sub_page(self, page: str) -> None:
        if page not in ("texture", "meshops"):
            page = "texture"
        self._sub_page = page
        self._sub_slide.set_index(0 if page == "texture" else 1, animate=True)
        self.sidebar.set_page(page, animate=True)
        self._sync_right_dock()
        label = "Texture" if page == "texture" else "Mesh Ops"
        msg = f"Assets Tools — {label}"
        self.path_lab.setText(msg)
        self.status.emit(msg)

    def _on_native(self, action: str) -> None:
        handlers = {
            "open_chump": self._open_chump,
            "save_chump": self._save_chump,
            "txt_to_chump": self._txt_to_chump,
            "export_config_txt": self._export_config_txt,
            "open_cdp": self.packages_page.action_open_cdp,
            "pack_cdp": self.packages_page.action_pack_cdp,
            "extract_cdp": self.packages_page.action_extract_cdp,
            "open_tzarc": self.packages_page.action_open_tzarc,
            "extract_tzarc": self.packages_page.action_extract_tzarc,
            "copy_pkg_kuids": self.packages_page.action_copy_kuids,
            "tex_from_image": self._tex_from_image,
            "tex_save": self._tex_save,
            "tex_save_all": self._tex_save_all,
            "tex_resize": self._tex_resize,
            "tex_ve39_scan": self._tex_ve39_scan,
            "tex_ve39_fix": self._tex_ve39_fix,
            "open_texture": self._check_texture_file,
            "scan_folder": self._scan_texture_folder,
            "lm_add": lambda: self._lm_add_row(1.0, "mesh.im"),
            "lm_remove": self._lm_remove_row,
            "lm_load": self._lm_load,
            "lm_save": self._lm_save,
            "normalize_kuids": self._normalize_kuids,
            "kuid_hash": self._kuid_hash,
            "copy_kuids": self._copy_kuids,
        }
        fn = handlers.get(action)
        if fn is not None:
            fn()

    def _msg(self, text: str) -> None:
        self.path_lab.setText(text)
        self.status.emit(text)

    def handle_dropped_paths(self, paths: list[Path]) -> bool:
        """Window-level drop while Assets is active. Returns True if handled."""
        if self._page != "packages" or not hasattr(self, "packages_page"):
            return False
        usable = [
            p
            for p in paths
            if (p.suffix.lower() == ".cdp" and p.is_file())
            or p.is_dir()
            or (p.is_file() and p.name.lower() == "config.txt")
        ]
        if not usable:
            return False
        self.packages_page.add_queue_paths(usable)
        return True

    # ── packages / chump ─────────────────────────────────────

    def _open_chump(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open config.chump",
            str(Path.home()),
            "Chump (*.chump);;CDP/chump (*.chump *.cdp);;All (*.*)",
        )
        if not path:
            return
        p = Path(path)
        try:
            text = chump_to_text(read_chump(p))
        except Exception as exc:
            QMessageBox.warning(self, "config.chump", str(exc))
            return
        self.chump_edit.setPlainText(text)
        self._chump_path = p
        self._msg(f"Opened {p.name}")

    def _save_chump(self) -> None:
        text = self.chump_edit.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "config.chump", "Editor is empty.")
            return
        try:
            chump = text_to_chump(text)
        except Exception as exc:
            QMessageBox.warning(self, "config.chump parse", str(exc))
            return
        start = str(self._chump_path or (Path.home() / "config.chump"))
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save config.chump",
            start,
            "Chump (*.chump);;All (*.*)",
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != ".chump":
            out = out.with_suffix(".chump")
        try:
            write_chump(out, chump)
        except Exception as exc:
            QMessageBox.critical(self, "config.chump save", str(exc))
            return
        self._chump_path = out
        self._msg(f"Wrote {out.name}")

    def _txt_to_chump(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open config.txt (pack to chump)",
            str(Path.home()),
            "Trainz config (config.txt *.txt);;All (*.*)",
        )
        if not path:
            return
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            # Load into editor first so user can review
            chump = text_to_chump(text)
            self.chump_edit.setPlainText(chump_to_text(chump))
        except Exception as exc:
            QMessageBox.warning(self, "config.txt", str(exc))
            return
        dest = p.with_name("config.chump")
        out, _ = QFileDialog.getSaveFileName(
            self, "Save as config.chump", str(dest), "Chump (*.chump);;All (*.*)"
        )
        if not out:
            self._msg(f"Loaded {p.name} into editor (not saved)")
            return
        try:
            pack_text_to_chump_file(self.chump_edit.toPlainText(), Path(out))
        except Exception as exc:
            QMessageBox.critical(self, "Pack chump", str(exc))
            return
        self._chump_path = Path(out)
        self._msg(f"Packed {p.name} → {Path(out).name}")

    def _export_config_txt(self) -> None:
        text = self.chump_edit.toPlainText().strip()
        if not text:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open config.chump to export",
                str(Path.home()),
                "Chump (*.chump);;All (*.*)",
            )
            if not path:
                return
            try:
                text = chump_to_text(read_chump(Path(path)))
            except Exception as exc:
                QMessageBox.warning(self, "Export config.txt", str(exc))
                return
            self.chump_edit.setPlainText(text)
        suggest = str(
            (self._chump_path.parent / "config.txt")
            if self._chump_path is not None
            else (Path.home() / "config.txt")
        )
        out, _ = QFileDialog.getSaveFileName(
            self,
            "Export to config.txt",
            suggest,
            "Trainz config (config.txt);;Text (*.txt);;All (*.*)",
        )
        if not out:
            return
        dest = Path(out)
        if dest.name.lower() != "config.txt" and dest.suffix.lower() != ".txt":
            dest = dest.with_name("config.txt")
        dest.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        self._msg(f"Exported → {dest.name}")

    # ── texture ──────────────────────────────────────────────

    def _tex_seg_val(self, seg: _SegPills) -> str:
        v = seg.value()
        return "" if v == _TEX_OMIT else v

    def _tex_set_seg(self, seg: _SegPills, value: str) -> None:
        seg.set_value(value if value else _TEX_OMIT)

    def _tex_keys(self) -> dict[str, str]:
        keys = default_texture_keys(
            primary=self.tex_primary.text().strip(),
            alpha=self.tex_alpha.text().strip(),
            usage=self._tex_seg_val(self.tex_usage) or None,
            normal=self._tex_seg_val(self.tex_normal) == "normalmap",
            tile=self._tex_seg_val(self.tex_tile),
            compression=self._tex_seg_val(self.tex_compress),
        )
        nm = self._tex_seg_val(self.tex_normal)
        if nm and nm != "normalmap":
            keys["NormalMapHint"] = nm
        return keys

    def _tex_defaults_for_primary(self, primary: str) -> dict[str, str]:
        """Sidebar Tile/Compression + stem-detected UsageHint / NormalMapHint."""
        return keys_for_image(
            primary,
            alpha=self.tex_alpha.text().strip(),
            tile=self._tex_seg_val(self.tex_tile),
            compression=self._tex_seg_val(self.tex_compress),
        )

    def _tex_on_usage_changed(self) -> None:
        usage = self._tex_seg_val(self.tex_usage)
        if usage == "normal":
            self.tex_normal.set_value("normalmap")
        elif usage in ("albedo", "parameter") and self._tex_seg_val(self.tex_normal) == "normalmap":
            self.tex_normal.set_value(_TEX_OMIT)
        self._tex_refresh_preview()

    def _tex_refresh_preview(self) -> None:
        keys = self._tex_keys()
        if not keys.get("Primary"):
            self.tex_preview.setPlainText("Primary=…")
            return
        self.tex_preview.setPlainText(format_texture_txt(keys))

    def _tex_apply_hints_from_stem(self, stem: str) -> None:
        _, role = material_family(stem)
        if role == "normal":
            self.tex_usage.set_value("normal")
            self.tex_normal.set_value("normalmap")
        elif role == "parameter":
            self.tex_usage.set_value("parameter")
            if self._tex_seg_val(self.tex_normal) == "normalmap":
                self.tex_normal.set_value(_TEX_OMIT)
        elif role == "albedo":
            self.tex_usage.set_value("albedo")
            if self._tex_seg_val(self.tex_normal) == "normalmap":
                self.tex_normal.set_value(_TEX_OMIT)

    def _tex_apply_image(self, path: Path, *, as_primary: bool = True) -> None:
        self._tex_source_dir = path.parent
        self._tex_add_list_item(path, select=as_primary)
        if as_primary:
            self.tex_primary.blockSignals(True)
            self.tex_primary.setText(path.name)
            self.tex_primary.blockSignals(False)
            self._tex_apply_hints_from_stem(path.stem)
            self._tex_refresh_preview()

    def _tex_add_list_item(self, path: Path, *, select: bool = False) -> None:
        path = Path(path)
        known = {p.resolve() for p in self._tex_paths}
        is_new = path.resolve() not in known
        if is_new:
            self._tex_paths.append(path)
        self._tex_rebuild_table(select=path if select else None)
        if is_new:
            self._tex_catalog([path], announce=False)

    def _tex_add_from_paths(self, paths: object) -> None:
        images = [Path(p) for p in (paths or [])]
        if not images:
            return
        known = {p.resolve() for p in self._tex_paths}
        fresh: list[Path] = []
        for p in images:
            if p.resolve() in known:
                continue
            self._tex_paths.append(p)
            known.add(p.resolve())
            fresh.append(p)
        self._tex_source_dir = images[0].parent
        self._tex_rebuild_table(select=images[0])
        self.tex_primary.blockSignals(True)
        self.tex_primary.setText(images[0].name)
        self.tex_primary.blockSignals(False)
        self._tex_apply_hints_from_stem(images[0].stem)
        self._tex_refresh_preview()
        need = [
            p
            for p in self._tex_paths
            if p not in self._tex_meta and p.resolve() not in self._tex_meta
        ]
        if need:
            self._tex_catalog(need, announce=bool(fresh))
        self._msg(
            f"Texture ← {images[0].name}"
            + (f" (+{len(images) - 1})" if len(images) > 1 else "")
        )

    def _tex_rebuild_table(self, *, select: Path | None = None) -> None:
        """Fill table grouped by PBR family · role colors · cached probe/VE39."""
        rows = sort_texture_paths(self._tex_paths)
        self._tex_select_guard = True
        self.tex_list.setRowCount(0)
        select_row = -1
        for i, (path, fam, role, set_lab) in enumerate(rows):
            self.tex_list.insertRow(i)
            self.tex_list.setRowHeight(i, 52)
            accent, tint = _TEX_ROLE_COLORS.get(role or "", ("#8e8e93", QColor(142, 142, 147, 22)))
            badge = _TEX_ROLE_BADGE.get(role or "", "·")
            sub = f"{fam} · {set_lab}" if role else set_lab
            self.tex_list.setCellWidget(
                i,
                _TEX_COL_NAME,
                _TexNameCell(path.name, sub, badge=badge, color=accent),
            )
            meta = self._tex_meta.get(path) or self._tex_meta.get(path.resolve()) or {}

            def _cell(text: str, *, align_right: bool = False) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setData(_TEX_ROLE_PATH, path)
                it.setData(_TEX_ROLE_FAMILY, fam)
                it.setData(_TEX_ROLE_MAP, role or "")
                it.setToolTip(str(path))
                it.setBackground(tint)
                if align_right:
                    it.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    it.setForeground(QColor("#98989d"))
                    it.setFont(app_font(11, QFont.Weight.Medium))
                return it

            # Empty text — name is drawn by _TexNameCell (item text was stacking on top).
            name_it = _cell("")
            name_it.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            self.tex_list.setItem(i, _TEX_COL_NAME, name_it)
            self.tex_list.setItem(i, _TEX_COL_DIMS, _cell(str(meta.get("dims", "…"))))
            self.tex_list.setItem(i, _TEX_COL_CH, _cell(str(meta.get("channels", "…"))))
            size_s = (
                format_bytes(int(meta["bytes"]))
                if isinstance(meta.get("bytes"), int) and meta["bytes"] >= 0
                else "…"
            )
            self.tex_list.setItem(i, _TEX_COL_SIZE, _cell(size_s, align_right=True))
            st = str(meta.get("status", "…"))
            st_it = _cell(st)
            if st.startswith("VE39"):
                st_it.setForeground(QColor("#ff453a"))
            elif st == "OK":
                st_it.setForeground(QColor("#30d158"))
            elif st == "ERR":
                st_it.setForeground(QColor("#ff453a"))
            self.tex_list.setItem(i, _TEX_COL_STATUS, st_it)
            if select is not None and path.resolve() == Path(select).resolve():
                select_row = i
        self._tex_select_guard = False
        if select_row >= 0:
            self.tex_list.selectRow(select_row)
            self.tex_list.setCurrentCell(select_row, _TEX_COL_NAME)
        self.tex_list.viewport().update()

    def _tex_row_path(self, row: int) -> Path | None:
        it = self.tex_list.item(row, _TEX_COL_NAME)
        if it is None:
            return None
        path = it.data(_TEX_ROLE_PATH)
        return path if isinstance(path, Path) else None

    def _tex_list_selection_changed(self) -> None:
        if self._tex_select_guard:
            return
        rows = sorted({idx.row() for idx in self.tex_list.selectedIndexes()})
        if not rows:
            return
        path = self._tex_row_path(rows[0])
        if path is None:
            return
        self._tex_source_dir = path.parent
        self.tex_primary.blockSignals(True)
        self.tex_primary.setText(path.name)
        self.tex_primary.blockSignals(False)
        self._tex_apply_hints_from_stem(path.stem)
        self._tex_refresh_preview()
        self._msg(f"Primary ← {path.name}")

    def _tex_list_dbl(self, row: int, col: int) -> None:
        """Double-click any column → select whole PBR family."""
        del col
        it = self.tex_list.item(row, _TEX_COL_NAME)
        if it is None:
            return
        fam = it.data(_TEX_ROLE_FAMILY)
        if not fam:
            return
        self._tex_select_guard = True
        self.tex_list.clearSelection()
        last_col = self.tex_list.columnCount() - 1
        for r in range(self.tex_list.rowCount()):
            cell = self.tex_list.item(r, _TEX_COL_NAME)
            if cell is not None and cell.data(_TEX_ROLE_FAMILY) == fam:
                self.tex_list.setRangeSelected(
                    QTableWidgetSelectionRange(r, 0, r, last_col), True
                )
        self._tex_select_guard = False
        path = self._tex_row_path(row)
        if path is not None:
            self.tex_primary.blockSignals(True)
            self.tex_primary.setText(path.name)
            self.tex_primary.blockSignals(False)
            self._tex_apply_hints_from_stem(path.stem)
            self._tex_refresh_preview()
        self._msg(f"Set ← {fam}")

    def _tex_catalog(self, paths: list[Path], *, announce: bool = False) -> None:
        """Auto probe dims/channels/size + VE39 into the Status column."""
        if not paths:
            return
        if self._prep_busy():
            # ponytail: queue skipped while resize/fix runs — re-drop or VE39 scan
            return
        if announce:
            self.tex_log.setPlainText(f"catalog — {len(paths)} file(s)…\n")
        worker = _TexPrepWorker("catalog", paths, {}, self)
        self._tex_prep_worker = worker
        if announce:
            worker.line.connect(self._tex_prep_line)
        worker.catalog_row.connect(self._tex_catalog_row)
        worker.finished_counts.connect(
            lambda ok, fail, loud=announce: self._tex_catalog_done(ok, fail, announce=loud)
        )
        worker.start()

    def _tex_catalog_row(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        path = payload.get("path")
        if not isinstance(path, Path):
            return
        self._tex_meta[path] = payload
        try:
            self._tex_meta[path.resolve()] = payload
        except OSError:
            pass
        want = path
        try:
            want_res = path.resolve()
        except OSError:
            want_res = path
        for r in range(self.tex_list.rowCount()):
            row_path = self._tex_row_path(r)
            if row_path is None:
                continue
            try:
                same = row_path == want or row_path.resolve() == want_res
            except OSError:
                same = row_path == want
            if not same:
                continue
            dims = self.tex_list.item(r, _TEX_COL_DIMS)
            ch = self.tex_list.item(r, _TEX_COL_CH)
            size = self.tex_list.item(r, _TEX_COL_SIZE)
            st = self.tex_list.item(r, _TEX_COL_STATUS)
            if dims:
                dims.setText(str(payload.get("dims", "—")))
            if ch:
                ch.setText(str(payload.get("channels", "—")))
            if size:
                b = payload.get("bytes")
                size.setText(format_bytes(int(b)) if isinstance(b, int) else "—")
            if st:
                text = str(payload.get("status", "—"))
                st.setText(text)
                if text.startswith("VE39") or text == "ERR":
                    st.setForeground(QColor("#ff453a"))
                elif text == "OK":
                    st.setForeground(QColor("#30d158"))
            break

    def _tex_catalog_done(self, ok: int, fail: int, *, announce: bool = True) -> None:
        # catalog: ok count = uniform VE39 hits
        self._msg(f"Texture catalog — VE39 hits {ok}, errors {fail}")
        if announce:
            self.tex_log.appendPlainText(f"\n— catalog done: VE39={ok} err={fail} —")

    def _tex_apply_keys(self, keys: dict[str, str]) -> None:
        self.tex_primary.blockSignals(True)
        self.tex_alpha.blockSignals(True)
        self.tex_primary.setText(keys.get("Primary", ""))
        self.tex_alpha.setText(keys.get("Alpha", ""))
        self.tex_primary.blockSignals(False)
        self.tex_alpha.blockSignals(False)
        self._tex_set_seg(self.tex_tile, keys.get("Tile", ""))
        self._tex_set_seg(self.tex_usage, keys.get("UsageHint", ""))
        self._tex_set_seg(self.tex_normal, keys.get("NormalMapHint", ""))
        self._tex_set_seg(self.tex_compress, keys.get("Compression", ""))
        self._tex_refresh_preview()

    def _tex_load_path(self, path: object) -> None:
        p = Path(path) if not isinstance(path, Path) else path
        if not p.is_file():
            self._msg(f"Missing {p.name}")
            return
        name = p.name.lower()
        if name.endswith(".texture.txt"):
            try:
                keys = parse_texture_txt(p.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                self._msg(f"Read failed — {exc}")
                return
            self._tex_source_dir = p.parent
            self._tex_apply_keys(keys)
            report = check_texture_txt(p)
            self.tex_log.setPlainText(format_report(report))
            primary = keys.get("Primary", "")
            if primary:
                sibling = p.parent / primary
                if sibling.is_file():
                    self._tex_add_list_item(sibling, select=True)
            self._msg(f"Loaded {p.name}")
            return
        # compiled .texture — check only
        report = check_texture_txt(p)
        self.tex_log.setPlainText(format_report(report))
        self._msg(f"{p.name} — {report.summary}")

    def _tex_from_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Image for Primary=",
            str(self._tex_source_dir or Path.home()),
            "Images (*.tga *.png *.jpg *.jpeg *.bmp *.dds *.hdr);;All (*.*)",
        )
        if not path:
            return
        self._tex_apply_image(Path(path), as_primary=True)
        self._msg(f"Primary ← {Path(path).name}")

    def _tex_save(self) -> None:
        keys = self._tex_keys()
        if not keys.get("Primary"):
            QMessageBox.warning(self, "Texture", "Primary is required.")
            return
        self._tex_refresh_preview()
        suggest = Path(keys["Primary"]).stem + ".texture.txt"
        start = (self._tex_source_dir or Path.home()) / suggest
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save .texture.txt",
            str(start),
            "Trainz texture (*.texture.txt);;All (*.*)",
        )
        if not path:
            return
        out = write_texture_txt(Path(path), keys)
        report = check_texture_txt(out)
        self.tex_log.setPlainText(format_report(report))
        self._msg(f"Wrote {out.name} — {report.summary}")

    def _tex_list_image_paths(self) -> list[Path]:
        return [p for p in self._tex_paths if p.is_file()]

    def _tex_save_all(self) -> None:
        """Write one .texture.txt per listed image — PBR role from stem (TXT Generator style)."""
        images = self._tex_list_image_paths()
        if not images:
            primary = self.tex_primary.text().strip()
            if not primary:
                QMessageBox.warning(self, "Texture", "Drop images first, or set Primary.")
                return
            folder = self._tex_source_dir or Path.home()
            images = [folder / primary] if (folder / primary).is_file() else []
            if not images:
                QMessageBox.warning(self, "Texture", "No image files in the list.")
                return
        parents = {p.parent for p in images}
        if len(parents) == 1:
            folder = next(iter(parents))
        else:
            start = str(self._tex_source_dir or images[0].parent)
            picked = QFileDialog.getExistingDirectory(self, "Save all .texture.txt into…", start)
            if not picked:
                return
            folder = Path(picked)
        written: list[Path] = []
        reports: list[str] = []
        roles: dict[str, int] = {}
        for img in images:
            keys = self._tex_defaults_for_primary(img.name)
            # Alpha only applies to the currently selected Primary row
            if img.name != self.tex_primary.text().strip():
                keys.pop("Alpha", None)
            out = write_texture_txt(folder / f"{img.stem}.texture.txt", keys)
            written.append(out)
            report = check_texture_txt(out)
            reports.append(format_report(report))
            role = keys.get("UsageHint") or "plain"
            roles[role] = roles.get(role, 0) + 1
        self.tex_log.setPlainText("\n\n".join(reports))
        role_bits = ", ".join(f"{n}× {r}" for r, n in sorted(roles.items()))
        self._msg(f"Wrote {len(written)} .texture.txt ({role_bits}) → {folder.name}")

    def _prep_busy(self) -> bool:
        w = self._tex_prep_worker
        return w is not None and w.isRunning()

    def _prep_opts_resize(self) -> dict:
        return {
            "mode": _PREP_MAP_MODE.get(self.prep_map.value(), "auto"),
            "resize_mode": _PREP_RESIZE_MAP.get(self.prep_resize.value(), "max"),
            "percent": float(self.prep_percent.value()),
            "target_w": int(self.prep_w.value()),
            "target_h": int(self.prep_h.value()),
            "max_dim": int(self.prep_max.value()),
            "pot_down": self.prep_pot_down.isChecked(),
            "out_format": self.prep_fmt.value(),
            "flip_green": self.prep_flip_green.isChecked(),
        }

    def _tex_start_prep(self, kind: str, paths: list[Path], opts: dict) -> None:
        if self._prep_busy():
            QMessageBox.information(
                self, "Batch Resize", "Still running — wait or restart Assets."
            )
            return
        self.tex_log.setPlainText(f"{kind} — {len(paths)} file(s)…\n")
        worker = _TexPrepWorker(kind, paths, opts, self)
        self._tex_prep_worker = worker
        worker.line.connect(self._tex_prep_line)
        worker.finished_counts.connect(self._tex_prep_done)
        worker.start()

    def _tex_prep_line(self, text: str) -> None:
        self.tex_log.appendPlainText(text)

    def _tex_prep_done(self, ok: int, fail: int) -> None:
        self._msg(f"Batch Resize done — {ok} ok, {fail} fail")
        self.tex_log.appendPlainText(f"\n— done: {ok} ok, {fail} fail —")

    def _tex_resize(self) -> None:
        if not self.prep_enabled.isChecked():
            QMessageBox.information(
                self,
                "Batch Resize → _prep/",
                "Turn on “Use these settings for Resize → _prep…” "
                "on the Resize → _prep tab first.",
            )
            self._tex_side_tabs.set_index(1, animate=True, emit=True)
            return
        paths = self._tex_list_image_paths()
        if not paths:
            QMessageBox.warning(
                self, "Batch Resize → _prep/", "Drop images into the list first."
            )
            return
        self._tex_start_prep("resize", paths, self._prep_opts_resize())

    def _tex_ve39_scan(self) -> None:
        paths = self._tex_list_image_paths()
        if not paths:
            from ..i18n import g, t

            QMessageBox.warning(
                self, g("ve39.ui.title"), t("Drop images into the list first.")
            )
            return
        self._tex_catalog(paths, announce=True)

    def _tex_ve39_fix(self) -> None:
        paths = self._tex_list_image_paths()
        if not paths:
            from ..i18n import g, t

            QMessageBox.warning(
                self, g("ve39.ui.title"), t("Drop images into the list first.")
            )
            return
        from ..i18n import g

        reply = QMessageBox.question(
            self,
            g("ve39.ui.fix_title"),
            g("ve39.fix.confirm", n=len(paths)),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def _after_fix(ok: int, fail: int) -> None:
            self._tex_prep_done(ok, fail)
            self._tex_catalog(paths, announce=False)

        if self._prep_busy():
            QMessageBox.information(
                self, "Batch Resize", "Still running — wait or restart Assets."
            )
            return
        self.tex_log.setPlainText(f"ve39_fix — {len(paths)} file(s)…\n")
        worker = _TexPrepWorker(
            "ve39_fix", paths, {"bak": True, "num_dots": 3, "max_size": 5}, self
        )
        self._tex_prep_worker = worker
        worker.line.connect(self._tex_prep_line)
        worker.finished_counts.connect(_after_fix)
        worker.start()

    def _check_texture_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Check texture.txt",
            str(self._tex_source_dir or Path.home()),
            "Trainz texture (*.texture.txt *.texture);;All (*.*)",
        )
        if not path:
            return
        self._tex_load_path(Path(path))

    def _scan_texture_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Scan folder for .texture.txt", str(self._tex_source_dir or Path.home())
        )
        if not path:
            return
        reports = scan_folder(Path(path))
        if not reports:
            self.tex_log.setPlainText("(no .texture / .texture.txt found)")
            self._msg("Texture scan — empty")
            return
        self.tex_log.setPlainText("\n\n".join(format_report(r) for r in reports))
        bad = sum(1 for r in reports if not r.ok)
        self._msg(f"Scanned {len(reports)} — {bad} with errors")

    # ── LM ───────────────────────────────────────────────────

    def _lm_add_row(
        self,
        width: float = 1.0,
        name: str = "mesh.im",
        *,
        lod: bool = False,
        source: Path | None = None,
        refresh: bool = True,
    ) -> None:
        table = self.lm_table
        table.blockSignals(True)
        r = table.rowCount()
        table.insertRow(r)
        lod_item = QTableWidgetItem("")
        lod_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        lod_item.setCheckState(Qt.CheckState.Checked if lod else Qt.CheckState.Unchecked)
        lod_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(r, _LM_COL_LOD, lod_item)
        table.setItem(r, _LM_COL_WIDTH, QTableWidgetItem(f"{width:g}"))
        name_item = QTableWidgetItem(name)
        if source is not None:
            name_item.setData(_LM_ROLE_SOURCE, str(source))
        table.setItem(r, _LM_COL_NAME, name_item)
        table.blockSignals(False)
        if refresh:
            self._lm_refresh_preview()

    def _lm_add_from_paths(self, paths: list[Path]) -> None:
        """Append dropped meshes (LOD off → each gets its own .lm.txt on Save all)."""
        meshes = [p for p in paths if p.suffix.lower() in _LM_MESH_EXTS]
        if not meshes:
            return
        for p in sorted(meshes, key=lambda x: x.name.lower()):
            self._lm_add_row(1.0, p.name, lod=False, source=p, refresh=False)
        self._lm_refresh_preview()
        n = len(meshes)
        self._msg(f"Added {n} mesh{'es' if n != 1 else ''} — Save all writes {n} file(s) unless LOD ticked")

    def _lm_load_path(self, path: Path) -> None:
        p = Path(path)
        if p.suffix.lower() == ".lm" and not p.name.lower().endswith(".lm.txt"):
            sib = Path(str(p) + ".txt")
            if sib.is_file():
                p = sib
        try:
            lm = read_lm_txt(p)
        except Exception as exc:
            QMessageBox.warning(self, "LM", str(exc))
            return
        self._lm_to_ui(lm, source_dir=p.parent)
        self._lm_refresh_preview()
        self._msg(f"Loaded {p.name}")

    def _lm_remove_row(self) -> None:
        rows = sorted({i.row() for i in self.lm_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.lm_table.removeRow(r)
        self._lm_refresh_preview()

    def _lm_collect_rows(self) -> list[dict]:
        rows: list[dict] = []
        for r in range(self.lm_table.rowCount()):
            lod_item = self.lm_table.item(r, _LM_COL_LOD)
            w_item = self.lm_table.item(r, _LM_COL_WIDTH)
            n_item = self.lm_table.item(r, _LM_COL_NAME)
            if w_item is None or n_item is None:
                continue
            name = n_item.text().strip()
            if not name:
                continue
            try:
                width = float(w_item.text().strip())
            except ValueError:
                width = 1.0
            src_raw = n_item.data(_LM_ROLE_SOURCE)
            source = Path(src_raw) if src_raw else None
            lod = (
                lod_item is not None
                and lod_item.checkState() == Qt.CheckState.Checked
            )
            rows.append({"lod": lod, "width": width, "name": name, "source": source})
        return rows

    def _lm_base_params(self) -> dict:
        return {
            "offset": self.lm_offset.value(),
            "calc_point": self.lm_calc.value(),
            "multiplier": self.lm_mult.value(),
            "animation_cutoff": self.lm_anim.value(),
            "render_cutoff": self.lm_render.value(),
            "attachment_cutoff": self.lm_att.value(),
        }

    def _lm_file_for(self, meshes: list[LmMesh]) -> LmFile:
        return LmFile(**self._lm_base_params(), meshes=meshes)

    def _lm_from_ui(self) -> LmFile:
        """LOD-ticked rows, or all rows if none ticked (single-table preview)."""
        rows = self._lm_collect_rows()
        lod_rows = [r for r in rows if r["lod"]]
        use = lod_rows if lod_rows else rows
        return self._lm_file_for(
            [LmMesh(width=r["width"], name=r["name"]) for r in use]
        )

    def _lm_to_ui(self, lm: LmFile, *, source_dir: Path | None = None) -> None:
        self.lm_offset.blockSignals(True)
        self.lm_mult.blockSignals(True)
        self.lm_anim.blockSignals(True)
        self.lm_render.blockSignals(True)
        self.lm_att.blockSignals(True)
        self.lm_offset.setValue(lm.offset)
        self.lm_calc.set_value(lm.calc_point)
        self.lm_mult.setValue(lm.multiplier)
        self.lm_anim.setValue(lm.animation_cutoff)
        self.lm_render.setValue(lm.render_cutoff)
        self.lm_att.setValue(lm.attachment_cutoff)
        self.lm_offset.blockSignals(False)
        self.lm_mult.blockSignals(False)
        self.lm_anim.blockSignals(False)
        self.lm_render.blockSignals(False)
        self.lm_att.blockSignals(False)
        self.lm_table.blockSignals(True)
        self.lm_table.setRowCount(0)
        self.lm_table.blockSignals(False)
        for m in lm.sorted_meshes():
            src = (source_dir / m.name) if source_dir is not None else None
            self._lm_add_row(m.width, m.name, lod=True, source=src, refresh=False)

    def _lm_refresh_preview(self) -> None:
        prev = getattr(self, "lm_preview", None)
        if prev is None:
            return
        rows = self._lm_collect_rows()
        if not rows:
            prev.setPlainText("Drop .trainzmesh / .im / .fbx — or Add mesh row.")
            return
        lod_rows = [r for r in rows if r["lod"]]
        solo_rows = [r for r in rows if not r["lod"]]
        parts: list[str] = []
        if lod_rows:
            try:
                parts.append(
                    "# LOD group → one .lm.txt\n"
                    + format_lm_txt(
                        self._lm_file_for(
                            [LmMesh(r["width"], r["name"]) for r in lod_rows]
                        )
                    ).rstrip()
                )
            except ValueError as exc:
                parts.append(f"# LOD group error: {exc}")
        if solo_rows:
            parts.append(f"# Save all → {len(solo_rows)} individual .lm.txt")
            try:
                sample = solo_rows[0]
                parts.append(
                    f"# sample: {Path(sample['name']).stem}.lm.txt\n"
                    + format_lm_txt(
                        self._lm_file_for([LmMesh(sample["width"], sample["name"])])
                    ).rstrip()
                )
            except ValueError as exc:
                parts.append(str(exc))
        prev.setPlainText("\n\n".join(parts) + "\n")

    def _lm_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load .lm.txt", str(Path.home()), "LM (*.lm.txt *.lm);;All (*.*)"
        )
        if not path:
            return
        self._lm_load_path(Path(path))

    def _lm_save_folder(self, rows: list[dict]) -> Path | None:
        parents = {r["source"].parent for r in rows if r.get("source")}
        if len(parents) == 1:
            return next(iter(parents))
        start = str(next(iter(parents))) if parents else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Save all .lm.txt into…", start)
        if not folder:
            return None
        return Path(folder)

    def _lm_save(self) -> None:
        rows = self._lm_collect_rows()
        if not rows:
            QMessageBox.warning(self, "LM", "No mesh rows to save.")
            return
        lod_rows = [r for r in rows if r["lod"]]
        solo_rows = [r for r in rows if not r["lod"]]
        folder = self._lm_save_folder(rows)
        if folder is None:
            return

        written: list[str] = []
        try:
            if lod_rows:
                lm = self._lm_file_for(
                    [LmMesh(r["width"], r["name"]) for r in lod_rows]
                )
                format_lm_txt(lm)
                stem = Path(lod_rows[0]["name"]).stem
                out_name = f"{stem}.lm.txt"
                solo_names = {f"{Path(r['name']).stem}.lm.txt" for r in solo_rows}
                if out_name in solo_names:
                    out_name = f"{stem}_lod.lm.txt"
                out = write_lm_txt(folder / out_name, lm)
                written.append(out.name)
            for r in solo_rows:
                lm = self._lm_file_for([LmMesh(r["width"], r["name"])])
                format_lm_txt(lm)
                out = write_lm_txt(folder / f"{Path(r['name']).stem}.lm.txt", lm)
                written.append(out.name)
        except ValueError as exc:
            QMessageBox.warning(self, "LM", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "LM", str(exc))
            return

        self._lm_refresh_preview()
        self._msg(f"Wrote {len(written)} file(s) → {folder.name}")

    # ── KUID ─────────────────────────────────────────────────

    def _normalize_kuids(self) -> None:
        text = self.kuid_in.toPlainText()
        out = normalize_list(text)
        self.kuid_out.setPlainText(out)
        n = count_kuids(text)
        self.kuid_count.setText(f"{n} KUID{'s' if n != 1 else ''}")
        self._msg(f"Normalized {n} KUID(s)")

    def _kuid_hash(self) -> None:
        text = self.kuid_in.toPlainText()
        self.kuid_out.setPlainText(describe_kuid(text))
        n = count_kuids(text)
        self.kuid_count.setText(f"{n} KUID{'s' if n != 1 else ''}")
        self._msg("Hex + hash")

    def _copy_kuids(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = self.kuid_out.toPlainText().strip()
        if not text:
            self._normalize_kuids()
            text = self.kuid_out.toPlainText().strip()
        if not text:
            self._msg("Nothing to copy")
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(text)
        self._msg(f"Copied {count_kuids(text) or 'output'}")


def build_assets_studio(
    *,
    on_home: Callable[[], None],
    on_theme: Callable[[], None] | None = None,
    theme_mode: str = "dark",
) -> AssetsStudioHost:
    return AssetsStudioHost(on_home=on_home, on_theme=on_theme, theme_mode=theme_mode)
