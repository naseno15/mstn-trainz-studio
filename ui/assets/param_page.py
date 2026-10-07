"""Parameter map editor page — Trainz RGBA channels + paint + Save overwrite."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
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
    channel_stats,
    open_parameter,
    paint_line,
    save_parameter,
    view_param_channels,
)
from ...io.tex_map_edit import TexMapSession
from ..theme import app_font


def _rgba_to_pixmap(rgba: np.ndarray) -> QPixmap:
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


class _PaintCanvas(QWidget):
    """Zoomable preview — paints when paint mode is on."""

    painted = Signal()
    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self._pix: QPixmap | None = None
        self._scale = 1.0
        self._origin = QPoint(0, 0)
        self._drag_pan = False
        self._last = QPoint()
        self._paint_on = False
        self._session: TexMapSession | None = None
        self._selected: set[str] = set()
        self._brush = 16
        self._value = 128
        self._hardness = 0.6
        self._opacity = 1.0
        self._stroke = False
        self._img_last: tuple[float, float] | None = None

    def set_session(self, session: TexMapSession | None) -> None:
        self._session = session

    def set_paint_mode(self, on: bool) -> None:
        self._paint_on = on
        self.setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor
        )

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

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        self._scale = max(0.05, min(32.0, self._scale * factor))
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and not self._paint_on
        ):
            self._drag_pan = True
            self._last = event.position().toPoint()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._paint_on and self._session:
            pt = self._img_pos(event.position().toPoint())
            if pt is None:
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
            )
            self._img_last = pt
            self._session.dirty = True
            self.painted.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._drag_pan = False
            self._stroke = False
            self._img_last = None

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(18, 20, 26))
        if self._pix is None or self._pix.isNull():
            p.setPen(QColor(140, 148, 160))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop a parameter map…")
            return
        w = int(self._pix.width() * self._scale)
        h = int(self._pix.height() * self._scale)
        x = int(self.width() / 2 + self._origin.x() - w / 2)
        y = int(self.height() / 2 + self._origin.y() - h / 2)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._scale < 2.5)
        p.drawPixmap(x, y, w, h, self._pix)


class ParameterPage(QWidget):
    """Full page — edit Parameter maps; Save overwrites (+ ``.bak`` once)."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session: TexMapSession | None = None
        self._solo: str | None = None
        self._ch_on = {k: True for k in CHANNEL_KEYS}
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("glassPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        title = QLabel("Parameter map")
        title.setObjectName("welcomeTitle")
        title.setFont(app_font(16, QFont.Weight.Bold))
        lay.addWidget(title)
        tip = QLabel(
            "R=Emissive · G=Roughness · B=AO · A=Metallic — edits stay in memory until Save."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(12)

        self._canvas = _PaintCanvas()
        self._canvas.painted.connect(self._refresh)
        body.addWidget(self._canvas, 1)

        side = QFrame()
        side.setObjectName("mapRoleWell")
        side.setFixedWidth(300)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 10, 10, 10)
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
        for lab, w in (
            ("Offset", self._offset),
            ("Scale", self._scale),
            ("Fill", self._fill),
            ("Bright", self._bright),
            ("Contrast", self._contrast),
            ("→ Mean", self._mean),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab), 1)
            row.addWidget(w, 2)
            sl.addLayout(row)

        tools = QHBoxLayout()
        for label, slot in (
            ("Offset", self._do_offset),
            ("Scale", self._do_scale),
            ("Fill", self._do_fill),
        ):
            b = QPushButton(label)
            b.setObjectName("mapToolBtn")
            b.setFixedHeight(28)
            b.clicked.connect(slot)
            tools.addWidget(b)
        sl.addLayout(tools)
        tools2 = QHBoxLayout()
        for label, slot in (
            ("B/C", self._do_bc),
            ("Mean", self._do_mean),
            ("Invert", self._do_invert),
        ):
            b = QPushButton(label)
            b.setObjectName("mapToolBtn")
            b.setFixedHeight(28)
            b.clicked.connect(slot)
            tools2.addWidget(b)
        sl.addLayout(tools2)

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

        sl.addWidget(self._section("PAINT"))
        self._paint_chk = QCheckBox("Paint mode")
        self._paint_chk.toggled.connect(self._canvas.set_paint_mode)
        sl.addWidget(self._paint_chk)
        self._brush = self._spin(1, 256, 16)
        self._paint_val = self._spin(0, 255, 128)
        self._hard = QSlider(Qt.Orientation.Horizontal)
        self._hard.setRange(0, 100)
        self._hard.setValue(60)
        for lab, w in (("Radius", self._brush), ("Value", self._paint_val)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab), 1)
            row.addWidget(w, 2)
            sl.addLayout(row)
        sl.addWidget(QLabel("Hardness"))
        sl.addWidget(self._hard)
        for w in (self._brush, self._paint_val, self._hard):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._sync_brush)
        self._sync_brush()

        hist = QHBoxLayout()
        for label, slot in (("Undo", self.undo), ("Redo", self.redo), ("Revert", self.revert)):
            b = QPushButton(label)
            b.setObjectName("mapGhostBtn")
            b.setFixedHeight(28)
            b.clicked.connect(slot)
            hist.addWidget(b)
        sl.addLayout(hist)

        self._stats = QLabel("")
        self._stats.setObjectName("mutedTip")
        self._stats.setWordWrap(True)
        sl.addWidget(self._stats)

        save = QPushButton("Save (overwrite)")
        save.setObjectName("accentBtn")
        save.setFixedHeight(36)
        save.clicked.connect(self.save)
        sl.addWidget(save)
        sl.addStretch(1)

        body.addWidget(side)
        lay.addLayout(body, 1)
        root.addWidget(panel, 1)

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("mapSectionLabel")
        return lab

    def _spin(self, lo: int, hi: int, val: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _dbl_spin(self, lo: float, hi: float, val: float, step: float):
        from PySide6.QtWidgets import QDoubleSpinBox

        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(val)
        return s

    def _selected(self) -> set[str]:
        return {k for k, box in self._ch_boxes.items() if box.isChecked()}

    def _on_ch_toggle(self, key: str) -> None:
        del key
        self._sync_brush()
        self._refresh()

    def _sync_brush(self, *_args) -> None:
        self._canvas.set_brush(
            selected=self._selected(),
            radius=int(self._brush.value()),
            value=int(self._paint_val.value()),
            hardness=self._hard.value() / 100.0,
            opacity=1.0,
        )

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
            f"Retarget mean → {int(self._mean.value())}",
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
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open parameter map",
            "",
            "Images (*.png *.tga *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path) -> None:
        path = Path(path)
        if path.suffix.lower() not in IMAGE_EXTS:
            self.status.emit(f"Unsupported: {path.suffix}")
            return
        self._session = TexMapSession.open(path, role="parameter")
        self._canvas.set_session(self._session)
        self._path_lab.setText(path.name)
        self._refresh()
        self._canvas.fit()
        self.status.emit(f"Parameter · {path.name}")

    def _refresh(self) -> None:
        if self._session is None:
            self._canvas.set_image(None)
            self._stats.setText("")
            return
        view = view_param_channels(
            self._session.pixels,
            r=self._ch_boxes["R"].isChecked(),
            g=self._ch_boxes["G"].isChecked(),
            b=self._ch_boxes["B"].isChecked(),
            a=self._ch_boxes["A"].isChecked(),
            solo=self._solo,
        )
        self._canvas.set_image(_rgba_to_pixmap(view))
        st = channel_stats(self._session.pixels)
        parts = [f"{k} {v[0]}–{v[1]} μ{v[2]:.0f}" for k, v in st.items()]
        dirty = " · dirty" if self._session.dirty else ""
        self._stats.setText(" · ".join(parts) + dirty)

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
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in IMAGE_EXTS:
                self.load_path(p)
                break
