"""Parameter map editor page — Trainz RGBA channels + paint + Save overwrite."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QRect,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...io.param_map_edit import (
    CHANNELS,
    CHANNEL_KEYS,
    IMAGE_EXTS,
    apply_brightness_contrast,
    apply_fill,
    apply_invert,
    apply_offset,
    apply_overlay,
    apply_retarget_mean,
    apply_scale,
    apply_stamp_at,
    CHANNEL_INDEX,
    channel_stats,
    downscale_rgba,
    luminance,
    magic_mask,
    open_parameter,
    paint_line,
    save_parameter,
    view_param_composite,
    view_plane,
)
from ...io.tex_map_edit import TexMapSession
from ..smooth_scroll import enable_smooth_table
from ..theme import app_font

_CHANNEL_CAPTION = {
    "R": "R  Emissive",
    "G": "G  Roughness",
    "B": "B  AO",
    "A": "A  Metallic",
}


def _rgba_to_pixmap(rgba: np.ndarray) -> QPixmap:
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return str(a.resolve()).lower() == str(b.resolve()).lower()
    except OSError:
        return str(a).lower() == str(b).lower()


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _paint_drop_hint(painter: QPainter, rect, *, title: str, exts: str, hot: bool) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#ff5a1f") if hot else QColor(152, 152, 157, 150)
    pen = QPen(color)
    pen.setWidthF(1.75)
    pen.setStyle(Qt.PenStyle.CustomDashLine)
    pen.setDashPattern([5.0, 5.0])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    box = rect.adjusted(8, 8, -8, -8)
    painter.drawRoundedRect(box, 14, 14)
    if hot:
        painter.fillRect(box, QColor(255, 90, 31, 22))
    painter.setPen(QColor("#ff5a1f") if hot else QColor(235, 235, 245, 200))
    painter.setFont(app_font(13, QFont.Weight.DemiBold))
    mid = box.adjusted(12, 0, -12, 0)
    painter.drawText(mid.adjusted(0, -10, 0, -10), int(Qt.AlignmentFlag.AlignCenter), title)
    painter.setPen(QColor(152, 152, 157, 170))
    painter.setFont(app_font(10, QFont.Weight.Normal))
    painter.drawText(mid.adjusted(0, 14, 0, 14), int(Qt.AlignmentFlag.AlignCenter), exts)


@dataclass
class _MapSlot:
    path: Path
    session: TexMapSession | None = None
    thumb: QIcon | None = None
    overlays: dict = field(default_factory=dict)


class _DecodeBus(QObject):
    ready = Signal(str, str, object, object)


class _DecodeJob(QRunnable):
    """Full decode off the UI thread. The list only waits on the queued result."""

    def __init__(self, path: str, kind: str, sink: Signal) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._path = path
        self._kind = kind
        self._sink = sink

    def run(self) -> None:
        try:
            rgba = open_parameter(self._path)
            payload = rgba if self._kind == "map" else luminance(rgba)
            extra = _thumb_rgba(rgba) if self._kind == "map" else None
        except Exception:
            payload = extra = None
        try:
            self._sink.emit(self._path, self._kind, payload, extra)
        except RuntimeError:
            return


def _thumb_rgba(rgba: np.ndarray, side: int = 36) -> np.ndarray:
    height, width = rgba.shape[:2]
    scale = side / max(height, width, 1)
    if scale >= 1:
        return rgba
    return cv2.resize(
        rgba,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


class _MapTable(QTableWidget):
    """Sidebar queue — same drop table as Packages, for parameter images."""

    images_dropped = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self._drag_over = False
        self.setObjectName("pkgFinder")
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setHorizontalHeaderLabels(["Name", "Size"])
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 72)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(48)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setIconSize(QSize(36, 36))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        enable_smooth_table(self)

    def _image_paths(self, event) -> list[Path]:
        if not event.mimeData().hasUrls():
            return []
        out: list[Path] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in IMAGE_EXTS and path.is_file():
                out.append(path)
        return out

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._image_paths(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if self._image_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_drag_over(False)
        paths = self._image_paths(event)
        if not paths:
            event.ignore()
            return
        self.images_dropped.emit(paths)
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        empty = self.rowCount() == 0
        if not empty and not self._drag_over:
            return
        painter = QPainter(self.viewport())
        _paint_drop_hint(
            painter,
            self.viewport().rect(),
            title="Drop images here" if empty else "Drop to add",
            exts=".png  ·  .tga  ·  .jpg  ·  .bmp  ·  .tif  ·  .webp",
            hot=self._drag_over,
        )


class _PaintCanvas(QWidget):
    """Zoomable map. Brush, stamp placement, and magic select live here."""

    painted = Signal()
    stroke_done = Signal()
    magic_pick = Signal(float, float)
    image_dropped = Signal(object, QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._pix: QPixmap | None = None
        self._scale = 1.0
        self._origin = QPoint(0, 0)
        self._drag_pan = False
        self._last = QPoint()
        self._mode = "off"  # off | brush | stamp | magic
        self._session: TexMapSession | None = None
        self._selected: set[str] = set()
        self._brush = 16
        self._value = 128
        self._hardness = 0.6
        self._opacity = 1.0
        self._stroke = False
        self._img_last: tuple[float, float] | None = None
        self._mask: np.ndarray | None = None
        self._mask_pix: QPixmap | None = None
        self._stamp: np.ndarray | None = None
        self._stamp_pix: QPixmap | None = None
        self._stamp_xy = (0.0, 0.0)
        self._stamp_drag = False

    def set_session(self, session: TexMapSession | None) -> None:
        self._session = session

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("off", "brush", "stamp", "magic") else "off"
        cursors = {
            "brush": Qt.CursorShape.CrossCursor,
            "magic": Qt.CursorShape.PointingHandCursor,
            "stamp": Qt.CursorShape.SizeAllCursor,
        }
        self.setCursor(cursors.get(self._mode, Qt.CursorShape.ArrowCursor))

    def set_paint_mode(self, on: bool) -> None:
        if not on:
            self.set_mode("off")
        elif self._mode == "off":
            self.set_mode("brush")

    def set_brush(
        self,
        *,
        selected: set[str],
        radius: int,
        value: int,
        hardness: float,
        opacity: float,
    ) -> None:
        self._selected = set(selected)
        self._brush = max(1, int(radius))
        self._value = int(value)
        self._hardness = float(hardness)
        self._opacity = float(opacity)

    def set_image(self, pix: QPixmap | None) -> None:
        self._pix = pix
        self.update()

    def set_mask(self, mask: np.ndarray | None) -> None:
        self._mask = mask
        if mask is None:
            self._mask_pix = None
        else:
            h, w = mask.shape
            veil = np.zeros((h, w, 4), np.uint8)
            veil[..., 3] = np.where(mask, 0, 120).astype(np.uint8)
            self._mask_pix = _rgba_to_pixmap(veil)
        self.update()

    def set_stamp(self, src: np.ndarray | None, x: float = 0.0, y: float = 0.0) -> None:
        if src is None:
            self._stamp = None
            self._stamp_pix = None
        else:
            self._stamp = np.asarray(src, dtype=np.uint8)
            self._stamp_pix = _rgba_to_pixmap(self._stamp)
            self._stamp_xy = (float(x), float(y))
        self.update()

    def stamp_pixels(self) -> np.ndarray | None:
        return self._stamp

    def stamp_origin(self) -> tuple[float, float]:
        return self._stamp_xy

    def clear_stamp(self) -> None:
        self.set_stamp(None)

    def fit(self) -> None:
        if self._pix is None or self._pix.isNull():
            return
        wr = self.width() / max(1, self._pix.width())
        hr = self.height() / max(1, self._pix.height())
        self._scale = max(0.05, min(wr, hr) * 0.96)
        self._origin = QPoint(0, 0)
        self.update()

    def _img_pos(self, pos: QPoint) -> tuple[float, float] | None:
        if self._pix is None or self._pix.isNull():
            return None
        cx = self.width() / 2 + self._origin.x()
        cy = self.height() / 2 + self._origin.y()
        x = (pos.x() - cx) / self._scale + self._pix.width() / 2
        y = (pos.y() - cy) / self._scale + self._pix.height() / 2
        if x < 0 or y < 0 or x >= self._pix.width() or y >= self._pix.height():
            return None
        return float(x), float(y)

    def _draw_pix(self, painter: QPainter, pix: QPixmap, ix: float, iy: float) -> None:
        w = int(pix.width() * self._scale)
        h = int(pix.height() * self._scale)
        cx = self.width() / 2 + self._origin.x()
        cy = self.height() / 2 + self._origin.y()
        x = int(cx + (ix - self._pix.width() / 2) * self._scale) if self._pix else 0
        y = int(cy + (iy - self._pix.height() / 2) * self._scale) if self._pix else 0
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._scale < 2.5)
        painter.drawPixmap(x, y, w, h, pix)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        self._scale = max(0.05, min(32.0, self._scale * factor))
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._mode == "off"
        ):
            self._drag_pan = True
            self._last = event.position().toPoint()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._session is None:
            return
        pt = self._img_pos(event.position().toPoint())
        if pt is None:
            return
        if self._mode == "magic":
            self.magic_pick.emit(pt[0], pt[1])
            return
        if self._mode == "stamp" and self._stamp is not None:
            self._stamp_drag = True
            self._last = event.position().toPoint()
            return
        if self._mode != "brush":
            return
        self._session.snapshot()
        self._stroke = True
        self._img_last = pt
        paint_line(
            self._session.pixels,
            self._selected,
            pt[0],
            pt[1],
            pt[0],
            pt[1],
            self._brush,
            self._value,
            hardness=self._hardness,
            opacity=self._opacity,
            mask=self._mask,
        )
        self._session.dirty = True
        self.painted.emit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pan:
            cur = event.position().toPoint()
            self._origin += cur - self._last
            self._last = cur
            self.update()
            return
        if self._stamp_drag and self._stamp is not None:
            cur = event.position().toPoint()
            delta = cur - self._last
            self._last = cur
            self._stamp_xy = (
                self._stamp_xy[0] + delta.x() / self._scale,
                self._stamp_xy[1] + delta.y() / self._scale,
            )
            self.update()
            return
        if self._stroke and self._session and self._img_last is not None:
            pt = self._img_pos(event.position().toPoint())
            if pt is None:
                return
            paint_line(
                self._session.pixels,
                self._selected,
                self._img_last[0],
                self._img_last[1],
                pt[0],
                pt[1],
                self._brush,
                self._value,
                hardness=self._hardness,
                opacity=self._opacity,
                mask=self._mask,
            )
            self._img_last = pt
            self._session.dirty = True
            self.painted.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            done = self._stroke
            self._drag_pan = False
            self._stamp_drag = False
            self._stroke = False
            self._img_last = None
            if done:
                self.stroke_done.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths: list[Path] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in IMAGE_EXTS and path.is_file():
                paths.append(path)
        if not paths:
            event.ignore()
            return
        self.image_dropped.emit(paths[0], event.position().toPoint())
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 20, 26))
        if self._pix is None or self._pix.isNull():
            painter.setPen(QColor(140, 148, 160))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Pick a map on the left",
            )
            return
        self._draw_pix(painter, self._pix, 0, 0)
        if self._mask_pix is not None:
            self._draw_pix(painter, self._mask_pix, 0, 0)
        if self._stamp_pix is not None:
            painter.setOpacity(0.72)
            self._draw_pix(painter, self._stamp_pix, self._stamp_xy[0], self._stamp_xy[1])
            painter.setOpacity(1.0)


class _ViewTabs(QWidget):
    """Color | Grey — same orange pill track as the right dock tabs."""

    changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self._labels = ("Color", "Grey")
        self._index = 0
        self._pill = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_pill)

    def _on_pill(self, value: object) -> None:
        self._pill = float(value)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self.width() < 8:
            return
        index = 0 if event.position().x() < self.width() / 2 else 1
        if index == self._index:
            return
        self._index = index
        self._anim.stop()
        self._anim.setStartValue(self._pill)
        self._anim.setEndValue(float(index))
        self._anim.start()
        self.changed.emit(index)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(255, 255, 255, 20)))
        painter.setBrush(QColor(0, 0, 0, 82))
        painter.drawRoundedRect(track, 12, 12)
        span = max(1.0, (track.width() - 6) / 2)
        pill = QRect(int(3 + self._pill * span), 3, int(span), track.height() - 6)
        grad = QLinearGradient(pill.topLeft(), pill.bottomLeft())
        grad.setColorAt(0.0, QColor("#ff7a45"))
        grad.setColorAt(0.42, QColor("#ff5a1f"))
        grad.setColorAt(1.0, QColor("#c43a10"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(pill, 10, 10)
        painter.setPen(QColor(255, 255, 255, 140))
        painter.drawLine(pill.left() + 10, pill.top() + 1, pill.right() - 10, pill.top() + 1)
        painter.setFont(app_font(12, QFont.Weight.DemiBold))
        for index, label in enumerate(self._labels):
            cell = QRect(int(index * (track.width() / 2)), 0, int(track.width() / 2), track.height())
            painter.setPen(QColor("#ffffff") if index == self._index else QColor(242, 244, 248))
            weight = QFont.Weight.Bold if index == self._index else QFont.Weight.DemiBold
            painter.setFont(app_font(12, weight))
            painter.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), label)


class _ChannelStrip(QWidget):
    """Bottom row. Drop a gray image on a channel to replace that layer."""

    overlay_dropped = Signal(str, object)
    view_changed = Signal(str, str)
    overlay_cleared = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(132)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._pix: dict[str, QPixmap] = {}
        self._gray = False
        self._overlay: dict[str, str] = {}  # key → "original" | "modified"
        self._names: dict[str, str] = {}
        self._hot: str | None = None
        self._hits: list[tuple[object, str, str]] = []

    def set_state(
        self,
        pix: dict[str, QPixmap],
        *,
        gray: bool,
        overlay: dict[str, str],
        names: dict[str, str],
    ) -> None:
        self._pix = pix
        self._gray = gray
        self._overlay = dict(overlay)
        self._names = dict(names)
        self.update()

    def clear(self) -> None:
        self.set_state({}, gray=self._gray, overlay={}, names={})

    def _cell(self, x: int) -> str | None:
        if self.width() < 8:
            return None
        index = int(x / (self.width() / 4))
        if index < 0 or index > 3:
            return None
        return CHANNEL_KEYS[index]

    def _image_paths(self, event) -> list[Path]:
        if not event.mimeData().hasUrls():
            return []
        out: list[Path] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in IMAGE_EXTS and path.is_file():
                out.append(path)
        return out

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._image_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        key = self._cell(int(event.position().x()))
        if key != self._hot:
            self._hot = key
            self.update()
        if self._image_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._hot = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._hot = None
        paths = self._image_paths(event)
        key = self._cell(int(event.position().x()))
        if not paths or key is None:
            event.ignore()
            self.update()
            return
        self.overlay_dropped.emit(key, paths[0])
        event.acceptProposedAction()
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        for rect, kind, key in self._hits:
            if rect.contains(pos):
                if kind == "view":
                    self.view_changed.emit(key[0], key[1:])
                elif kind == "clear":
                    self.overlay_cleared.emit(key)
                return

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(14, 16, 20))
        self._hits = []
        width = max(1, self.width())
        cell = width / 4
        top = 4
        for index, key in enumerate(CHANNEL_KEYS):
            left = int(index * cell)
            right = int((index + 1) * cell)
            painter.setPen(QColor(180, 186, 196))
            painter.setFont(app_font(11, QFont.Weight.DemiBold))
            painter.drawText(
                left + 8,
                top,
                int(cell) - 16,
                16,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                _CHANNEL_CAPTION[key],
            )
            body_top = top + 18
            if key in self._overlay:
                body_top = self._paint_tabs(painter, key, left, right, body_top)
            box_top = body_top + 2
            box = self.rect().__class__(left + 6, box_top, max(4, right - left - 12), max(4, self.height() - box_top - 8))
            if self._hot == key:
                painter.setPen(QPen(QColor("#ff5a1f")))
                painter.setBrush(QColor(255, 90, 31, 28))
                painter.drawRoundedRect(box, 8, 8)
            pix = self._pix.get(key)
            if pix is None or pix.isNull():
                painter.setPen(QColor(140, 148, 160))
                painter.setFont(app_font(10, QFont.Weight.Normal))
                painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "Drop gray")
                continue
            scale = min(box.width() / pix.width(), box.height() / pix.height())
            w = max(1, int(pix.width() * scale))
            h = max(1, int(pix.height() * scale))
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, scale < 2.5)
            painter.drawPixmap(box.x() + (box.width() - w) // 2, box.y() + (box.height() - h) // 2, w, h, pix)

    def _paint_tabs(self, painter: QPainter, key: str, left: int, right: int, y: int) -> int:
        view = self._overlay.get(key, "modified")
        x = left + 8
        painter.setFont(app_font(10, QFont.Weight.DemiBold))
        for label, mode in (("Original", "original"), ("Modified", "modified")):
            rect = self.rect().__class__(x, y, 62, 16)
            self._hits.append((rect, "view", key + mode))
            on = view == mode
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ff5a1f") if on else QColor(255, 255, 255, 16))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor("#ffffff") if on else QColor(180, 186, 196))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)
            x += 66
        kill = self.rect().__class__(min(x, right - 22), y, 16, 16)
        self._hits.append((kill, "clear", key))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 16))
        painter.drawRoundedRect(kill, 4, 4)
        painter.setPen(QColor(220, 224, 230))
        painter.drawText(kill, int(Qt.AlignmentFlag.AlignCenter), "×")
        name = self._names.get(key, "")
        if name and right - x > 70:
            painter.setPen(QColor(140, 148, 160))
            painter.drawText(
                x + 20,
                y,
                right - x - 28,
                16,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                name,
            )
        return y + 18


class _Stage(QSplitter):
    """Top composite / bottom channels. First show gives the bottom a real share."""

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.height() > 80 and self.sizes()[1] < 40:
            self.setSizes([int(self.height() * 0.58), int(self.height() * 0.42)])


class ParameterPage(QWidget):
    """Canvas page — tools live in the host right dock (``tools_panel``)."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._slots: list[_MapSlot] = []
        self._session: TexMapSession | None = None
        self._mask: np.ndarray | None = None
        self._overlays: dict[str, dict] = {}
        self._gray_channels = False
        self._tool_tab = 0
        self._paint_tool = "Brush"
        self._selecting = False
        self._focus: _MapSlot | None = None
        self._bus = _DecodeBus(self)
        self._bus.ready.connect(self._on_decoded)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("glassPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        title = QLabel("Parameter map")
        title.setObjectName("pageHead")
        title.setFont(app_font(16, QFont.Weight.Bold))
        lay.addWidget(title)
        tip = QLabel(
            "Top: ticked channels overlaid. Bottom: drop a gray image on a channel to replace it."
        )
        tip.setObjectName("pageBlurb")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self._top = _PaintCanvas()
        self._top.painted.connect(self._refresh_top)
        self._top.stroke_done.connect(self._refresh)
        self._top.magic_pick.connect(self._on_magic)
        self._top.image_dropped.connect(self._on_canvas_drop)
        self._channels = _ChannelStrip()
        self._channels.overlay_dropped.connect(self._queue_overlay)
        self._channels.view_changed.connect(self._set_overlay_view)
        self._channels.overlay_cleared.connect(self._clear_overlay)
        self._tone = _ViewTabs()
        self._tone.changed.connect(lambda index: self._set_channel_gray(index == 1))
        self._split = _Stage(Qt.Orientation.Vertical)
        self._split.setChildrenCollapsible(False)
        self._split.addWidget(self._top)
        self._split.addWidget(self._channels)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        self._canvas = QWidget()
        stage = QVBoxLayout(self._canvas)
        stage.setContentsMargins(0, 0, 0, 0)
        stage.setSpacing(8)
        stage.addWidget(self._tone)
        stage.addWidget(self._split, 1)
        lay.addWidget(self._canvas, 1)
        root.addWidget(panel, 1)

        self.strip_rail = self._build_strip()
        self.tools_panel = self._build_tools()

    def _build_strip(self) -> QWidget:
        rail = QWidget()
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap = QLabel("Parameter maps")
        cap.setObjectName("mutedTip")
        lay.addWidget(cap)
        self._table = _MapTable()
        self._table.images_dropped.connect(self.add_maps)
        self._table.itemSelectionChanged.connect(self._on_row)
        lay.addWidget(self._table, 1)
        return rail

    def _build_tools(self) -> QWidget:
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sl = QVBoxLayout(body)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)

        tabs = QHBoxLayout()
        self._tab_btns: list[QPushButton] = []
        for index, label in enumerate(("Adjust", "Overlay", "Paint", "Export")):
            btn = QPushButton(label)
            btn.setObjectName("mapToolBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, i=index: self._click_tab(i))
            tabs.addWidget(btn)
            self._tab_btns.append(btn)
        sl.addLayout(tabs)

        from PySide6.QtWidgets import QStackedWidget

        self._tool_stack = QStackedWidget()
        self._tool_stack.addWidget(self._build_adjust())
        self._tool_stack.addWidget(self._build_overlay())
        self._tool_stack.addWidget(self._build_paint())
        self._tool_stack.addWidget(self._build_export())
        sl.addWidget(self._tool_stack)

        hist = QHBoxLayout()
        for label, slot in (("Undo", self.undo), ("Redo", self.redo), ("Revert", self.revert)):
            btn = QPushButton(label)
            btn.setObjectName("mapGhostBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(slot)
            hist.addWidget(btn)
        sl.addLayout(hist)

        self._stats = QLabel("")
        self._stats.setObjectName("mutedTip")
        self._stats.setWordWrap(True)
        sl.addWidget(self._stats)

        save = QPushButton("Save (overwrite)")
        save.setObjectName("accentBtn")
        save.clicked.connect(self.save)
        sl.addWidget(save)
        sl.addStretch(1)
        self._click_tab(0)
        return body

    def _build_adjust(self) -> QWidget:
        page = QWidget()
        sl = QVBoxLayout(page)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        open_row = QHBoxLayout()
        open_btn = QPushButton("Open…")
        open_btn.setObjectName("mapToolBtn")
        open_btn.clicked.connect(self.open_file)
        open_row.addWidget(open_btn, 1)
        self._path_lab = QLabel("No file")
        self._path_lab.setObjectName("mutedTip")
        self._path_lab.setWordWrap(True)
        open_row.addWidget(self._path_lab, 2)
        sl.addLayout(open_row)

        sl.addWidget(self._section("CHANNELS"))
        self._ch_boxes: dict[str, QCheckBox] = {}
        for key, label, _idx in CHANNELS:
            box = QCheckBox(f"{key} — {label}")
            box.setChecked(True)
            box.toggled.connect(lambda _=False, k=key: self._on_ch_toggle(k))
            self._ch_boxes[key] = box
            sl.addWidget(box)

        sl.addWidget(self._section("ADJUST"))
        self._offset = self._spin(-255, 255, 0)
        self._scale = self._dbl_spin(0.0, 4.0, 1.0, 0.05)
        self._fill = self._spin(0, 255, 128)
        self._bright = self._spin(-255, 255, 0)
        self._contrast = self._dbl_spin(0.0, 3.0, 1.0, 0.05)
        self._mean = self._spin(0, 255, 128)
        for lab, widget in (
            ("Offset", self._offset),
            ("Scale", self._scale),
            ("Fill", self._fill),
            ("Bright", self._bright),
            ("Contrast", self._contrast),
            ("→ Mean", self._mean),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab), 1)
            row.addWidget(widget, 2)
            sl.addLayout(row)

        tools = QHBoxLayout()
        for label, slot in (
            ("Offset", self._do_offset),
            ("Scale", self._do_scale),
            ("Fill", self._do_fill),
        ):
            btn = QPushButton(label)
            btn.setObjectName("mapToolBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(slot)
            tools.addWidget(btn)
        sl.addLayout(tools)
        tools2 = QHBoxLayout()
        for label, slot in (
            ("B/C", self._do_bc),
            ("Mean", self._do_mean),
            ("Invert", self._do_invert),
        ):
            btn = QPushButton(label)
            btn.setObjectName("mapToolBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(slot)
            tools2.addWidget(btn)
        sl.addLayout(tools2)
        sl.addStretch(1)
        return page

    def _build_overlay(self) -> QWidget:
        page = QWidget()
        sl = QVBoxLayout(page)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        sl.addWidget(self._section("OVERLAY"))
        self._ov_mode = QComboBox()
        self._ov_mode.addItems(["blend", "stamp", "replace"])
        self._ov_src = QComboBox()
        self._ov_src.addItems(["gray", "R", "G", "B", "A", "match"])
        self._ov_opacity = QSlider(Qt.Orientation.Horizontal)
        self._ov_opacity.setRange(0, 100)
        self._ov_opacity.setValue(100)
        ov_btn = QPushButton("Overlay image…")
        ov_btn.setObjectName("mapToolBtn")
        ov_btn.clicked.connect(self._do_overlay)
        sl.addWidget(self._ov_mode)
        sl.addWidget(self._ov_src)
        sl.addWidget(self._ov_opacity)
        sl.addWidget(ov_btn)
        note = QLabel("Paint → Stamp uses this mode, source, and opacity.")
        note.setObjectName("mutedTip")
        note.setWordWrap(True)
        sl.addWidget(note)
        sl.addStretch(1)
        return page

    def _build_paint(self) -> QWidget:
        page = QWidget()
        sl = QVBoxLayout(page)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self._paint_chk = QCheckBox("Paint mode")
        self._paint_chk.setChecked(False)
        self._paint_chk.hide()
        sl.addWidget(self._section("TOOL"))
        self._brush = self._spin(1, 256, 16)
        self._paint_val = self._spin(0, 255, 128)
        self._hard = QSlider(Qt.Orientation.Horizontal)
        self._hard.setRange(0, 100)
        self._hard.setValue(60)
        self._tol = self._spin(0, 255, 24)
        self._contiguous = QCheckBox("Contiguous")
        self._contiguous.setChecked(True)
        for lab, widget in (("Radius", self._brush), ("Value", self._paint_val), ("Tolerance", self._tol)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab), 1)
            row.addWidget(widget, 2)
            sl.addLayout(row)
        sl.addWidget(QLabel("Hardness"))
        sl.addWidget(self._hard)
        sl.addWidget(self._contiguous)
        for widget in (self._brush, self._paint_val, self._hard):
            widget.valueChanged.connect(self._sync_brush)
        self._stamp_lab = QLabel("Drop an image on the map to place it")
        self._stamp_lab.setObjectName("mutedTip")
        self._stamp_lab.setWordWrap(True)
        sl.addWidget(self._stamp_lab)
        row = QHBoxLayout()
        apply_btn = QPushButton("Apply stamp")
        apply_btn.setObjectName("mapToolBtn")
        apply_btn.clicked.connect(self.apply_stamp)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("mapGhostBtn")
        cancel_btn.clicked.connect(self.cancel_stamp)
        clear_btn = QPushButton("Clear select")
        clear_btn.setObjectName("mapGhostBtn")
        clear_btn.clicked.connect(self.clear_selection)
        for btn in (apply_btn, cancel_btn, clear_btn):
            btn.setFixedHeight(28)
            row.addWidget(btn)
        sl.addLayout(row)
        self._sync_brush()
        sl.addStretch(1)
        return page

    def _build_export(self) -> QWidget:
        page = QWidget()
        sl = QVBoxLayout(page)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        sl.addWidget(self._section("EXPORT"))
        note = QLabel("Writes that channel. Color uses the channel tint. Grey is black and white.")
        note.setObjectName("mutedTip")
        note.setWordWrap(True)
        sl.addWidget(note)
        tone = QHBoxLayout()
        self._export_tone = "Color"
        self._export_btns: list[QPushButton] = []
        for label in ("Color", "Grey"):
            btn = QPushButton(label)
            btn.setObjectName("mapToolBtn")
            btn.setCheckable(True)
            btn.setChecked(label == "Color")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, name=label: self.set_export_tone(name))
            tone.addWidget(btn)
            self._export_btns.append(btn)
        sl.addLayout(tone)
        for key, label, _idx in CHANNELS:
            btn = QPushButton(f"{key} — {label}")
            btn.setObjectName("mapToolBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, k=key: self.export_channel(k))
            sl.addWidget(btn)
        sl.addStretch(1)
        return page

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("mapSectionLabel")
        return lab

    def _spin(self, lo: int, hi: int, val: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(lo, hi)
        box.setValue(val)
        return box

    def _dbl_spin(self, lo: float, hi: float, val: float, step: float):
        from PySide6.QtWidgets import QDoubleSpinBox

        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setSingleStep(step)
        box.setValue(val)
        return box

    def _selected(self) -> set[str]:
        return {k for k, box in self._ch_boxes.items() if box.isChecked()}

    def _on_ch_toggle(self, key: str) -> None:
        del key
        self._sync_brush()
        self._refresh()

    def _sync_brush(self, *_args) -> None:
        self._top.set_brush(
            selected=self._selected(),
            radius=int(self._brush.value()),
            value=int(self._paint_val.value()),
            hardness=self._hard.value() / 100.0,
            opacity=1.0,
        )

    def _click_tab(self, index: int) -> None:
        self.set_tool_tab(index)
        host = self.window()
        bridge = getattr(host, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_form()

    def set_tool_tab(self, index: int) -> None:
        self._tool_tab = max(0, min(3, int(index)))
        self._tool_stack.setCurrentIndex(self._tool_tab)
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == self._tool_tab)
        painting = self._tool_tab == 2
        self._paint_chk.setChecked(painting)
        if painting:
            self._top.set_mode(self._paint_tool.lower())
        else:
            self._top.set_mode("off")
            self.cancel_stamp()

    def set_paint_tool(self, name: str) -> None:
        self._paint_tool = name if name in ("Brush", "Stamp", "Magic") else "Brush"
        if self._tool_tab == 2:
            self._top.set_mode(self._paint_tool.lower())

    def _apply(self, new_pixels: np.ndarray, msg: str) -> None:
        if self._session is None:
            self.status.emit("Open a parameter map first")
            return
        self._session.apply(new_pixels)
        self._refresh()
        self.status.emit(msg)

    def _do_offset(self) -> None:
        if not self._session:
            return
        self._apply(
            apply_offset(self._session.pixels, self._selected(), int(self._offset.value())),
            f"Offset {int(self._offset.value())}",
        )

    def _do_scale(self) -> None:
        if not self._session:
            return
        self._apply(
            apply_scale(self._session.pixels, self._selected(), float(self._scale.value())),
            f"Scale ×{float(self._scale.value()):.2f}",
        )

    def _do_fill(self) -> None:
        if not self._session:
            return
        self._apply(
            apply_fill(self._session.pixels, self._selected(), int(self._fill.value())),
            f"Fill {int(self._fill.value())}",
        )

    def _do_bc(self) -> None:
        if not self._session:
            return
        self._apply(
            apply_brightness_contrast(
                self._session.pixels,
                self._selected(),
                int(self._bright.value()),
                float(self._contrast.value()),
            ),
            "Brightness / contrast",
        )

    def _do_mean(self) -> None:
        if not self._session:
            return
        self._apply(
            apply_retarget_mean(
                self._session.pixels, self._selected(), int(self._mean.value())
            ),
            f"Mean → {int(self._mean.value())}",
        )

    def _do_invert(self) -> None:
        if not self._session:
            return
        self._apply(apply_invert(self._session.pixels, self._selected()), "Invert")

    def _do_overlay(self) -> None:
        if not self._session:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Overlay image",
            str(self._session.path.parent),
            "Images (*.png *.tga *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if not path:
            return
        src = open_parameter(path)
        self._apply(
            apply_overlay(
                self._session.pixels,
                self._selected(),
                src,
                mode=self._ov_mode.currentText(),
                opacity=self._ov_opacity.value() / 100.0,
                source_channel=self._ov_src.currentText(),
            ),
            f"Overlay {Path(path).name}",
        )

    def open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open parameter maps",
            "",
            "Images (*.png *.tga *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if paths:
            self.add_maps([Path(p) for p in paths])

    def add_maps(self, paths: list[Path]) -> None:
        added = 0
        focus: _MapSlot | None = None
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
                continue
            existing = next((s for s in self._slots if _same_path(s.path, path)), None)
            if existing is None:
                slot = _MapSlot(path=path)
                self._slots.append(slot)
                self._insert_row(len(self._slots) - 1)
                self._pool.start(_DecodeJob(str(path), "map", self._bus.ready))
                added += 1
                focus = slot
            else:
                focus = existing
        if focus is not None:
            self._select_slot(focus)
        if added:
            self.status.emit(f"Added {added} map" + ("s" if added != 1 else ""))
        elif focus is not None:
            self.status.emit(focus.path.name)

    def clear_maps(self) -> None:
        self._slots.clear()
        self._session = None
        self._focus = None
        self._mask = None
        self._top.set_session(None)
        self._top.set_mask(None)
        self._top.clear_stamp()
        self._overlays.clear()
        self._top.set_image(None)
        self._channels.clear()
        self._fill_table(None)
        self._path_lab.setText("No file")
        self._stats.setText("")
        self.status.emit("Cleared maps")
        self._sync_bridge()

    def remove_selected_maps(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        if not rows and self._session is not None:
            rows = [i for i, slot in enumerate(self._slots) if slot.session is self._session]
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._slots):
                del self._slots[row]
        self._session = None
        self._fill_table(self._slots[0].path if self._slots else None)
        if not self._slots:
            self.clear_maps()

    def load_path(self, path: Path) -> None:
        self.add_maps([Path(path)])

    def _insert_row(self, row: int) -> None:
        slot = self._slots[row]
        self._selecting = True
        self._table.insertRow(row)
        self._table.setItem(row, 0, self._name_item(slot))
        self._table.setItem(row, 1, QTableWidgetItem(self._file_size(slot.path)))
        self._selecting = False

    def _name_item(self, slot: _MapSlot) -> QTableWidgetItem:
        mark = ""
        if slot.session is None:
            mark = " …"
        elif slot.session.dirty:
            mark = " ·"
        item = QTableWidgetItem(slot.path.name + mark)
        item.setData(Qt.ItemDataRole.UserRole, str(slot.path))
        if slot.thumb is not None:
            item.setIcon(slot.thumb)
        return item

    def _file_size(self, path: Path) -> str:
        try:
            return _fmt_size(path.stat().st_size)
        except OSError:
            return "—"

    def _select_slot(self, slot: _MapSlot) -> None:
        self._focus = slot
        try:
            row = self._slots.index(slot)
        except ValueError:
            return
        self._table.selectRow(row)

    def _fill_table(self, focus: Path | None) -> None:
        self._selecting = True
        self._table.setRowCount(0)
        focus_row = 0
        for row, slot in enumerate(self._slots):
            self._table.insertRow(row)
            self._table.setItem(row, 0, self._name_item(slot))
            self._table.setItem(row, 1, QTableWidgetItem(self._file_size(slot.path)))
            if focus is not None and _same_path(slot.path, focus):
                focus_row = row
        self._selecting = False
        if self._slots:
            self._table.selectRow(focus_row)
        else:
            self._show_session(None)

    def _on_decoded(self, path: str, kind: str, payload: object, thumb: object) -> None:
        if payload is None:
            self.status.emit(f"Could not read {Path(path).name}")
            return
        if kind != "map":
            self._apply_overlay(kind, np.asarray(payload), Path(path).name)
            return
        slot = next((s for s in self._slots if _same_path(s.path, Path(path))), None)
        if slot is None or slot.session is not None:
            return
        rgba = np.asarray(payload, dtype=np.uint8)
        slot.session = TexMapSession(path=Path(path), role="parameter", pixels=rgba, dirty=False)
        if isinstance(thumb, np.ndarray):
            slot.thumb = QIcon(_rgba_to_pixmap(thumb))
        row = self._slots.index(slot)
        self._selecting = True
        self._table.setItem(row, 0, self._name_item(slot))
        self._selecting = False
        if slot is self._focus or self._table.currentRow() == row:
            self._show_session(slot.session)

    def _on_row(self) -> None:
        if self._selecting:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._slots):
            return
        self._focus = self._slots[row]
        self._show_session(self._slots[row].session)

    def _show_session(self, session: TexMapSession | None) -> None:
        if self._session is not None and self._session is not session:
            previous = next((s for s in self._slots if s.session is self._session), None)
            if previous is not None:
                previous.overlays = self._overlays
        self._session = session
        self._mask = None
        self._top.set_session(session)
        self._top.set_mask(None)
        self._top.clear_stamp()
        self._stamp_lab.setText("Drop an image on the map to place it")
        if self._focus is not None and self._focus.session is session:
            self._overlays = self._focus.overlays
        else:
            found = next(
                (s for s in self._slots if session is not None and s.session is session),
                None,
            )
            self._overlays = found.overlays if found is not None else {}
        if session is None:
            waiting = any(slot.session is None for slot in self._slots)
            self._path_lab.setText("Reading…" if waiting else "No file")
            self._top.set_image(None)
            self._channels.clear()
            self._stats.setText("")
        else:
            self._path_lab.setText(session.path.name)
            self._refresh()
            self._top.fit()
            self.status.emit(f"Parameter · {session.path.name}")
        self._sync_bridge()

    def _flags(self) -> dict[str, bool]:
        return {key.lower(): self._ch_boxes[key].isChecked() for key in CHANNEL_KEYS}

    def _preview_pixmap(self, rgba: np.ndarray) -> QPixmap:
        view = view_param_composite(rgba, **self._flags())
        if self._gray_channels:
            tone = luminance(view)
            view = view.copy()
            view[..., 0] = tone
            view[..., 1] = tone
            view[..., 2] = tone
        return _rgba_to_pixmap(view)

    def _refresh_top(self) -> None:
        if self._session is None:
            return
        self._top.set_image(self._preview_pixmap(self._display_pixels()))

    def _display_pixels(self) -> np.ndarray:
        src = self._session.pixels if self._session is not None else None
        if src is None:
            return np.zeros((1, 1, 4), np.uint8)
        original = [key for key, ov in self._overlays.items() if ov.get("view") == "original"]
        if not original:
            return src
        out = src.copy()
        for key in original:
            out[..., CHANNEL_INDEX[key]] = self._overlays[key]["before"]
        return out

    def _push_channels(self, rgba: np.ndarray) -> None:
        small = downscale_rgba(rgba, 480)
        pix = {
            key: _rgba_to_pixmap(
                view_plane(small[..., CHANNEL_INDEX[key]], key, gray=self._gray_channels)
            )
            for key in CHANNEL_KEYS
        }
        self._channels.set_state(
            pix,
            gray=self._gray_channels,
            overlay={key: ov["view"] for key, ov in self._overlays.items()},
            names={key: ov["name"] for key, ov in self._overlays.items()},
        )

    def _reconcile_overlays(self) -> None:
        if self._session is None:
            self._overlays.clear()
            return
        gone = []
        for key, ov in self._overlays.items():
            current = self._session.pixels[..., CHANNEL_INDEX[key]]
            before = ov["before"]
            if current.shape != before.shape or np.array_equal(current, before):
                gone.append(key)
        for key in gone:
            del self._overlays[key]

    def _queue_overlay(self, key: str, path: Path) -> None:
        if self._session is None:
            self.status.emit("Open a parameter map first")
            return
        self.status.emit(f"Reading {Path(path).name}…")
        self._pool.start(_DecodeJob(str(path), f"ov:{key}", self._bus.ready))

    def _apply_overlay(self, kind: str, plane: np.ndarray, name: str) -> None:
        if self._session is None or not kind.startswith("ov:"):
            return
        key = kind[3:]
        if key not in CHANNEL_INDEX:
            return
        height, width = self._session.pixels.shape[:2]
        gray = np.asarray(plane, dtype=np.uint8)
        if gray.shape[:2] != (height, width):
            gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
        idx = CHANNEL_INDEX[key]
        previous = self._overlays.get(key)
        before = previous["before"] if previous else self._session.pixels[..., idx].copy()
        self._session.snapshot()
        self._session.pixels[..., idx] = gray
        self._session.dirty = True
        self._overlays[key] = {"before": before, "view": "modified", "name": name}
        self._refresh()
        tint = {"R": "red", "G": "green", "B": "blue", "A": "white"}[key]
        self.status.emit(f"{key} ← {name} · {tint}")

    def set_export_tone(self, name: str) -> None:
        self._export_tone = "Grey" if name == "Grey" else "Color"
        for btn in self._export_btns:
            btn.setChecked(btn.text() == self._export_tone)

    def export_channel(self, key: str) -> None:
        if self._session is None or key not in CHANNEL_INDEX:
            self.status.emit("Open a parameter map first")
            return
        color = self._export_tone != "Grey"
        plane = self._display_pixels()[..., CHANNEL_INDEX[key]]
        image = view_plane(plane, key, gray=not color)
        suffix = "color" if color else "grey"
        default = self._session.path.with_name(f"{self._session.path.stem}_{key}_{suffix}.png")
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {key}",
            str(default),
            "Images (*.png *.tga *.bmp *.tif *.tiff *.webp)",
        )
        if not path:
            return
        from ...io.tex_map_edit import save_trainz_image

        out = save_trainz_image(Path(path), image, bak=False)
        self.status.emit(f"Exported {out.name}")

    def _set_overlay_view(self, key: str, view: str) -> None:
        ov = self._overlays.get(key)
        if ov is None or view not in ("original", "modified"):
            return
        ov["view"] = view
        self._refresh()

    def _clear_overlay(self, key: str) -> None:
        ov = self._overlays.pop(key, None)
        if ov is None or self._session is None:
            return
        self._session.snapshot()
        self._session.pixels[..., CHANNEL_INDEX[key]] = ov["before"]
        self._session.dirty = True
        self._refresh()
        self.status.emit(f"Removed {key} overlay")

    def _set_channel_gray(self, gray: bool) -> None:
        self._gray_channels = bool(gray)
        shown = None if self._session is None else self._display_pixels()
        if shown is None:
            self._channels.set_state({}, gray=self._gray_channels, overlay={}, names={})
            return
        self._top.set_image(self._preview_pixmap(shown))
        self._push_channels(shown)

    def _refresh(self) -> None:
        if self._session is None:
            self._top.set_image(None)
            self._channels.clear()
            self._stats.setText("")
            self._sync_bridge()
            return
        self._reconcile_overlays()
        shown = self._display_pixels()
        self._top.set_image(self._preview_pixmap(shown))
        self._push_channels(shown)
        st = channel_stats(self._session.pixels)
        parts = [f"{k} {v[0]}–{v[1]} μ{v[2]:.0f}" for k, v in st.items()]
        dirty = " · dirty" if self._session.dirty else ""
        sel = ""
        if self._mask is not None:
            sel = f" · select {int(self._mask.sum())}"
        self._stats.setText(" · ".join(parts) + dirty + sel)
        self._touch_row_name()
        self._sync_bridge()

    def _touch_row_name(self) -> None:
        if self._session is None:
            return
        for row, slot in enumerate(self._slots):
            session = slot.session
            if session is self._session:
                item = self._table.item(row, 0)
                if item is not None:
                    item.setText(session.path.name + (" ·" if session.dirty else ""))
                break

    def _sync_bridge(self) -> None:
        host = self.window()
        bridge = getattr(host, "_assets_bridge", None)
        if bridge is not None:
            bridge.sync_form()

    def _on_magic(self, x: float, y: float) -> None:
        if self._session is None:
            return
        self._mask = magic_mask(
            self._session.pixels,
            x,
            y,
            tol=int(self._tol.value()),
            contiguous=self._contiguous.isChecked(),
        )
        self._top.set_mask(self._mask)
        self._refresh()
        self.status.emit(f"Magic select {int(self._mask.sum())} px")

    def clear_selection(self) -> None:
        self._mask = None
        self._top.set_mask(None)
        self._refresh()

    def _on_canvas_drop(self, path: Path, pos: QPoint) -> None:
        if self._tool_tab == 2 and self._session is not None:
            self._load_stamp(Path(path), pos)
            return
        self.add_maps([Path(path)])

    def _load_stamp(self, path: Path, pos: QPoint) -> None:
        src = open_parameter(path)
        pt = self._top._img_pos(pos)
        if pt is None:
            pt = (0.0, 0.0)
            origin = (0.0, 0.0)
        else:
            origin = (pt[0] - src.shape[1] / 2, pt[1] - src.shape[0] / 2)
        self._paint_tool = "Stamp"
        self._top.set_mode("stamp")
        self._top.set_stamp(src, origin[0], origin[1])
        self._stamp_lab.setText(path.name)
        self.status.emit(f"Place {path.name} — drag, then Apply stamp")
        self._sync_bridge()

    def apply_stamp(self) -> None:
        src = self._top.stamp_pixels()
        if self._session is None or src is None:
            self.status.emit("Drop an image on the map first")
            return
        x, y = self._top.stamp_origin()
        self._apply(
            apply_stamp_at(
                self._session.pixels,
                self._selected(),
                src,
                x,
                y,
                mode=self._ov_mode.currentText(),
                opacity=self._ov_opacity.value() / 100.0,
                source_channel=self._ov_src.currentText(),
                mask=self._mask,
            ),
            "Stamp",
        )
        self.cancel_stamp()

    def cancel_stamp(self) -> None:
        self._top.clear_stamp()
        if hasattr(self, "_stamp_lab"):
            self._stamp_lab.setText("Drop an image on the map to place it")

    def undo(self) -> None:
        if self._session and self._session.undo():
            self._refresh()
            self.status.emit("Undo")

    def redo(self) -> None:
        if self._session and self._session.redo():
            self._refresh()
            self.status.emit("Redo")

    def revert(self) -> None:
        if self._session:
            self._session.revert()
            self._refresh()
            self.status.emit("Reverted")

    def save(self) -> None:
        if self._session is None:
            self.status.emit("Nothing to save")
            return
        out = save_parameter(self._session.path, self._session.pixels, bak=True)
        self._session.dirty = False
        self._refresh()
        self.status.emit(f"Saved {out.name}")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in IMAGE_EXTS:
                paths.append(path)
        if paths:
            self.add_maps(paths)
