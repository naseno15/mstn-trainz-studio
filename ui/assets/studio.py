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
    QSize,
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
    QFontMetrics,
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
from ...io.mat_names import (
    apply_renames,
    format_mat_report,
    scan_materials,
    suggested_mapping,
)
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
from ...io.ve_rules import (
    catalog_image,
    fix_reports,
    format_findings,
    format_report as format_ve_report,
    scan_mesh_folder,
    scan_paths,
    scan_texture_folder,
)
from ..code_edit import CodeEdit, apply_code_edit_theme
from ..frost import (
    FROST_CONTENT_MARGINS,
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

# Mesh Lods uses the same dock width as Texture Denoiser.
_RIGHT_DOCK_MIN = 320
_RIGHT_DOCK_DEFAULT = 400
_RIGHT_DOCK_MAX = 520
# Texture Params form is one column. Drag the edge to open Maps wider.
_RIGHT_DOCK_TEX_MIN = 360
_RIGHT_DOCK_TEX_DEFAULT = 420
_RIGHT_DOCK_TEX_MAX = 920
# Texture Editor / Texture Denoiser — Mesh Editor-style width.
_RIGHT_DOCK_EDIT_MIN = 320
_RIGHT_DOCK_EDIT_DEFAULT = 400
_RIGHT_DOCK_EDIT_MAX = 520
# Packages Viewer — full-height sibling of left sidebar (Mesh Editor chrome).
_RIGHT_DOCK_PKG_MIN = 420
_RIGHT_DOCK_PKG_DEFAULT = 560
_RIGHT_DOCK_PKG_MAX = 920
_TEX_ROW_H = 64  # badge + title + subtitle — 52 clipped the second line
# Longer + InOutCubic + frozen page paint = silk (setSizes every frame was janky).
_DOCK_ANIM_MS = 560
_DOCK_TICK_MS = 24
from ..smooth_scroll import enable_smooth_scroll_area, enable_smooth_table
from ..icons import apply_icon
from ..theme import app_font
from .export_cdp import ExportCdpPage
from .kuid import count_kuids, describe_kuid, normalize_list
from .denoise_page import DenoisePage
from .nav import AccentPill, AssetsPageNav, AssetsSubNav
from .packages import PackagesPage
from .param_page import ParameterPage
from .sidebar import AssetsSidebar
from .tex_map_panel import TexMapSidePanel

# Nav / slide order: Mesh Lods · Texture Params · Texture Editor · Texture Denoiser
_TEXMESH_SUB_PAGES = ("meshops", "texture", "parameter", "denoise")
_TEXMESH_SUB_LABELS = {
    "meshops": "Mesh Lods",
    "texture": "Texture Params",
    "parameter": "Texture Editor",
    "denoise": "Texture Denoiser",
}
# Right dock stack index per sub-page (full-height sibling of left sidebar).
_TEXMESH_DOCK_INDEX = {
    "texture": 0,
    "meshops": 1,
    "parameter": 2,
    "denoise": 3,
}


class _PageSlideHost(QWidget):
    """Horizontal page strip — Mesh Lods ↔ Texture Denoiser (clipped scroll, animated)."""

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


class _ForwardDrop(QObject):
    """Canvas leaves its page, so file drops on the well are handed back."""

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)
        self._target = target

    def eventFilter(self, obj: QObject, event) -> bool:  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif et == QEvent.Type.Drop:
            self._target.dropEvent(event)
            return True
        return False


_LM_MESH_EXTS = {".trainzmesh", ".im", ".fbx"}
_LM_CALC_POINTS = ("center", "near", "far")
_LM_COL_LOD, _LM_COL_WIDTH, _LM_COL_NAME = 0, 1, 2
_LM_ROLE_SOURCE = int(Qt.ItemDataRole.UserRole)


def _lm_mesh_name_for_lm(path: Path) -> str:
    """Filename written in lm.txt — Trainz converts .fbx → .trainzmesh on import."""
    if path.suffix.lower() == ".fbx":
        return f"{path.stem}.trainzmesh"
    return path.name

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


class _ElideLabel(QLabel):
    """Single-line label — middle-elide when the Name column is tight.

    sizeHint stays tiny so long filenames cannot force the table wider than
    the viewport (that was shoving Dims/Ch/Size/Status off the right edge).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setToolTip(text)
        self.setText(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        w = max(24, self.width() - 2)
        self.setText(
            QFontMetrics(self.font()).elidedText(
                self._full, Qt.TextElideMode.ElideMiddle, w
            )
        )


def _paint_drop_hint(
    painter: QPainter,
    rect,
    *,
    title: str,
    exts: str,
    hot: bool,
) -> None:
    """Empty/drag affordance — title medium, extensions small."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#ff5a1f") if hot else QColor(152, 152, 157, 150)
    pen = QPen(color)
    pen.setWidthF(1.75)
    pen.setStyle(Qt.PenStyle.CustomDashLine)
    pen.setDashPattern([5.0, 5.0])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    r = rect.adjusted(8, 8, -8, -8)
    painter.drawRoundedRect(r, 14, 14)
    if hot:
        painter.fillRect(r, QColor(255, 90, 31, 22))
    title_c = QColor("#ff5a1f") if hot else QColor(235, 235, 245, 200)
    painter.setPen(title_c)
    painter.setFont(app_font(13, QFont.Weight.DemiBold))
    mid = r.adjusted(12, 0, -12, 0)
    painter.drawText(
        mid.adjusted(0, -10, 0, -10),
        int(Qt.AlignmentFlag.AlignCenter),
        title,
    )
    painter.setPen(QColor(152, 152, 157, 170))
    painter.setFont(app_font(10, QFont.Weight.Normal))
    painter.drawText(
        mid.adjusted(0, 14, 0, 14),
        int(Qt.AlignmentFlag.AlignCenter),
        exts,
    )


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        # Ignored: cell geometry comes from the column — never grow the table.
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(0)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        mark = QLabel(badge)
        mark.setObjectName("pkgFinderBadge")
        mark.setFixedSize(28, 28)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            f"QLabel#pkgFinderBadge {{"
            f"background: {color}33; color: {color}; border-radius: 8px;"
            f"font-weight: 700; font-size: 12px;}}"
        )
        lay.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        t = _ElideLabel(title)
        t.setObjectName("pkgFinderTitle")
        t.setFont(app_font(12, QFont.Weight.DemiBold))
        t.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text.addWidget(t)
        if subtitle:
            s = _ElideLabel(subtitle)
            s.setObjectName("pkgFinderSub")
            s.setFont(app_font(10, QFont.Weight.Normal))
            s.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            text.addWidget(s)
        lay.addLayout(text, 1)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, _TEX_ROW_H)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(72, _TEX_ROW_H)


class _TexPrepWorker(QThread):
    """Resize / VE rules scan+fix / catalog off the UI thread."""

    line = Signal(str)
    catalog_row = Signal(object)  # dict: path + probe + multi-VE status
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
        elif self._kind in ("catalog", "rules_scan"):
            for path in self._paths:
                if self.isInterruptionRequested():
                    break
                row = catalog_image(path)
                status = str(row.get("status", "—"))
                findings = row.get("findings") or []
                if status == "ERR" or (row.get("error") and status == "—"):
                    fail += 1
                    self.line.emit(f"ERR  {path.name}  {row.get('error') or status}")
                elif findings:
                    ok += 1
                    self.line.emit(
                        f"HIT  {path.name}  {status}\n{format_findings(findings)}"
                    )
                else:
                    self.line.emit(
                        f"ok  {path.name}  {row.get('dims', '')}  "
                        f"{row.get('channels', '')}  {format_bytes(int(row.get('bytes') or 0))}"
                    )
                self.catalog_row.emit(row)
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
        elif self._kind == "rules_fix":
            reports = scan_paths(self._paths)
            for finding, good, msg in fix_reports(reports, bak=bool(self._opts.get("bak", True))):
                if self.isInterruptionRequested():
                    break
                tag = f"VE{finding.code}" if finding.code else "MAT"
                if good:
                    ok += 1
                    self.line.emit(f"FIXED  {tag}  {finding.path.name}  {msg}")
                else:
                    fail += 1
                    self.line.emit(f"FAIL  {tag}  {finding.path.name}  {msg}")
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
        empty = self.rowCount() == 0
        if not empty and not self._drag_over:
            return
        painter = QPainter(self.viewport())
        _paint_drop_hint(
            painter,
            self.viewport().rect(),
            title="Drop image files here" if empty else "Drop to add",
            exts=".tga  ·  .png  ·  .bmp  ·  .jpg  ·  .dds  ·  .texture.txt",
            hot=self._drag_over,
        )


class _LmDropTable(QTableWidget):
    """Mesh list — drop .trainzmesh / .im / .fbx / .lm.txt onto the table."""

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

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        empty = self.rowCount() == 0
        if not empty and not self._drag_over:
            return
        painter = QPainter(self.viewport())
        _paint_drop_hint(
            painter,
            self.viewport().rect(),
            title="Drop mesh files here" if empty else "Drop to add",
            exts=".trainzmesh  ·  .im  ·  .fbx  ·  .lm.txt",
            hot=self._drag_over,
        )


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
        shell: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_home = on_home
        self._on_theme = on_theme
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self._shell = shell
        self._surface_ready = False
        self._page = "packages"
        self._sub_page = "texture"
        self._suite = "assets"  # assets | texmesh — Home cards share one host
        self._chump_path: Path | None = None
        self._build()

    def set_theme(self, mode: str) -> None:
        from ..theme import qpalette_for

        self._theme = mode if mode in ("dark", "light") else "dark"
        dark = self._theme != "light"
        self.setPalette(qpalette_for(self._theme))
        self.sidebar.set_theme(self._theme)
        for nav in (
            getattr(self, "_nav_assets", None),
            getattr(self, "_nav_texmesh", None),
            getattr(self, "_nav", None),
        ):
            if nav is not None and hasattr(nav, "set_theme"):
                nav.set_theme(self._theme)
        if hasattr(self, "_sub_nav"):
            self._sub_nav.set_theme(self._theme)
        for panel in self.findChildren(FrostGlassFrame):
            panel.set_frost(None, dark=dark)
        for seg in self.findChildren(_SegPills):
            set_glass_dark(seg, dark)
        if hasattr(self, "packages_page"):
            self.packages_page.set_theme(self._theme)
        apply_code_edit_theme(self, self._theme)
        bridge = getattr(self, "_assets_bridge", None)
        if bridge is not None:
            bridge.set_dark(dark)
            bridge.sync_nav()
            self._drop_qml_plates()
            self._resink_center_viewers()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(True)  # right dock animates open/shut
        split.setHandleWidth(6)
        self._main_split = split

        from ...util.preload import boot_log

        boot_log("Assets · AssetsSidebar")
        self.sidebar = AssetsSidebar()
        self.sidebar.set_theme(self._theme)
        self.sidebar.native_action.connect(self._on_native)
        split.addWidget(self.sidebar)

        mid_host = QWidget()
        self._mid_host = mid_host
        mid = QVBoxLayout(mid_host)
        mid.setContentsMargins(10, 0, 0, 0)
        mid.setSpacing(8)

        self.path_lab = QLabel("Assets Tools — native writers")
        self.path_lab.setObjectName("mutedTip")
        mid.addWidget(self.path_lab)

        # Right props dock — sibling of left sidebar (Mesh Studio editor dock).
        # Built before pages so texmesh tools can mount into it.
        self._right_dock_host = QWidget()
        self._right_dock_host.setMinimumWidth(0)
        self._right_dock_host.setMaximumWidth(_RIGHT_DOCK_TEX_MAX)
        self._right_dock_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        dock_lay = QVBoxLayout(self._right_dock_host)
        # Gap from splitter only — frost plate owns content insets (FROST_CONTENT_MARGINS).
        dock_lay.setContentsMargins(8, 0, 0, 0)
        dock_lay.setSpacing(0)
        self._right_dock = QStackedWidget()
        self._right_dock.setObjectName("assetsRightDock")
        self._right_dock.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        dock_lay.addWidget(self._right_dock, 1)
        self._right_dock_host.hide()
        self._dock_width_saved = _RIGHT_DOCK_TEX_DEFAULT
        self._dock_animating = False
        self._pkg_viewer_expanded = False
        self._pkg_split_saved: list[int] | None = None

        self._stack = QStackedWidget()
        boot_log("Assets · packages page")
        self._stack.addWidget(self._build_packages_page())  # 0
        boot_log("Assets · config page")
        self._stack.addWidget(self._build_config_page())  # 1
        boot_log("Assets · texture / mesh page")
        self._stack.addWidget(self._build_texmesh_page())  # 2 Texture & Mesh Lods
        boot_log("Assets · kuid page")
        self._stack.addWidget(self._build_kuid_page())  # 3
        boot_log("Assets · export page")
        self._stack.addWidget(self._build_export_page())  # 4
        mid.addWidget(self._stack, 1)
        apply_code_edit_theme(self, self._theme)

        nav_wrap = QHBoxLayout()
        nav_wrap.addStretch(1)
        # Two suite navs — Assets (Packages·Config·KUID) vs Texture & Mesh Lods.
        self._nav_stack = QStackedWidget()
        self._nav_stack.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self._nav_assets = AssetsPageNav(suite="assets")
        self._nav_texmesh = AssetsPageNav(suite="texmesh")
        for nav in (self._nav_assets, self._nav_texmesh):
            nav.page_changed.connect(self._on_page)
            nav.home_clicked.connect(self._on_home)
            nav.theme_clicked.connect(self._theme_clicked)
            nav.set_theme(self._theme)
        self._nav_stack.addWidget(self._nav_assets)
        self._nav_stack.addWidget(self._nav_texmesh)
        self._nav = self._nav_assets
        nav_wrap.addWidget(self._nav_stack)
        nav_wrap.addStretch(1)
        mid.addLayout(nav_wrap)

        split.addWidget(mid_host)
        split.addWidget(self._right_dock_host)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        # Packages Viewer after texmesh docks (indices 0–3 stay stable).
        self._pkg_dock_index = self._right_dock.count()
        self._right_dock.addWidget(self.packages_page.viewer_panel)
        root.addWidget(split, 1)
        # Packages is the default page — open full-height Viewer dock immediately.
        self._sync_right_dock(animate=False)
        boot_log("Assets · AssetsPage.qml")
        if self._shell:
            return
        self._mount_qml()
        self._surface_ready = True

    def finish_surface(self) -> None:
        """Glass page, once. Packages, editors, and docks already exist."""
        if self._surface_ready:
            return
        self._shell = False
        self._mount_qml()
        self._surface_ready = True

    def _mount_qml(self) -> None:
        """Sunk stage + raised nav in QML. Tables, editors, and canvases stay in the wells."""
        from PySide6.QtQuickWidgets import QQuickWidget

        from ..qml_host import _quick
        from .bridge import AssetsBridge
        from .sidebar import _logo_pixmap

        qml = Path(__file__).resolve().parents[1] / "qml" / "AssetsPage.qml"
        if not qml.is_file():
            return
        self._assets_bridge = AssetsBridge(self)
        self._assets_bridge.set_dark(self._theme != "light")
        self._assets_bridge.sync_nav()
        view = _quick(qml, self._assets_bridge, logo=lambda mode: _logo_pixmap(160, mode=mode))
        if view.status() != QQuickWidget.Status.Ready:
            view.deleteLater()
            self._assets_bridge = None
            return
        lay = self.layout()
        if lay is not None:
            lay.removeWidget(self._main_split)
        self._main_split.hide()
        self._assets_view = view
        if lay is not None:
            lay.insertWidget(0, view, 1)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
        for nav in (self._nav_assets, self._nav_texmesh, getattr(self, "_sub_nav", None)):
            if nav is None:
                continue
            nav.hide()
            nav.setMaximumHeight(0)
        mid_lay = self._mid_host.layout()
        if mid_lay is not None:
            mid_lay.setContentsMargins(0, 0, 0, 0)
        self._mid_host.setAutoFillBackground(False)
        self._mid_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.path_lab.hide()
        self._nav_stack.hide()
        self._nav_stack.setMaximumHeight(0)
        self.sidebar.hide()
        rail = self.packages_page.queue_rail
        rail.setParent(self)
        self._mid_host.setParent(self)
        self._right_dock_host.setParent(self)
        dock_lay = self._right_dock_host.layout()
        if dock_lay is not None:
            dock_lay.setContentsMargins(0, 0, 0, 0)
        self._bind_side_mirror()
        self._bind_viewer_mirror()
        self._drop_qml_plates()
        self._collapse_center_heads()
        self._lift_texmesh_wells()
        open_dock = self._page == "packages" or (
            self._page == "texmesh" and self._sub_page in _TEXMESH_DOCK_INDEX
        )
        _dmin, dpref, _dmax = self._dock_width_budget()
        self._assets_bridge.set_dock(open_dock, dpref if open_dock else 0)

    def _clear_widget_fill(self, widget: QWidget, name: str) -> None:
        widget.setObjectName(name)
        widget.setAutoFillBackground(False)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        rule = f"#{name} {{ background: transparent; border: none; }}"
        sheet = widget.styleSheet()
        if rule not in sheet:
            widget.setStyleSheet((sheet + "\n" + rule).strip())

    def _lift_texmesh_wells(self) -> None:
        """Table, previews, and canvases sit in the QML center wells."""
        wells = (
            self.tex_list,
            self.tex_preview,
            self.tex_log,
            self.lm_table,
            self.lm_preview,
            self.lm_log,
            self.param_page._canvas,
            self.denoise_page._preview,
        )
        for widget in wells:
            widget.setParent(self)
            widget.setMinimumSize(0, 0)
            widget.setMaximumSize(16777215, 16777215)
            widget.hide()
        for canvas, page in (
            (self.param_page._canvas, self.param_page),
            (self.denoise_page._preview, self.denoise_page),
        ):
            canvas.setAcceptDrops(True)
            canvas.installEventFilter(_ForwardDrop(page))
        self._texmesh_lifted = True
        self._resink_center_viewers()

    def _resink_center_viewers(self) -> None:
        if not getattr(self, "_texmesh_lifted", False):
            return
        for edit in (self.tex_preview, self.tex_log, self.lm_preview, self.lm_log):
            self._sink_viewer(edit)

    def _collapse_center_heads(self) -> None:
        """Page title and blurb live on the QML center plate."""
        if not self._qml_active():
            return
        for lab in self._stack.findChildren(QLabel):
            if lab.objectName() not in ("pageHead", "pageBlurb"):
                continue
            lab.hide()
            lab.setMaximumHeight(0)
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            if page is None:
                continue
            for frame in page.findChildren(QFrame, "glassPanel"):
                lay = frame.layout()
                if lay is not None:
                    lay.setContentsMargins(0, 0, 0, 0)

    def _drop_qml_plates(self) -> None:
        """Center column and right dock sit on the QML stage — no extra black plate."""
        if not self._qml_active():
            return
        from PySide6.QtGui import QColor, QPalette

        self._clear_widget_fill(self._mid_host, "assetsMidWell")
        self._clear_widget_fill(self._stack, "assetsPageStack")
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            if page is not None:
                self._clear_widget_fill(page, f"assetsPage{index}")
        self._clear_widget_fill(self._right_dock_host, "assetsDockWell")
        self._clear_widget_fill(self._right_dock, "assetsRightDock")
        panel = getattr(self.packages_page, "_main_panel", None)
        if panel is not None:
            self._clear_widget_fill(panel, "assetsPkgPanel")
        shell = self.packages_page.findChild(QFrame, "pkgFinderShell")
        if shell is not None:
            self._clear_widget_fill(shell, "pkgFinderShell")
        preview = getattr(self.packages_page, "preview_stack", None)
        if preview is not None:
            self._clear_widget_fill(preview, "assetsPreviewStack")
        for frame in self._right_dock.findChildren(FrostGlassFrame):
            frame.set_paint_plate(False)
        from PySide6.QtWidgets import QAbstractScrollArea, QPlainTextEdit

        clear = QColor(0, 0, 0, 0)
        areas = list(self._right_dock.findChildren(QAbstractScrollArea))
        slide = getattr(self, "_sub_slide", None)
        if slide is not None:
            areas.extend(slide.findChildren(QAbstractScrollArea))
            for edit in slide.findChildren(QPlainTextEdit):
                edit.setStyleSheet(
                    "QPlainTextEdit { background: transparent; border: none; }"
                )
        for area in areas:
            vp = area.viewport()
            if vp is None:
                continue
            area.setAutoFillBackground(False)
            vp.setAutoFillBackground(False)
            pal = vp.palette()
            pal.setColor(QPalette.ColorRole.Base, clear)
            pal.setColor(QPalette.ColorRole.Window, clear)
            vp.setPalette(pal)
        table = getattr(self.packages_page, "finder_table", None)
        views = [table.viewport()] if table is not None else []
        if preview is not None:
            views.append(preview)
        for view in views:
            view.setAutoFillBackground(False)
            view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            pal = view.palette()
            pal.setColor(QPalette.ColorRole.Base, clear)
            pal.setColor(QPalette.ColorRole.Window, clear)
            view.setPalette(pal)

    def _bind_side_mirror(self) -> None:
        side = self.sidebar
        orig_page = side.set_page
        orig_en = side.set_action_enabled
        orig_brand = side.set_brand

        def set_page(page: str, *, animate: bool = True, _orig=orig_page) -> None:
            _orig(page, animate=animate)
            bridge = getattr(self, "_assets_bridge", None)
            if bridge is not None:
                bridge.sync_side()

        def set_enabled(action: str, enabled: bool, _orig=orig_en) -> None:
            _orig(action, enabled)
            bridge = getattr(self, "_assets_bridge", None)
            if bridge is not None:
                bridge.sync_side()

        def set_brand(title: str, _orig=orig_brand) -> None:
            _orig(title)
            bridge = getattr(self, "_assets_bridge", None)
            if bridge is not None:
                bridge.sync_nav()

        side.set_page = set_page  # type: ignore[method-assign]
        side.set_action_enabled = set_enabled  # type: ignore[method-assign]
        side.set_brand = set_brand  # type: ignore[method-assign]

    def _bind_viewer_mirror(self) -> None:
        """QML dock reads the widget labels; refresh it when preview chrome changes."""
        page = self.packages_page
        bridge = self._assets_bridge

        def wrap(widget: QWidget, method: str) -> None:
            orig = getattr(widget, method)

            def inner(*args, _orig=orig, **kwargs):
                _orig(*args, **kwargs)
                bridge.sync_viewer()

            setattr(widget, method, inner)

        wrap(page.preview_lab, "setText")
        wrap(page._side_title, "setText")
        wrap(page.font_lab, "setText")
        wrap(page.btn_nested, "setEnabled")
        wrap(page.btn_save_text, "setEnabled")
        for btn in (page.btn_engine_tuner, page.btn_fast_preview, page.btn_mesh_studio):
            wrap(btn, "setVisible")
        tabs = page._pane_mode_tabs
        orig_tab = tabs.set_tab_enabled

        def set_tab_enabled(index: int, enabled: bool, *, tip: str = "", _orig=orig_tab) -> None:
            _orig(index, enabled, tip=tip)
            bridge.sync_viewer()

        tabs.set_tab_enabled = set_tab_enabled  # type: ignore[method-assign]

    def _qml_active(self) -> bool:
        return getattr(self, "_assets_view", None) is not None and getattr(self, "_assets_bridge", None) is not None

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
        self.packages_page.viewer_expand_toggled.connect(self._on_pkg_viewer_expand)
        self.sidebar.mount_packages_queue(self.packages_page.queue_rail)
        return self.packages_page

    def show_packages(self) -> None:
        self.set_suite("assets")
        self._on_page("packages")

    def set_suite(self, suite: str) -> None:
        """Home entry: ``assets`` (pack/config/KUID) or ``texmesh`` (LODs·maps·bake)."""
        suite = "texmesh" if suite == "texmesh" else "assets"
        same = suite == getattr(self, "_suite", "assets")
        self._suite = suite
        stack = getattr(self, "_nav_stack", None)
        if suite == "texmesh":
            self._nav = self._nav_texmesh
            if stack is not None:
                stack.setCurrentIndex(1)
            sub = getattr(self, "_sub_nav", None)
            if sub is not None:
                sub.hide()  # bottom nav is enough
            self.sidebar.set_brand("Texture & Mesh Lods tools")
            if not same or self._page != "texmesh":
                self._on_page("texture")
            else:
                self._nav.set_page(self._sub_page, emit=False, animate=False)
        else:
            self._nav = self._nav_assets
            if stack is not None:
                stack.setCurrentIndex(0)
            sub = getattr(self, "_sub_nav", None)
            if sub is not None and not self._qml_active():
                sub.show()  # only visible while stack is on texmesh (won't be)
            self.sidebar.set_brand("Assets Tools")
            if not same or self._page == "texmesh":
                self._on_page("packages")
            else:
                self._nav.set_page(self._page, emit=False, animate=False)

    def _suite_label(self) -> str:
        return (
            "Texture & Mesh Lods tools"
            if self._suite == "texmesh"
            else "Assets Tools"
        )

    def _build_config_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        head = self._title("Config / chump")
        head.setObjectName("pageHead")
        pl.addWidget(head)
        tip = QLabel(
            "Edit config.chump as text (ChumpLib-style), save binary, "
            "or pack / export config.txt."
        )
        tip.setObjectName("pageBlurb")
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
        """Grouped hub — Mesh Lods · Texture Params · Texture Editor · Texture Denoiser."""
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

        self.param_page = ParameterPage()
        self.param_page.status.connect(self._msg)
        self.denoise_page = DenoisePage()
        self.denoise_page.status.connect(self._msg)
        # Order must match _TEXMESH_SUB_PAGES (meshops, texture, parameter, denoise).
        # Texture / Mesh Ops build also mount their own right-dock props (idx 0-1).
        tex_page = self._build_texture_page()
        mesh_page = self._build_meshops_page()
        self._mount_edit_dock(
            self.param_page.tools_panel,
            title="Texture Editor",
            subtitle="Channels · adjust · paint · Save overwrite",
        )
        self._mount_edit_dock(
            self.denoise_page.tools_panel,
            title="Texture Denoiser",
            subtitle="OIDN / OpenCV · preview then Save overwrite",
        )
        self._sub_slide = _PageSlideHost(
            [
                mesh_page,
                tex_page,
                self.param_page,
                self.denoise_page,
            ]
        )
        lay.addWidget(self._sub_slide, 1)
        return page

    def _mount_edit_dock(
        self,
        tools: QWidget,
        *,
        title: str,
        subtitle: str,
    ) -> FrostGlassFrame:
        """Full-height right dock chrome — same frost inset as Mesh Editor."""
        props = FrostGlassFrame(radius=14.0)
        props.setObjectName("editorDock")
        props.setMinimumWidth(0)
        props.setMaximumWidth(16777215)
        props.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        props.set_dark(self._theme != "light")
        pr = QVBoxLayout(props)
        pr.setContentsMargins(*FROST_CONTENT_MARGINS)
        pr.setSpacing(10)

        head = QLabel(title)
        head.setObjectName("welcomeTitle")
        head.setFont(app_font(14, QFont.Weight.DemiBold))
        pr.addWidget(head)
        tip = QLabel(subtitle)
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        pr.addWidget(tip)

        scroll = QScrollArea()
        scroll.setObjectName("editorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        tools.setParent(None)
        scroll.setWidget(tools)
        enable_smooth_scroll_area(scroll)
        pr.addWidget(scroll, 1)
        self._right_dock.addWidget(props)
        return props

    def _texmesh_sub_index(self, page: str) -> int:
        try:
            return _TEXMESH_SUB_PAGES.index(page)
        except ValueError:
            return 0

    def _build_texture_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        panel = self._glass()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        head = self._title("Texture.txt")
        head.setObjectName("pageHead")
        pl.addWidget(head)
        tip = QLabel(
            "Drop PBR maps onto the table — groups albedo/normal/parameter. "
            "Dims · channels · size · VE rules auto-scan (37/39/65…). "
            "Double-click a row to select the whole set."
        )
        tip.setObjectName("pageBlurb")
        tip.setWordWrap(True)
        pl.addWidget(tip)

        mid = QSplitter(Qt.Orientation.Vertical)
        mid.setChildrenCollapsible(False)
        mid.setHandleWidth(6)

        list_host = QWidget()
        lh = QVBoxLayout(list_host)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(4)
        list_lab = QLabel("Images · PBR sets")
        list_lab.setObjectName("mutedTip")
        lh.addWidget(list_lab)
        self.tex_list = _TexDropTable()
        self.tex_list.setObjectName("pkgFinder")
        self.tex_list.setHorizontalHeaderLabels(
            ["Name", "Dims", "Ch", "Size", "Status"]
        )
        hdr = self.tex_list.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(40)
        hdr.setSectionResizeMode(_TEX_COL_NAME, hdr.ResizeMode.Stretch)
        for col, w in (
            (_TEX_COL_DIMS, 118),
            (_TEX_COL_CH, 114),
            (_TEX_COL_SIZE, 96),
            (_TEX_COL_STATUS, 72),
        ):
            hdr.setSectionResizeMode(col, hdr.ResizeMode.Fixed)
            self.tex_list.setColumnWidth(col, w)
        vhdr = self.tex_list.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setDefaultSectionSize(_TEX_ROW_H)
        vhdr.setMinimumSectionSize(_TEX_ROW_H)
        self.tex_list.setShowGrid(False)
        self.tex_list.setWordWrap(False)
        self.tex_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tex_list.setAlternatingRowColors(False)
        self.tex_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tex_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tex_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tex_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tex_list.setMinimumWidth(0)

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
        refresh = QPushButton()
        apply_icon(refresh, "refresh", tip="Refresh preview", kind="icon", size=18, square=32)
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
        self._sink_viewer(self.tex_preview)
        twin.addWidget(self.tex_preview)
        self.tex_log = CodeEdit(syntax="plain")
        self.tex_log.setReadOnly(True)
        self.tex_log.setPlaceholderText("Check / scan results…")
        self._sink_viewer(self.tex_log)
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
        # Same air as left Assets sidebar / Mesh Editor — shadow fade needs room.
        pr.setContentsMargins(*FROST_CONTENT_MARGINS)
        pr.setSpacing(10)

        props_title = QLabel("Texture Params")
        props_title.setObjectName("welcomeTitle")
        props_title.setFont(app_font(14, QFont.Weight.DemiBold))
        self._tex_props_title = props_title
        pr.addWidget(props_title)

        # Lazy import — SideTabStrip lives in app.py (avoid circular at module load).
        from ..app import SideTabStrip

        self._tex_side_tabs = SideTabStrip(("Params", "Maps", "Resize"))
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
        self._tex_alpha_on = False

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

        # ── tab 1: Maps Viewer / Editor ───────────────────────
        self._tex_map_panel = TexMapSidePanel()
        self._tex_map_panel.status.connect(self._msg)
        self._tex_map_panel.saved.connect(self._tex_map_saved)
        self._tex_side_stack.addWidget(self._tex_map_panel)

        # ── tab 2: Batch Resize → _prep/ ──────────────────────
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
            "Rules scan/fix cover VE37/39/65… — VE39-only buttons still available."
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
        idx = max(0, min(int(index), 2))
        self._tex_side_index = idx
        stack = self._tex_side_stack
        # Instant swap — fade_stack_page + QGraphicsOpacityEffect on frost
        # side panels crashes Win / leaves options stuck invisible (opacity 0).
        for i in range(stack.count()):
            page = stack.widget(i)
            if page is not None and page.graphicsEffect() is not None:
                page.setGraphicsEffect(None)
        stack.setCurrentIndex(idx)
        titles = ("Texture Params", "Maps Viewer / Editor", "Batch Resize → _prep/")
        self._tex_props_title.setText(titles[max(0, min(idx, len(titles) - 1))])
        if idx == 1:
            self._tex_sync_map_panel()
        self._tex_sync_side_scroll()
        QTimer.singleShot(0, self._tex_sync_side_scroll)
        bridge = getattr(self, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_form()

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
        head = self._title("LM.txt LOD")
        head.setObjectName("pageHead")
        pl.addWidget(head)
        tip = QLabel(
            "Drop meshes onto the table → Save all writes one .lm.txt each. "
            "Tick LOD to combine those rows into a shared LOD table instead. "
            "FBX / trainzmesh material names are checked for .m.pbrmetal / .m.onetex."
        )
        tip.setObjectName("pageBlurb")
        tip.setWordWrap(True)
        pl.addWidget(tip)

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
        self.lm_table.setObjectName("pkgFinder")
        self.lm_table.setHorizontalHeaderLabels(["LOD", "Width", "Mesh file"])
        self.lm_table.horizontalHeader().setStretchLastSection(True)
        self.lm_table.setColumnWidth(_LM_COL_LOD, 48)
        self.lm_table.setColumnWidth(_LM_COL_WIDTH, 72)
        self.lm_table.setShowGrid(False)
        self.lm_table.verticalHeader().setVisible(False)
        self.lm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lm_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lm_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lm_table.setToolTip(
            "Drop .trainzmesh / .im / .fbx / .lm.txt here. Tick LOD to combine rows."
        )
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
        prev_lab = QLabel("lm.txt preview · material check")
        prev_lab.setObjectName("mutedTip")
        prev_row.addWidget(prev_lab)
        prev_row.addStretch(1)
        refresh = QPushButton()
        apply_icon(refresh, "refresh", tip="Refresh preview", kind="icon", size=18, square=32)
        refresh.clicked.connect(self._lm_refresh_preview)
        prev_row.addWidget(refresh)
        ph.addLayout(prev_row)

        # preview | material log side-by-side (same layout language as Texture)
        twin = QSplitter(Qt.Orientation.Horizontal)
        twin.setChildrenCollapsible(False)
        twin.setHandleWidth(6)
        self.lm_preview = CodeEdit(syntax="trainzconfig")
        self.lm_preview.setReadOnly(True)
        self.lm_preview.setPlaceholderText("Drop meshes or Add row → preview")
        self._sink_viewer(self.lm_preview)
        twin.addWidget(self.lm_preview)
        self.lm_log = CodeEdit(syntax="plain")
        self.lm_log.setReadOnly(True)
        self.lm_log.setPlaceholderText(
            "Material names… drop .fbx / .trainzmesh to check .m.pbrmetal / .m.onetex"
        )
        self._sink_viewer(self.lm_log)
        twin.addWidget(self.lm_log)
        twin.setStretchFactor(0, 1)
        twin.setStretchFactor(1, 1)
        twin.setSizes([420, 420])
        ph.addWidget(twin, 1)
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
        pr.setContentsMargins(*FROST_CONTENT_MARGINS)
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

        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.setAlignment(Qt.AlignmentFlag.AlignTop)
        bl.addWidget(self._lm_field("offset", self.lm_offset))
        bl.addWidget(self._lm_field("calcPoint", self.lm_calc))
        bl.addWidget(self._lm_field("multiplier", self.lm_mult))
        bl.addWidget(self._lm_field("animCutOff", self.lm_anim))
        bl.addWidget(self._lm_field("renderCutOff", self.lm_render))
        bl.addWidget(self._lm_field("attachCutOff", self.lm_att))
        bl.addStretch(1)
        scroll.setWidget(body)
        enable_smooth_scroll_area(scroll)
        pr.addWidget(scroll, 1)
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
        head = self._title("KUID")
        head.setObjectName("pageHead")
        pl.addWidget(head)
        tip = QLabel("Paste CM text → normalize. Hex + hash-XX from public KUID format.")
        tip.setObjectName("pageBlurb")
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

    def _build_export_page(self) -> QWidget:
        self.export_page = ExportCdpPage(on_status=self._msg)
        return self.export_page

    # ── nav / theme ──────────────────────────────────────────

    def _theme_clicked(self) -> None:
        if self._on_theme is not None:
            self._on_theme()

    def _dock_width_budget(self) -> tuple[int, int, int]:
        """``(min, preferred, max)`` — packages / tex params / editor docks."""
        if getattr(self, "_page", None) == "packages":
            if getattr(self, "_pkg_viewer_expanded", False):
                return (
                    _RIGHT_DOCK_PKG_MIN,
                    _RIGHT_DOCK_PKG_MAX,
                    _RIGHT_DOCK_PKG_MAX,
                )
            return (
                _RIGHT_DOCK_PKG_MIN,
                _RIGHT_DOCK_PKG_DEFAULT,
                _RIGHT_DOCK_PKG_MAX,
            )
        sub = getattr(self, "_sub_page", "texture")
        if sub == "texture":
            return _RIGHT_DOCK_TEX_MIN, _RIGHT_DOCK_TEX_DEFAULT, _RIGHT_DOCK_TEX_MAX
        if sub in ("parameter", "denoise"):
            return _RIGHT_DOCK_EDIT_MIN, _RIGHT_DOCK_EDIT_DEFAULT, _RIGHT_DOCK_EDIT_MAX
        return _RIGHT_DOCK_MIN, _RIGHT_DOCK_DEFAULT, _RIGHT_DOCK_MAX

    def _dock_target_sizes(self, *, open_dock: bool) -> list[int]:
        split = self._main_split
        sizes = [int(x) for x in split.sizes()]
        while len(sizes) < 3:
            sizes.append(0)
        total = max(1, sum(sizes) or int(split.width()) or 1800)
        left = sizes[0] if sizes[0] > 80 else min(400, total // 5)
        dmin, dpref, dmax = self._dock_width_budget()
        if open_dock:
            sub = getattr(self, "_sub_page", "texture")
            page = getattr(self, "_page", None)
            # packages expand / tex params: prefer near-max. Editor docks: fixed preferred.
            if page == "packages" and getattr(self, "_pkg_viewer_expanded", False):
                right = dpref
            elif page == "packages":
                right = int(self._dock_width_saved or dpref)
                right = max(dmin, min(dmax, right))
            elif sub in ("texture", "parameter", "denoise"):
                right = dpref
            else:
                right = int(self._dock_width_saved or dpref)
            right = max(dmin, min(dmax, right))
            mid_floor = 120 if (
                page == "packages" and getattr(self, "_pkg_viewer_expanded", False)
            ) else 240
            mid = max(mid_floor, total - left - right)
            # If mid got crushed, shrink right toward min.
            if mid < mid_floor:
                right = max(dmin, total - left - mid_floor)
                mid = max(mid_floor, total - left - right)
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
        """Show/hide full-height right dock — packages Viewer or texmesh props."""
        host = getattr(self, "_right_dock_host", None)
        dock = getattr(self, "_right_dock", None)
        split = getattr(self, "_main_split", None)
        if host is None or dock is None or split is None:
            if after is not None:
                after()
            return

        dock_index: int | None = None
        if self._qml_active():
            if self._page == "packages":
                dock_index = int(getattr(self, "_pkg_dock_index", -1))
                if dock_index < 0 or dock_index >= dock.count():
                    dock_index = None
            elif self._page == "texmesh" and self._sub_page in _TEXMESH_DOCK_INDEX:
                dock_index = _TEXMESH_DOCK_INDEX[self._sub_page]
            if dock_index is not None:
                dock.setCurrentIndex(dock_index)
                _dmin, dpref, dmax = self._dock_width_budget()
                host.setMaximumWidth(dmax)
                self._assets_bridge.set_dock(True, dpref)
            else:
                self._assets_bridge.set_dock(False, 0)
            # Entering texmesh froze the page stack so the dock could move.
            # QML does not run that lerp, so paint has to come back here.
            self._freeze_page_paint(False)
            if after is not None:
                after()
            return

        if self._page == "packages":
            dock_index = int(getattr(self, "_pkg_dock_index", -1))
            if dock_index < 0 or dock_index >= dock.count():
                dock_index = None
        elif self._page == "texmesh" and self._sub_page in _TEXMESH_DOCK_INDEX:
            dock_index = _TEXMESH_DOCK_INDEX[self._sub_page]

        want_open = dock_index is not None
        if want_open:
            dock.setCurrentIndex(dock_index)
            dmin, _dpref, dmax = self._dock_width_budget()
            host.setMaximumWidth(dmax)
            cur = [int(x) for x in split.sizes()]
            already_open = (not host.isHidden()) and len(cur) >= 3 and cur[2] >= 80
            target = self._dock_target_sizes(open_dock=True)
            # Texture / packages-expand want near-max — resize even if already open.
            need_resize = (
                already_open
                and len(cur) >= 3
                and abs(cur[2] - target[2]) > 24
            )
            if already_open and not need_resize and not self._dock_animating:
                host.setMinimumWidth(dmin)
                if self._page == "texmesh":
                    QTimer.singleShot(0, self._tex_sync_side_scroll)
                if after is not None:
                    after()
                return
            host.setMinimumWidth(0)
            host.show()
            if not animate:
                split.setSizes(target)
                host.setMinimumWidth(dmin)
                self._relayout_nav_bars()
                if self._page == "texmesh":
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
                host.setMinimumWidth(dmin)
                if self._page == "texmesh":
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

    def _on_pkg_viewer_expand(self, expanded: bool) -> None:
        """Grow / restore Packages Viewer dock width when Finder is toggled."""
        expanded = bool(expanded)
        self._pkg_viewer_expanded = expanded
        if self._qml_active():
            self._sync_right_dock(animate=True)
            return
        if expanded:
            sizes = [int(x) for x in self._main_split.sizes()]
            if len(sizes) >= 3 and sizes[1] > 80:
                self._pkg_split_saved = sizes
        elif self._pkg_split_saved is not None:
            # Restore prior mid/right split after collapse.
            saved = list(self._pkg_split_saved)
            self._pkg_split_saved = None
            self._pkg_viewer_expanded = False
            if len(saved) >= 3 and not self._dock_animating:
                host = self._right_dock_host
                dmin, _d, dmax = self._dock_width_budget()
                host.setMaximumWidth(dmax)
                host.setMinimumWidth(0)
                host.show()

                def _restored() -> None:
                    host.setMinimumWidth(dmin)
                    self._relayout_nav_bars()

                self._run_dock_anim(saved, on_done=_restored)
                return
        self._sync_right_dock(animate=True)

    def _reveal_sub_nav(self) -> None:
        """Fade top Texture | Mesh Ops bar after the dock has settled (avoids double jank)."""
        sub = getattr(self, "_sub_nav", None)
        if sub is None:
            return
        fade_widget(sub, 0.05, 1.0, 280)
        QTimer.singleShot(0, lambda: sub._sync_pill(False) if hasattr(sub, "_sync_pill") else None)

    def _on_page(self, page: str) -> None:
        # Bottom group + legacy aliases
        prev = getattr(self, "_page", None)
        prev_sub = getattr(self, "_sub_page", "texture")
        if page in _TEXMESH_SUB_PAGES:
            self._sub_page = page
            page = "texmesh"
        elif page == "texmesh":
            page = "texmesh"
        idx = {
            "packages": 0,
            "config": 1,
            "texmesh": 2,
            "kuid": 3,
            "export": 4,
        }.get(page, 0)
        changed = prev != page
        sub_changed = (
            prev == "texmesh" and page == "texmesh" and prev_sub != self._sub_page
        )
        entering_tex = page == "texmesh" and prev != "texmesh"
        leaving_tex = prev == "texmesh" and page != "texmesh"
        leaving_pkg = prev == "packages" and page != "packages"
        if leaving_pkg:
            self._pkg_viewer_expanded = False
            self._pkg_split_saved = None
            self.packages_page.reset_viewer_expand()
        self._page = page
        # Freeze before the stack swap so the first dock frame isn't a heavy paint.
        if changed and (entering_tex or leaving_tex):
            clear_button_hover_chrome()
            self._freeze_page_paint(True)
        self._stack.setCurrentIndex(idx)
        # Pill slide — suite nav speaks texture/…/meshops or packages/config/kuid
        if self._suite == "texmesh":
            self._nav.set_page(self._sub_page, emit=False, animate=True)
        else:
            pill = page if page in ("packages", "config", "kuid", "export") else "packages"
            self._nav.set_page(pill, emit=False, animate=True)

        if page == "texmesh":
            if self._suite != "texmesh":
                self._sub_nav.set_page(
                    self._sub_page, emit=False, animate=(prev == "texmesh")
                )
            self._sub_slide.set_index(
                self._texmesh_sub_index(self._sub_page),
                animate=(prev == "texmesh"),
            )
            label = _TEXMESH_SUB_LABELS.get(self._sub_page, "Texture")
        else:
            label = {
                "packages": "Packages",
                "config": "Config",
                "kuid": "KUID",
                "export": "Export",
            }.get(page, page)

        # Defer sidebar rebuild + sub-nav fade until dock motion finishes —
        # running them in parallel with setSizes was the hitch.
        def _after_dock() -> None:
            if page == "texmesh":
                self.sidebar.set_page(self._sub_page, animate=entering_tex)
                if entering_tex and self._suite != "texmesh":
                    self._reveal_sub_nav()
            else:
                self.sidebar.set_page(page, animate=leaving_tex or changed)

        # Animate dock when entering/leaving texmesh OR switching texture↔meshops↔tools.
        self._sync_right_dock(animate=changed or sub_changed, after=_after_dock)
        msg = f"{self._suite_label()} — {label}"
        self.path_lab.setText(msg)
        self.status.emit(msg)
        bridge = getattr(self, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_nav()

    def _on_sub_page(self, page: str) -> None:
        if page not in _TEXMESH_SUB_PAGES:
            page = "texture"
        self._sub_page = page
        self._sub_slide.set_index(self._texmesh_sub_index(page), animate=True)
        self.sidebar.set_page(page, animate=True)
        self._sync_right_dock()
        if self._suite == "texmesh":
            self._nav.set_page(page, emit=False, animate=True)
        label = _TEXMESH_SUB_LABELS.get(page, "Texture")
        msg = f"{self._suite_label()} — {label}"
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
            "tex_rules_scan": self._tex_rules_scan,
            "tex_rules_fix": self._tex_rules_fix,
            "tex_ve39_scan": self._tex_ve39_scan,
            "tex_ve39_fix": self._tex_ve39_fix,
            "open_texture": self._check_texture_file,
            "scan_folder": self._scan_texture_folder,
            "cfg_rules_scan": self._cfg_rules_scan,
            "param_open": lambda: getattr(self, "param_page", None) and self.param_page.open_file(),
            "param_save": lambda: getattr(self, "param_page", None) and self.param_page.save(),
            "param_undo": lambda: getattr(self, "param_page", None) and self.param_page.undo(),
            "param_redo": lambda: getattr(self, "param_page", None) and self.param_page.redo(),
            "param_revert": lambda: getattr(self, "param_page", None) and self.param_page.revert(),
            "denoise_open": lambda: getattr(self, "denoise_page", None) and self.denoise_page.open_file(),
            "denoise_run": lambda: getattr(self, "denoise_page", None) and self.denoise_page.run_denoise(),
            "denoise_save": lambda: getattr(self, "denoise_page", None) and self.denoise_page.save(),
            "denoise_revert": lambda: getattr(self, "denoise_page", None) and self.denoise_page.revert(),
            "lm_add": lambda: self._lm_add_row(1.0, "mesh.im"),
            "lm_remove": self._lm_remove_row,
            "lm_load": self._lm_load,
            "lm_save": self._lm_save,
            "lm_rules_scan": self._lm_rules_scan,
            "lm_rules_fix": self._lm_rules_fix,
            "lm_mat_scan": self._lm_mat_scan_selected,
            "lm_mat_fix": self._lm_mat_fix_selected,
            "normalize_kuids": self._normalize_kuids,
            "kuid_hash": self._kuid_hash,
            "copy_kuids": self._copy_kuids,
            "export_read": self.export_page.read_list,
            "export_all": self.export_page.select_all,
            "export_each": self.export_page.export_each,
            "export_one": self.export_page.export_one,
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

    def _sink_viewer(self, edit) -> None:
        """Inset the preview / scan log so it sits in the stage, not as a flat plate."""
        dark = self._theme != "light"
        if dark:
            fill = "rgba(0, 0, 0, 0.46)"
            top, side, bot = "rgba(0,0,0,0.72)", "rgba(0,0,0,0.40)", "rgba(255,255,255,0.14)"
            base = QColor(6, 8, 12, 210)
        else:
            fill = "rgba(255, 255, 255, 0.62)"
            top, side, bot = "rgba(0,0,0,0.16)", "rgba(0,0,0,0.08)", "rgba(255,255,255,0.90)"
            base = QColor(255, 255, 255, 210)
        edit.setStyleSheet(
            "QPlainTextEdit {"
            f"background: {fill}; color: {'#f2f4f8' if dark else '#1d1d1f'};"
            "border-radius: 12px;"
            f"border-top: 1px solid {top};"
            f"border-left: 1px solid {side};"
            f"border-bottom: 1px solid {bot};"
            f"border-right: 1px solid {bot};"
            "padding: 6px;"
            "}"
        )
        from PySide6.QtGui import QPalette

        view = edit.viewport()
        view.setAutoFillBackground(True)
        pal = view.palette()
        pal.setColor(QPalette.ColorRole.Base, base)
        view.setPalette(pal)

    def _tex_pick_map(self, which: str) -> None:
        start = str(getattr(self, "_tex_source_dir", "") or "")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select texture",
            start,
            "Images (*.tga *.png *.jpg *.jpeg *.bmp *.dds *.texture *.texture.txt);;All (*.*)",
        )
        if not path:
            return
        name = Path(path).name
        if name.lower().endswith(".texture.txt"):
            name = name[: -len(".txt")]
        self._tex_source_dir = Path(path).parent
        if which == "alpha":
            self._tex_alpha_on = True
            self.tex_alpha.setText(name)
        else:
            self.tex_primary.setText(name)
        self._tex_refresh_preview()

    def _tex_seg_val(self, seg: _SegPills) -> str:
        v = seg.value()
        return "" if v == _TEX_OMIT else v

    def _tex_set_seg(self, seg: _SegPills, value: str) -> None:
        seg.set_value(value if value else _TEX_OMIT)

    def _tex_keys(self) -> dict[str, str]:
        alpha = self.tex_alpha.text().strip() if getattr(self, "_tex_alpha_on", False) else ""
        keys = default_texture_keys(
            primary=self.tex_primary.text().strip(),
            alpha=alpha,
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
            alpha=self.tex_alpha.text().strip() if getattr(self, "_tex_alpha_on", False) else "",
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
        else:
            self.tex_preview.setPlainText(format_texture_txt(keys))
        bridge = getattr(self, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_form()

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
        self._tex_sync_map_panel(images[0])
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
            self.tex_list.setRowHeight(i, _TEX_ROW_H)
            accent, _tint = _TEX_ROLE_COLORS.get(
                role or "", ("#8e8e93", QColor(142, 142, 147, 22))
            )
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
                # No solid row tint — was covering selection wash (orange rim / black fill).
                align = Qt.AlignmentFlag.AlignVCenter
                if align_right:
                    align |= Qt.AlignmentFlag.AlignRight
                    it.setForeground(QColor("#98989d"))
                    it.setFont(app_font(11, QFont.Weight.Medium))
                else:
                    align |= Qt.AlignmentFlag.AlignLeft
                it.setTextAlignment(align)
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
        self._tex_sync_map_panel(path)
        self._msg(f"Primary ← {path.name}")

    def _tex_sync_map_panel(self, path: Path | None = None) -> None:
        panel = getattr(self, "_tex_map_panel", None)
        if panel is None:
            return
        if path is None:
            rows = sorted({idx.row() for idx in self.tex_list.selectedIndexes()})
            path = self._tex_row_path(rows[0]) if rows else None
        panel.set_from_selection(list(self._tex_paths), path)

    def _tex_map_saved(self, path: object) -> None:
        """Refresh catalog row after Maps editor Save."""
        if not isinstance(path, Path):
            return
        self._tex_catalog([path], announce=False)
        self._msg(f"Map saved ← {path.name}")

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
            self._tex_sync_map_panel(path)
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
                if text == "OK":
                    st.setForeground(QColor("#30d158"))
                elif text == "ERR" or text.startswith("VE"):
                    st.setForeground(QColor("#ff453a"))
            break

    def _tex_catalog_done(self, ok: int, fail: int, *, announce: bool = True) -> None:
        # catalog: ok count = files with VE hits
        self._msg(f"Texture catalog — VE hits {ok}, errors {fail}")
        if announce:
            self.tex_log.appendPlainText(f"\n— catalog done: hits={ok} err={fail} —")

    def _tex_apply_keys(self, keys: dict[str, str]) -> None:
        self.tex_primary.blockSignals(True)
        self.tex_alpha.blockSignals(True)
        self.tex_primary.setText(keys.get("Primary", ""))
        self.tex_alpha.setText(keys.get("Alpha", ""))
        self._tex_alpha_on = bool(keys.get("Alpha", "").strip())
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

    def _tex_rules_scan(self) -> None:
        paths = self._tex_list_image_paths()
        if not paths:
            from ..i18n import g, t

            QMessageBox.warning(
                self, g("rules.ui.title"), t("Drop images into the list first.")
            )
            return
        self._tex_catalog(paths, announce=True)

    def _tex_rules_fix(self) -> None:
        paths = self._tex_list_image_paths()
        if not paths:
            from ..i18n import g, t

            QMessageBox.warning(
                self, g("rules.ui.title"), t("Drop images into the list first.")
            )
            return
        from ..i18n import g

        reply = QMessageBox.question(
            self,
            g("rules.ui.fix_title"),
            g("rules.fix.confirm", n=len(paths)),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def _after_fix(ok: int, fail: int) -> None:
            self._msg(f"Rules fix — {ok} ok, {fail} fail")
            self.tex_log.appendPlainText(f"\n— rules fix done: {ok} ok, {fail} fail —")
            self._tex_catalog(paths, announce=False)

        if self._prep_busy():
            QMessageBox.information(
                self, "Rules", "Still running — wait or restart Assets."
            )
            return
        self.tex_log.setPlainText(f"rules_fix — {len(paths)} file(s)…\n")
        worker = _TexPrepWorker("rules_fix", paths, {"bak": True}, self)
        self._tex_prep_worker = worker
        worker.line.connect(self._tex_prep_line)
        worker.finished_counts.connect(_after_fix)
        worker.start()

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
            self,
            "Scan folder for texture VE rules",
            str(self._tex_source_dir or Path.home()),
        )
        if not path:
            return
        folder = Path(path)
        ve_reports = scan_texture_folder(folder)
        legacy = scan_folder(folder)
        chunks: list[str] = []
        if ve_reports:
            chunks.append(
                "\n\n".join(format_ve_report(r) for r in ve_reports if r.findings)
                or "(no VE hits on images/texture.txt)"
            )
        if legacy:
            chunks.append("\n\n".join(format_report(r) for r in legacy))
        if not chunks:
            self.tex_log.setPlainText("(no textures found)")
            self._msg("Texture scan — empty")
            return
        self.tex_log.setPlainText("\n\n".join(chunks))
        bad = sum(1 for r in ve_reports if r.error_count)
        self._msg(f"Rules scan — {len(ve_reports)} file(s), {bad} with errors")
        # drop images into the list for Status column
        images = [
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        ]
        if images:
            self._tex_add_from_paths(images)
            self._tex_catalog(images, announce=False)

    def ve_context_paths(self) -> list[Path]:
        """Paths for app-wide Tools → VE Rules (textures, meshes, config folder)."""
        out: list[Path] = []
        out.extend(self._tex_list_image_paths())
        out.extend(self._lm_source_paths(selected_only=False))
        if self._chump_path is not None:
            out.append(self._chump_path.parent)
            cfg = self._chump_path.parent / "config.txt"
            if cfg.is_file():
                out.append(cfg)
        if self._tex_source_dir is not None:
            out.append(self._tex_source_dir)
        # dedupe
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in out:
            try:
                key = str(p.resolve())
            except OSError:
                key = str(p)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        return uniq

    def _show_ve_report_dialog(self, title: str, reports: list) -> None:
        from ..ve_dialog import show_ve_reports

        show_ve_reports(self, reports, title=title)

    def _cfg_rules_scan(self) -> None:
        """Scan an asset folder: config + mesh + texture VE rules."""
        from ...io.ve_rules import scan_asset_folder

        start = (
            self._chump_path.parent if self._chump_path is not None else Path.home()
        )
        path = QFileDialog.getExistingDirectory(
            self, "Scan asset folder for VE rules", str(start)
        )
        if not path:
            return
        folder = Path(path)
        reports = scan_asset_folder(folder)
        self._show_ve_report_dialog(f"VE Rules — {folder.name}", reports)
        hits = sum(1 for r in reports if r.findings)
        self._msg(f"Rules scan — {hits} report(s) with findings in {folder.name}")

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
            self._lm_add_row(
                1.0,
                _lm_mesh_name_for_lm(p),
                lod=False,
                source=p,
                refresh=False,
            )
        self._lm_refresh_preview()
        n = len(meshes)
        self._msg(f"Added {n} mesh{'es' if n != 1 else ''} — Save all writes {n} file(s) unless LOD ticked")
        self._lm_scan_materials(meshes, offer_fix=True)

    def _lm_source_paths(self, *, selected_only: bool = False) -> list[Path]:
        """Mesh source paths from table rows (prefer selected when asked)."""
        table = getattr(self, "lm_table", None)
        if table is None:
            return []
        rows = range(table.rowCount())
        if selected_only:
            picked = sorted({i.row() for i in table.selectedIndexes()})
            if picked:
                rows = picked
        out: list[Path] = []
        seen: set[str] = set()
        for r in rows:
            item = table.item(r, _LM_COL_NAME)
            if item is None:
                continue
            raw = item.data(_LM_ROLE_SOURCE)
            if not raw:
                continue
            p = Path(str(raw))
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            if p.suffix.lower() in _LM_MESH_EXTS and p.is_file():
                out.append(p)
        return out

    def _lm_log_set(self, text: str) -> None:
        log = getattr(self, "lm_log", None)
        if log is not None:
            log.setPlainText(text)

    def _lm_log_append(self, text: str) -> None:
        log = getattr(self, "lm_log", None)
        if log is not None:
            log.appendPlainText(text)

    def _lm_scan_materials(
        self, paths: list[Path], *, offer_fix: bool = False
    ) -> list[tuple[Path, list]]:
        """Scan material names → lm_log; optionally prompt to rename in place."""
        reports: list[str] = []
        scanned: list[tuple[Path, list]] = []
        fixable: list[tuple[Path, dict[str, str]]] = []
        for p in paths:
            try:
                issues = scan_materials(p)
            except Exception as exc:
                reports.append(f"— {p.name} —\n(error: {exc})")
                continue
            reports.append(format_mat_report(p, issues))
            scanned.append((p, issues))
            mapping = suggested_mapping(issues)
            if mapping and p.suffix.lower() in {".fbx", ".trainzmesh"}:
                fixable.append((p, mapping))
        body = "\n\n".join(reports) if reports else "(no mesh sources to scan)"
        self._lm_log_set(body)
        bad_n = sum(len(suggested_mapping(iss)) for _, iss in scanned)
        if bad_n:
            self._msg(f"Material names: {bad_n} need fix — see log")
        elif scanned:
            self._msg(f"Material names: {sum(len(i) for _, i in scanned)} ok")
        if offer_fix and fixable:
            self._lm_offer_mat_fix(fixable)
        return scanned

    def _lm_offer_mat_fix(self, fixable: list[tuple[Path, dict[str, str]]]) -> None:
        """Ask whether to apply suggested renames now."""
        lines: list[str] = []
        total = 0
        for path, mapping in fixable:
            lines.append(path.name)
            for old, new in mapping.items():
                lines.append(f"  {old}  ->  {new}")
                total += 1
            lines.append("")
        reply = QMessageBox.question(
            self,
            "Material names",
            f"{total} material name(s) look wrong for Trainz.\n"
            "Rename in the mesh file now?\n\n"
            + "\n".join(lines[:40])
            + ("\n…" if len(lines) > 40 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._lm_log_append("\n— fix skipped —")
            return
        self._lm_apply_mat_fixes(fixable)

    def _lm_apply_mat_fixes(self, fixable: list[tuple[Path, dict[str, str]]]) -> None:
        ok = 0
        fail = 0
        notes: list[str] = []
        for path, mapping in fixable:
            try:
                n = apply_renames(path, mapping, backup=True)
                ok += n
                notes.append(f"fixed {path.name}: {n} rename(s)")
            except Exception as exc:
                fail += 1
                notes.append(f"fix failed {path.name}: {exc}")
        paths = [p for p, _ in fixable]
        self._lm_scan_materials(paths, offer_fix=False)
        if notes:
            self._lm_log_append("\n— " + " · ".join(notes) + " —")
        self._msg(f"Material rename — {ok} ok, {fail} fail")

    def _lm_rules_scan(self) -> None:
        paths = self._lm_source_paths(selected_only=True)
        if not paths:
            paths = self._lm_source_paths(selected_only=False)
        # also include any .lm.txt loaded / beside meshes
        extras: list[Path] = []
        for p in paths:
            lm = p.with_suffix(".lm.txt")
            if lm.is_file():
                extras.append(lm)
            cfg = p.parent / "config.txt"
            if cfg.is_file() and cfg not in extras:
                extras.append(cfg)
        if not paths and not extras:
            QMessageBox.information(
                self, "Rules", "Drop .fbx / .trainzmesh / .im onto the table first."
            )
            return
        # Prefer whole-folder scan when all meshes share a parent
        parents = {p.parent for p in paths} if paths else set()
        if len(parents) == 1:
            folder = next(iter(parents))
            reports = scan_mesh_folder(folder)
            reports.extend(scan_texture_folder(folder))
        else:
            reports = scan_paths(paths + extras)
        body = "\n\n".join(
            format_ve_report(r) for r in reports if r.findings
        ) or "(no VE issues)"
        self._lm_log_set(body)
        self._show_ve_report_dialog("Mesh / LOD VE Rules", reports)
        hits = sum(1 for r in reports if r.findings)
        self._msg(f"Mesh rules — {hits} report(s) with findings")

    def _lm_rules_fix(self) -> None:
        paths = self._lm_source_paths(selected_only=True)
        if not paths:
            paths = self._lm_source_paths(selected_only=False)
        if not paths:
            QMessageBox.information(
                self, "Rules", "Drop .fbx / .trainzmesh onto the table first."
            )
            return
        from ..i18n import g

        reply = QMessageBox.question(
            self,
            g("rules.ui.fix_title"),
            g("rules.fix.confirm", n=len(paths)),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        reports = scan_paths(paths)
        results = fix_reports(reports, bak=True)
        lines = [
            f"{'FIXED' if ok else 'FAIL'}  VE{f.code if f.code else 'MAT'}  "
            f"{f.path.name}  {msg}"
            for f, ok, msg in results
        ]
        self._lm_log_set("\n".join(lines) if lines else "(nothing fixable)")
        # re-scan materials after renames
        self._lm_scan_materials(paths, offer_fix=False)
        ok_n = sum(1 for _, ok, _ in results if ok)
        self._msg(f"Mesh rules fix — {ok_n} ok, {len(results) - ok_n} fail")

    def _lm_mat_scan_selected(self) -> None:
        paths = self._lm_source_paths(selected_only=True)
        if not paths:
            paths = self._lm_source_paths(selected_only=False)
        if not paths:
            QMessageBox.information(
                self, "Materials", "Drop .fbx / .trainzmesh onto the table first."
            )
            return
        self._lm_scan_materials(paths, offer_fix=False)

    def _lm_mat_fix_selected(self) -> None:
        paths = self._lm_source_paths(selected_only=True)
        if not paths:
            paths = self._lm_source_paths(selected_only=False)
        if not paths:
            QMessageBox.information(
                self, "Materials", "Drop .fbx / .trainzmesh onto the table first."
            )
            return
        scanned = self._lm_scan_materials(paths, offer_fix=False)
        fixable = [
            (p, suggested_mapping(issues))
            for p, issues in scanned
            if suggested_mapping(issues) and p.suffix.lower() in {".fbx", ".trainzmesh"}
        ]
        if not fixable:
            QMessageBox.information(self, "Materials", "No material renames suggested.")
            return
        self._lm_offer_mat_fix(fixable)

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

    def _sync_qml_form(self) -> None:
        bridge = getattr(self, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_form()

    def _lm_refresh_preview(self) -> None:
        prev = getattr(self, "lm_preview", None)
        if prev is None:
            return
        rows = self._lm_collect_rows()
        if not rows:
            prev.setPlainText("Drop .trainzmesh / .im / .fbx — or Add mesh row.")
            self._sync_qml_form()
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
        self._sync_qml_form()

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
    shell: bool = False,
) -> AssetsStudioHost:
    return AssetsStudioHost(
        on_home=on_home, on_theme=on_theme, theme_mode=theme_mode, shell=shell
    )
