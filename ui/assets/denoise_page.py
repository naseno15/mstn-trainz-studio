"""Bake Denoise page — OIDN / OpenCV; preview in memory; Save overwrites."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...io.bake_denoise import (
    IMAGE_EXTS,
    DenoiseSettings,
    bgr_from_rgba,
    compose_with_alpha,
    denoise_image,
    load_bake_image,
    oidn_available,
)
from ...io.tex_map_edit import save_trainz_image
from ..theme import app_font


def _rgba_to_pixmap(rgba: np.ndarray) -> QPixmap:
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


class _DenoiseWorker(QThread):
    progress = Signal(str, float)
    finished_ok = Signal(object, str)  # rgba, engine
    failed = Signal(str)

    def __init__(self, rgba: np.ndarray, settings: DenoiseSettings) -> None:
        super().__init__()
        self._rgba = np.asarray(rgba, dtype=np.uint8).copy()
        self._settings = settings

    def run(self) -> None:  # noqa: N802
        try:
            bgr, alpha = bgr_from_rgba(self._rgba)
            out, engine = denoise_image(
                bgr,
                self._settings,
                progress=lambda m, f: self.progress.emit(m, f),
            )
            rgba = compose_with_alpha(out, alpha)
            self.finished_ok.emit(rgba, engine)
        except Exception as e:
            self.failed.emit(str(e))


class _Preview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(280)
        self._pix: QPixmap | None = None
        self._caption = "Drop an AO / lightmap bake…"

    def set_image(self, pix: QPixmap | None, caption: str = "") -> None:
        self._pix = pix
        if caption:
            self._caption = caption
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(18, 20, 26))
        if self._pix is None or self._pix.isNull():
            p.setPen(QColor(140, 148, 160))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._caption)
            return
        pix = self._pix.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - pix.width()) // 2
        y = (self.height() - pix.height()) // 2
        p.drawPixmap(x, y, pix)


class DenoisePage(QWidget):
    """Preview page — tools live in the host right dock (``tools_panel``)."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._orig: np.ndarray | None = None
        self._work: np.ndarray | None = None
        self._dirty = False
        self._worker: _DenoiseWorker | None = None
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        panel = QFrame()
        panel.setObjectName("glassPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        title = QLabel("Bake Denoise")
        title.setObjectName("welcomeTitle")
        title.setFont(app_font(16, QFont.Weight.Bold))
        lay.addWidget(title)

        eng = "OIDN ready" if oidn_available() else "OIDN missing · OpenCV fallback"
        tip = QLabel(
            f"AO / lightmap grain · {eng}. Denoise previews in memory — Save overwrites (+ .bak once)."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self._preview = _Preview()
        lay.addWidget(self._preview, 1)
        root.addWidget(panel, 1)

        self.tools_panel = self._build_tools()

    def _build_tools(self) -> QWidget:
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sl = QVBoxLayout(body)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)

        open_btn = QPushButton("Open bake…")
        open_btn.setObjectName("mapToolBtn")
        open_btn.clicked.connect(self.open_file)
        sl.addWidget(open_btn)
        self._path_lab = QLabel("No file")
        self._path_lab.setObjectName("mutedTip")
        self._path_lab.setWordWrap(True)
        sl.addWidget(self._path_lab)

        sl.addWidget(self._lab("Strength"))
        self._strength = QComboBox()
        for key, label in (
            ("light", "Light"),
            ("balanced", "Balanced"),
            ("heavy", "Heavy (default)"),
            ("nuclear", "Nuclear"),
        ):
            self._strength.addItem(label, key)
        self._strength.setCurrentIndex(2)
        sl.addWidget(self._strength)

        self._prefer_oidn = QCheckBox("Prefer Intel OIDN")
        self._prefer_oidn.setChecked(True)
        self._prefer_oidn.setEnabled(oidn_available())
        sl.addWidget(self._prefer_oidn)

        self._preserve = QCheckBox("Lock black UV padding")
        self._preserve.setChecked(True)
        sl.addWidget(self._preserve)

        row = QHBoxLayout()
        row.addWidget(QLabel("Black ≤"), 1)
        self._black = QSpinBox()
        self._black.setRange(0, 64)
        self._black.setValue(8)
        row.addWidget(self._black, 2)
        sl.addLayout(row)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        sl.addWidget(self._bar)
        self._prog_lab = QLabel("Idle")
        self._prog_lab.setObjectName("mutedTip")
        sl.addWidget(self._prog_lab)

        run = QPushButton("Denoise")
        run.setObjectName("accentBtn")
        run.clicked.connect(self.run_denoise)
        sl.addWidget(run)

        show_row = QHBoxLayout()
        orig_btn = QPushButton("Show original")
        orig_btn.setObjectName("mapGhostBtn")
        orig_btn.clicked.connect(self._show_orig)
        work_btn = QPushButton("Show result")
        work_btn.setObjectName("mapGhostBtn")
        work_btn.clicked.connect(self._show_work)
        show_row.addWidget(orig_btn)
        show_row.addWidget(work_btn)
        sl.addLayout(show_row)

        revert = QPushButton("Revert")
        revert.setObjectName("mapGhostBtn")
        revert.clicked.connect(self.revert)
        sl.addWidget(revert)

        save = QPushButton("Save (overwrite)")
        save.setObjectName("accentBtn")
        save.clicked.connect(self.save)
        sl.addWidget(save)
        sl.addStretch(1)
        return body

    def _lab(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("mapSectionLabel")
        return lab

    def _settings(self) -> DenoiseSettings:
        return DenoiseSettings(
            strength=str(self._strength.currentData()),
            prefer_oidn=bool(self._prefer_oidn.isChecked()),
            preserve_black=bool(self._preserve.isChecked()),
            black_threshold=int(self._black.value()),
        )

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open bake image",
            "",
            "Images (*.png *.jpg *.jpeg *.tga *.tif *.tiff *.bmp *.webp)",
        )
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path) -> None:
        path = Path(path)
        if path.suffix.lower() not in IMAGE_EXTS:
            self.status.emit(f"Unsupported: {path.suffix}")
            return
        try:
            bgr, alpha = load_bake_image(path)
            self._orig = compose_with_alpha(bgr, alpha)
        except Exception as e:
            self.status.emit(f"Load failed: {e}")
            return
        self._path = path
        self._work = None
        self._dirty = False
        self._path_lab.setText(path.name)
        self._preview.set_image(_rgba_to_pixmap(self._orig), path.name)
        self._bar.setValue(0)
        self._prog_lab.setText("Idle")
        self.status.emit(f"Bake · {path.name}")

    def run_denoise(self) -> None:
        if self._orig is None:
            self.status.emit("Open a bake image first")
            return
        if self._worker is not None and self._worker.isRunning():
            self.status.emit("Denoise already running")
            return
        self._bar.setValue(0)
        self._prog_lab.setText("Starting…")
        self._worker = _DenoiseWorker(self._orig, self._settings())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_progress(self, msg: str, frac: float) -> None:
        self._bar.setValue(int(max(0.0, min(1.0, frac)) * 100))
        self._prog_lab.setText(msg)

    def _on_done(self, rgba: object, engine: str) -> None:
        self._work = np.asarray(rgba, dtype=np.uint8)
        self._dirty = True
        self._bar.setValue(100)
        self._prog_lab.setText(f"Done · {engine}")
        self._preview.set_image(_rgba_to_pixmap(self._work))
        self.status.emit(f"Denoised via {engine} — Save to overwrite")

    def _on_fail(self, err: str) -> None:
        self._prog_lab.setText("Failed")
        self.status.emit(f"Denoise failed: {err}")

    def _show_orig(self) -> None:
        if self._orig is not None:
            self._preview.set_image(_rgba_to_pixmap(self._orig))

    def _show_work(self) -> None:
        if self._work is not None:
            self._preview.set_image(_rgba_to_pixmap(self._work))

    def revert(self) -> None:
        if self._orig is None:
            return
        self._work = None
        self._dirty = False
        self._preview.set_image(_rgba_to_pixmap(self._orig))
        self._bar.setValue(0)
        self._prog_lab.setText("Idle")
        self.status.emit("Reverted")

    def save(self) -> None:
        if self._path is None:
            self.status.emit("Nothing to save")
            return
        pixels = self._work if self._work is not None else self._orig
        if pixels is None:
            self.status.emit("Nothing to save")
            return
        out = save_trainz_image(self._path, pixels, bak=True)
        self._dirty = False
        self._orig = np.asarray(pixels, dtype=np.uint8).copy()
        self._work = None
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
