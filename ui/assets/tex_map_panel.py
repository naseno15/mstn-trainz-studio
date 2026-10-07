"""Texture Maps viewer / editor — Albedo · Normal · Parameter + channel mute.

Compact sidebar panel + Expand dialog with File/Edit/Image/Adjust/View menus.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...io.tex_map_edit import (
    TexMapSession,
    adjust_brightness_contrast,
    denoise_rgba,
    fill_channel,
    flip_green,
    flip_horizontal,
    flip_vertical,
    invert_channels,
    rgba_to_qimage_bytes,
    view_channels,
)
from ...io.texture import material_family
from ..theme import app_font

_MAP_ROLES = ("albedo", "normal", "parameter")
_ROLE_LABEL = {"albedo": "Albedo", "normal": "Normal", "parameter": "Parameter"}
_ROLE_COLOR = {
    "albedo": "#30d158",
    "normal": "#64d2ff",
    "parameter": "#ff9f0a",
}


def family_role_paths(paths: list[Path], family: str) -> dict[str, Path]:
    """``{role: path}`` for one material family from the Texture list."""
    out: dict[str, Path] = {}
    for p in paths:
        fam, role = material_family(p.name)
        if fam == family and role in _MAP_ROLES:
            out[role] = Path(p)
    return out


def _rgba_to_pixmap(rgba: np.ndarray) -> QPixmap:
    raw, w, h = rgba_to_qimage_bytes(rgba)
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


class _MapPreviewStage(QWidget):
    """Hero map stage — rounded glass, role accent rim, caption bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mapPreviewStage")
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pix: QPixmap | None = None
        self._accent = QColor("#ff5a1f")
        self._caption = ""
        self._sub = "Select a texture row"
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def set_image(self, pix: QPixmap | None) -> None:
        self._pix = pix
        self.update()

    def set_accent(self, color: QColor | str) -> None:
        self._accent = QColor(color) if isinstance(color, str) else QColor(color)
        self.update()

    def set_caption(self, title: str, sub: str = "") -> None:
        self._caption = title
        self._sub = sub
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 16.0
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        # Soft outer plate
        p.fillPath(path, QColor(18, 20, 26, 220))

        # Inner checker (clipped)
        p.save()
        p.setClipPath(path)
        cell = 10
        c0, c1 = QColor(38, 40, 48), QColor(28, 30, 36)
        for y in range(0, self.height() + cell, cell):
            for x in range(0, self.width() + cell, cell):
                p.fillRect(
                    x, y, cell, cell, c0 if ((x // cell) + (y // cell)) % 2 == 0 else c1
                )

        if self._pix is not None and not self._pix.isNull():
            pad = 10
            avail = QSize(
                max(8, self.width() - pad * 2),
                max(8, self.height() - pad * 2 - 40),
            )
            scaled = self._pix.scaled(
                avail,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height() - 36) // 2
            # Soft drop under texture
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 70))
            p.drawRoundedRect(
                QRectF(x + 3, y + 5, scaled.width(), scaled.height()), 6, 6
            )
            p.drawPixmap(x, y, scaled)
        else:
            p.setPen(QColor(160, 162, 170))
            f = app_font(13, QFont.Weight.DemiBold)
            p.setFont(f)
            p.drawText(
                self.rect().adjusted(12, 12, -12, -48),
                Qt.AlignmentFlag.AlignCenter,
                "Drop or select a map",
            )
            p.setPen(QColor(120, 122, 130))
            p.setFont(app_font(11, QFont.Weight.Medium))
            p.drawText(
                self.rect().adjusted(16, 40, -16, -40),
                Qt.AlignmentFlag.AlignCenter,
                "Albedo · Normal · Parameter",
            )

        # Bottom caption veil
        veil_h = 44
        veil = QLinearGradient(0, self.height() - veil_h, 0, self.height())
        veil.setColorAt(0.0, QColor(12, 14, 18, 0))
        veil.setColorAt(0.35, QColor(12, 14, 18, 160))
        veil.setColorAt(1.0, QColor(12, 14, 18, 220))
        p.fillRect(0, self.height() - veil_h, self.width(), veil_h, veil)
        if self._caption:
            p.setPen(QColor("#f5f5f7"))
            p.setFont(app_font(12, QFont.Weight.DemiBold))
            p.drawText(
                14,
                self.height() - 22,
                self._caption,
            )
        if self._sub:
            p.setPen(QColor(170, 172, 180))
            p.setFont(app_font(10, QFont.Weight.Medium))
            p.drawText(
                14,
                self.height() - 8,
                self._sub,
            )
        p.restore()

        # Accent rim
        pen = QPen(self._accent)
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        # Top accent glow line
        glow = QLinearGradient(r.left(), r.top(), r.right(), r.top())
        ac = QColor(self._accent)
        ac.setAlpha(0)
        mid = QColor(self._accent)
        mid.setAlpha(200)
        glow.setColorAt(0.0, ac)
        glow.setColorAt(0.5, mid)
        glow.setColorAt(1.0, ac)
        p.setPen(QPen(QBrush(glow), 2.2))
        p.drawLine(
            int(r.left() + 18),
            int(r.top() + 1),
            int(r.right() - 18),
            int(r.top() + 1),
        )
        p.end()


class _ZoomCanvas(QWidget):
    """Expand-dialog canvas — wheel zoom, drag pan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pix: QPixmap | None = None
        self._zoom = 1.0
        self._origin = QPoint(0, 0)
        self._drag: QPoint | None = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_image(self, pix: QPixmap | None) -> None:
        self._pix = pix
        self.update()

    def fit(self) -> None:
        if self._pix is None or self._pix.isNull() or self.width() < 8:
            return
        sx = self.width() / max(self._pix.width(), 1)
        sy = self.height() / max(self._pix.height(), 1)
        self._zoom = max(0.05, min(sx, sy) * 0.96)
        self._origin = QPoint(0, 0)
        self.update()

    def actual(self) -> None:
        self._zoom = 1.0
        self._origin = QPoint(0, 0)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else (1 / 1.12)
        self._zoom = max(0.05, min(32.0, self._zoom * factor))
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            return
        pos = event.position().toPoint()
        self._origin += pos - self._drag
        self._drag = pos
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        del event
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(28, 28, 32))
        cell = 10
        c0, c1 = QColor(44, 44, 48), QColor(32, 32, 36)
        for y in range(0, self.height(), cell):
            for x in range(0, self.width(), cell):
                p.fillRect(x, y, cell, cell, c0 if ((x // cell) + (y // cell)) % 2 else c1)
        if self._pix is None or self._pix.isNull():
            p.setPen(QColor(160, 160, 165))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select a map")
            p.end()
            return
        w = max(1, int(self._pix.width() * self._zoom))
        h = max(1, int(self._pix.height() * self._zoom))
        scaled = self._pix.scaled(
            w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2 + self._origin.x()
        y = (self.height() - scaled.height()) // 2 + self._origin.y()
        p.drawPixmap(x, y, scaled)
        p.end()


class TexMapEditorCore(QWidget):
    """Shared controls: role pills, channels, preview, quick adjust, save."""

    status = Signal(str)
    saved = Signal(object)  # Path
    role_changed = Signal(str)
    expand_requested = Signal()

    def __init__(self, *, compact: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._compact = compact
        self._session: TexMapSession | None = None
        self._maps: dict[str, Path] = {}
        self._role = "albedo"
        self._ch = [True, True, True, True]
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Hidden meta label — caption lives on the preview stage (kept for API).
        self._meta = QLabel("")
        self._meta.hide()

        # ── Map type (A / N / P) ─────────────────────────────
        role_well = QFrame()
        role_well.setObjectName("mapRoleWell")
        rw = QVBoxLayout(role_well)
        rw.setContentsMargins(8, 8, 8, 8)
        rw.setSpacing(6)
        role_head = QLabel("MAP")
        role_head.setObjectName("mapSectionLabel")
        rw.addWidget(role_head)
        role_row = QHBoxLayout()
        role_row.setSpacing(6)
        self._role_group = QButtonGroup(self)
        self._role_group.setExclusive(True)
        self._role_btns: dict[str, QPushButton] = {}
        role_obj = {
            "albedo": "mapRoleAlbedo",
            "normal": "mapRoleNormal",
            "parameter": "mapRoleParam",
        }
        for i, role in enumerate(_MAP_ROLES):
            btn = QPushButton(_ROLE_LABEL[role])
            btn.setObjectName(role_obj[role])
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(32)
            if role == self._role:
                btn.setChecked(True)
            self._role_group.addButton(btn, i)
            btn.clicked.connect(lambda _=False, r=role: self._pick_role(r))
            role_row.addWidget(btn, 1)
            self._role_btns[role] = btn
        rw.addLayout(role_row)
        lay.addWidget(role_well)

        # ── Hero preview ────────────────────────────────────
        if self._compact:
            self._preview = _MapPreviewStage()
            self._preview.setMinimumHeight(260)
            lay.addWidget(self._preview, 1)
        else:
            self._preview = None
            self._canvas = _ZoomCanvas()
            lay.addWidget(self._canvas, 1)

        # ── Channels ────────────────────────────────────────
        ch_well = QFrame()
        ch_well.setObjectName("mapRoleWell")
        cw = QVBoxLayout(ch_well)
        cw.setContentsMargins(8, 8, 8, 8)
        cw.setSpacing(6)
        ch_head_row = QHBoxLayout()
        ch_lab = QLabel("CHANNELS")
        ch_lab.setObjectName("mapSectionLabel")
        ch_head_row.addWidget(ch_lab)
        ch_head_row.addStretch(1)
        all_btn = QPushButton("RGB+A")
        all_btn.setObjectName("mapGhostBtn")
        all_btn.setFixedHeight(24)
        all_btn.setToolTip("Show all channels")
        all_btn.clicked.connect(self._all_channels)
        ch_head_row.addWidget(all_btn)
        cw.addLayout(ch_head_row)
        ch_row = QHBoxLayout()
        ch_row.setSpacing(6)
        self._ch_btns: list[QPushButton] = []
        ch_names = ("mapChR", "mapChG", "mapChB", "mapChA")
        for i, (name, obj) in enumerate(zip(("R", "G", "B", "A"), ch_names)):
            btn = QPushButton(name)
            btn.setObjectName(obj)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.setToolTip(f"{name} — click mute · double-click solo")
            btn.toggled.connect(lambda on, idx=i: self._set_channel(idx, on))
            btn.installEventFilter(self)
            ch_row.addWidget(btn, 1)
            self._ch_btns.append(btn)
        cw.addLayout(ch_row)
        lay.addWidget(ch_well)

        # ── Adjust ──────────────────────────────────────────
        adj = QFrame()
        adj.setObjectName("mapRoleWell")
        al = QVBoxLayout(adj)
        al.setContentsMargins(10, 10, 10, 10)
        al.setSpacing(8)
        adj_lab = QLabel("ADJUST")
        adj_lab.setObjectName("mapSectionLabel")
        al.addWidget(adj_lab)

        bc_row = QHBoxLayout()
        bc_row.setSpacing(10)
        bright_col = QVBoxLayout()
        bright_col.setSpacing(4)
        bright_col.addWidget(self._field_lab("Bright"))
        self._bright = QSlider(Qt.Orientation.Horizontal)
        self._bright.setRange(-100, 100)
        self._bright.setValue(0)
        bright_col.addWidget(self._bright)
        bc_row.addLayout(bright_col, 1)
        contrast_col = QVBoxLayout()
        contrast_col.setSpacing(4)
        contrast_col.addWidget(self._field_lab("Contrast"))
        self._contrast = QSlider(Qt.Orientation.Horizontal)
        self._contrast.setRange(-100, 100)
        self._contrast.setValue(0)
        contrast_col.addWidget(self._contrast)
        bc_row.addLayout(contrast_col, 1)
        al.addLayout(bc_row)

        dn_row = QHBoxLayout()
        dn_row.setSpacing(8)
        dn_col = QVBoxLayout()
        dn_col.setSpacing(4)
        dn_col.addWidget(self._field_lab("Denoise"))
        self._denoise = QSlider(Qt.Orientation.Horizontal)
        self._denoise.setRange(0, 100)
        self._denoise.setValue(40)
        self._denoise.setToolTip("Median + soft blur · normals re-normalized")
        dn_col.addWidget(self._denoise)
        dn_row.addLayout(dn_col, 1)
        al.addLayout(dn_row)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        for label, slot in (
            ("Apply B/C", self._apply_bc),
            ("Denoise", self.apply_denoise),
            ("Invert", self._invert),
            ("Flip G", self._flip_g),
        ):
            b = QPushButton(label)
            b.setObjectName("mapToolBtn")
            b.setFixedHeight(30)
            b.clicked.connect(slot)
            tool_row.addWidget(b, 1)
        al.addLayout(tool_row)

        hist_row = QHBoxLayout()
        hist_row.setSpacing(6)
        for label, slot in (("Undo", self.undo), ("Redo", self.redo)):
            b = QPushButton(label)
            b.setObjectName("mapGhostBtn")
            b.setFixedHeight(28)
            b.clicked.connect(slot)
            hist_row.addWidget(b, 1)
        al.addLayout(hist_row)
        lay.addWidget(adj)

        # ── Footer ──────────────────────────────────────────
        foot = QHBoxLayout()
        foot.setSpacing(8)
        if self._compact:
            exp = QPushButton("Expand")
            exp.setObjectName("mapGhostBtn")
            exp.setFixedHeight(36)
            exp.clicked.connect(self.expand_requested.emit)
            foot.addWidget(exp, 1)
        self._save_btn = QPushButton("Save map")
        self._save_btn.setObjectName("accentBtn")
        self._save_btn.setFixedHeight(36)
        self._save_btn.clicked.connect(self.save)
        foot.addWidget(self._save_btn, 2)
        lay.addLayout(foot)

        tip = QLabel("Double-click a channel to solo · Save → sibling .bak once")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)

    def _field_lab(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("lmFieldLabel")
        return lab

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj in getattr(self, "_ch_btns", []) and event.type() == QEvent.Type.MouseButtonDblClick:
            idx = self._ch_btns.index(obj)  # type: ignore[arg-type]
            self._solo(idx)
            return True
        return super().eventFilter(obj, event)

    # ── public API ───────────────────────────────────────────
    def set_family_maps(
        self,
        maps: dict[str, Path],
        *,
        prefer_role: str | None = None,
        prefer_path: Path | None = None,
    ) -> None:
        self._maps = {k: Path(v) for k, v in maps.items() if k in _MAP_ROLES}
        for role, btn in self._role_btns.items():
            btn.setEnabled(role in self._maps)
            if role in self._maps:
                btn.setToolTip(self._maps[role].name)
            else:
                btn.setToolTip(f"No {role} in this set")

        role = prefer_role if prefer_role in self._maps else None
        if role is None and prefer_path is not None:
            _, r = material_family(prefer_path.name)
            if r in self._maps:
                role = r
        if role is None:
            for r in _MAP_ROLES:
                if r in self._maps:
                    role = r
                    break
        if role is None and prefer_path is not None and prefer_path.is_file():
            # Plain image — treat as albedo slot for editing.
            self._maps["albedo"] = Path(prefer_path)
            self._role_btns["albedo"].setEnabled(True)
            role = "albedo"
        if role is None:
            self.clear()
            return
        self._pick_role(role, force=True)

    def clear(self) -> None:
        self._session = None
        self._maps = {}
        self._meta.setText("No image selected")
        if self._preview is not None:
            self._preview.set_caption("No map", "Select a texture row")
            self._preview.set_accent("#8e8e93")
        self._paint()
        for btn in self._role_btns.values():
            btn.setEnabled(False)

    def session(self) -> TexMapSession | None:
        return self._session

    def current_role(self) -> str:
        return self._role

    # ── internals ────────────────────────────────────────────
    def _pick_role(self, role: str, *, force: bool = False) -> None:
        if role not in self._maps:
            return
        if (
            not force
            and self._session is not None
            and self._session.dirty
            and self._session.path.resolve() != Path(self._maps[role]).resolve()
        ):
            ans = QMessageBox.question(
                self,
                "Unsaved map",
                f"Save changes to {self._session.path.name}?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                btn = self._role_btns.get(self._role)
                if btn:
                    btn.setChecked(True)
                return
            if ans == QMessageBox.StandardButton.Save:
                self.save()

        self._role = role
        btn = self._role_btns.get(role)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        path = self._maps[role]
        try:
            self._session = TexMapSession.open(path, role=role)
        except Exception as exc:  # noqa: BLE001
            self._session = None
            self._meta.setText(f"Load failed: {exc}")
            self._paint()
            self.status.emit(str(exc))
            return
        self._bright.setValue(0)
        self._contrast.setValue(0)
        self._refresh_meta()
        self._paint()
        self.role_changed.emit(role)

    def _refresh_meta(self) -> None:
        s = self._session
        if s is None:
            self._meta.setText("No image selected")
            if self._preview is not None:
                self._preview.set_caption("No map", "Select a texture row")
                self._preview.set_accent("#8e8e93")
            return
        h, w = s.pixels.shape[:2]
        dirty = " · edited" if s.dirty else ""
        color = _ROLE_COLOR.get(s.role, "#98989d")
        role_lab = _ROLE_LABEL.get(s.role, "Map")
        self._meta.setText(
            f'<span style="color:{color}">{role_lab}</span>'
            f"  ·  {s.path.name}  ·  {w}×{h}{dirty}"
        )
        if self._preview is not None:
            self._preview.set_accent(color)
            self._preview.set_caption(s.path.name, f"{role_lab}  ·  {w}×{h}{dirty}")

    def _ch_tuple(self) -> tuple[bool, bool, bool, bool]:
        return (self._ch[0], self._ch[1], self._ch[2], self._ch[3])

    def _set_channel(self, idx: int, on: bool) -> None:
        self._ch[idx] = bool(on)
        if not any(self._ch):
            # Keep at least one on.
            self._ch[idx] = True
            self._ch_btns[idx].blockSignals(True)
            self._ch_btns[idx].setChecked(True)
            self._ch_btns[idx].blockSignals(False)
        self._paint()

    def _solo(self, idx: int) -> None:
        for i, btn in enumerate(self._ch_btns):
            btn.blockSignals(True)
            btn.setChecked(i == idx)
            self._ch[i] = i == idx
            btn.blockSignals(False)
        self._paint()

    def _all_channels(self) -> None:
        for i, btn in enumerate(self._ch_btns):
            btn.blockSignals(True)
            btn.setChecked(True)
            self._ch[i] = True
            btn.blockSignals(False)
        self._paint()

    def _display_rgba(self) -> np.ndarray | None:
        if self._session is None:
            return None
        return view_channels(self._session.pixels, r=self._ch[0], g=self._ch[1], b=self._ch[2], a=self._ch[3])

    def _paint(self) -> None:
        rgba = self._display_rgba()
        pix = _rgba_to_pixmap(rgba) if rgba is not None else None
        if self._preview is not None:
            self._preview.set_image(pix)
        else:
            self._canvas.set_image(pix)

    def _apply_bc(self) -> None:
        if self._session is None:
            return
        b, c = self._bright.value(), self._contrast.value()
        if b == 0 and c == 0:
            return
        # Apply to RGB channels that are visible; A only if solo A or A checked with RGB.
        ch = (
            self._ch[0],
            self._ch[1],
            self._ch[2],
            self._ch[3] and not any(self._ch[:3]),
        )
        if not any(ch):
            ch = (True, True, True, False)
        new = adjust_brightness_contrast(
            self._session.pixels, brightness=float(b), contrast=float(c), channels=ch
        )
        self._session.apply(new)
        self._bright.setValue(0)
        self._contrast.setValue(0)
        self._refresh_meta()
        self._paint()
        self.status.emit("Applied brightness/contrast")

    def apply_denoise(self, strength: float | None = None) -> None:
        if self._session is None:
            return
        s = float(self._denoise.value() if strength is None else strength)
        if s < 0.5:
            self.status.emit("Denoise strength is 0")
            return
        ch = self._ch_tuple()
        if not any(ch):
            ch = (True, True, True, False)
        new = denoise_rgba(
            self._session.pixels,
            strength=s,
            role=self._session.role,
            channels=ch,
        )
        self._session.apply(new)
        self._refresh_meta()
        self._paint()
        self.status.emit(f"Denoise · strength {int(s)}")

    def _invert(self) -> None:
        if self._session is None:
            return
        self._session.apply(invert_channels(self._session.pixels, self._ch_tuple()))
        self._refresh_meta()
        self._paint()

    def _flip_g(self) -> None:
        if self._session is None:
            return
        self._session.apply(flip_green(self._session.pixels))
        self._refresh_meta()
        self._paint()
        self.status.emit("Flipped green (DX ↔ GL)")

    def flip_h(self) -> None:
        if self._session is None:
            return
        self._session.apply(flip_horizontal(self._session.pixels))
        self._refresh_meta()
        self._paint()

    def flip_v(self) -> None:
        if self._session is None:
            return
        self._session.apply(flip_vertical(self._session.pixels))
        self._refresh_meta()
        self._paint()

    def fill_active(self, value: int) -> None:
        if self._session is None:
            return
        # Fill every checked channel.
        pix = self._session.pixels
        for i, on in enumerate(self._ch):
            if on:
                pix = fill_channel(pix, i, value)
        self._session.apply(pix)
        self._refresh_meta()
        self._paint()

    def undo(self) -> None:
        if self._session and self._session.undo():
            self._refresh_meta()
            self._paint()

    def redo(self) -> None:
        if self._session and self._session.redo():
            self._refresh_meta()
            self._paint()

    def revert(self) -> None:
        if self._session is None:
            return
        self._session.revert()
        self._refresh_meta()
        self._paint()
        self.status.emit("Reverted from disk")

    def save(self) -> None:
        if self._session is None:
            return
        try:
            out = self._session.save(bak=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save failed", str(exc))
            self.status.emit(str(exc))
            return
        self._refresh_meta()
        self.saved.emit(out)
        self.status.emit(f"Saved {out.name} (+.bak if first)")

    def fit_view(self) -> None:
        if self._preview is None:
            self._canvas.fit()

    def actual_view(self) -> None:
        if self._preview is None:
            self._canvas.actual()


class TexMapExpandDialog(QDialog):
    """Fuller Photoshop-style shell — menus + large canvas."""

    saved = Signal(object)

    def __init__(
        self,
        maps: dict[str, Path],
        *,
        prefer_role: str | None = None,
        prefer_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Texture Map Editor")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(1100, 720)
        self._core = TexMapEditorCore(compact=False, parent=self)
        self._core.saved.connect(self.saved.emit)
        self._build_menus()
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 0, 8, 8)
        root.setSpacing(6)
        root.setMenuBar(self._menu)
        root.addWidget(self._core, 1)
        self._core.set_family_maps(maps, prefer_role=prefer_role, prefer_path=prefer_path)
        QTimer.singleShot(0, self._core.fit_view)

    def _build_menus(self) -> None:
        self._menu = QMenuBar(self)
        file_m = self._menu.addMenu("File")
        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._core.save)
        file_m.addAction(act_save)
        act_rev = QAction("Revert", self)
        act_rev.triggered.connect(self._core.revert)
        file_m.addAction(act_rev)
        file_m.addSeparator()
        act_close = QAction("Close", self)
        act_close.setShortcut(QKeySequence.StandardKey.Close)
        act_close.triggered.connect(self.accept)
        file_m.addAction(act_close)

        edit_m = self._menu.addMenu("Edit")
        act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        act_undo.triggered.connect(self._core.undo)
        edit_m.addAction(act_undo)
        act_redo = QAction("Redo", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        act_redo.triggered.connect(self._core.redo)
        edit_m.addAction(act_redo)
        edit_m.addSeparator()
        act_inv = QAction("Invert Channels", self)
        act_inv.setShortcut(QKeySequence("Ctrl+I"))
        act_inv.triggered.connect(self._core._invert)
        edit_m.addAction(act_inv)

        img_m = self._menu.addMenu("Image")
        act_fg = QAction("Flip Green (DX ↔ GL)", self)
        act_fg.triggered.connect(self._core._flip_g)
        img_m.addAction(act_fg)
        act_fh = QAction("Flip Horizontal", self)
        act_fh.triggered.connect(self._core.flip_h)
        img_m.addAction(act_fh)
        act_fv = QAction("Flip Vertical", self)
        act_fv.triggered.connect(self._core.flip_v)
        img_m.addAction(act_fv)

        adj_m = self._menu.addMenu("Adjustments")
        act_bc = QAction("Brightness / Contrast…", self)
        act_bc.triggered.connect(self._dlg_bc)
        adj_m.addAction(act_bc)
        act_dn = QAction("Denoise…", self)
        act_dn.triggered.connect(self._dlg_denoise)
        adj_m.addAction(act_dn)
        act_fill = QAction("Fill Active Channels…", self)
        act_fill.triggered.connect(self._dlg_fill)
        adj_m.addAction(act_fill)

        view_m = self._menu.addMenu("View")
        act_fit = QAction("Fit on Screen", self)
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.triggered.connect(self._core.fit_view)
        view_m.addAction(act_fit)
        act_1 = QAction("Actual Pixels", self)
        act_1.setShortcut(QKeySequence("Ctrl+1"))
        act_1.triggered.connect(self._core.actual_view)
        view_m.addAction(act_1)
        view_m.addSeparator()
        for i, name in enumerate(("R", "G", "B", "A")):
            act = QAction(f"Solo {name}", self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 2}"))
            act.triggered.connect(lambda _=False, idx=i: self._core._solo(idx))
            view_m.addAction(act)
        act_rgb = QAction("RGB + A", self)
        act_rgb.setShortcut(QKeySequence("Ctrl+`"))
        act_rgb.triggered.connect(self._core._all_channels)
        view_m.addAction(act_rgb)

    def _dlg_bc(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Brightness / Contrast")
        form = QFormLayout(dlg)
        b = QSlider(Qt.Orientation.Horizontal)
        b.setRange(-100, 100)
        c = QSlider(Qt.Orientation.Horizontal)
        c.setRange(-100, 100)
        form.addRow("Brightness", b)
        form.addRow("Contrast", c)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._core._bright.setValue(b.value())
        self._core._contrast.setValue(c.value())
        self._core._apply_bc()

    def _dlg_fill(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Fill Active Channels")
        form = QFormLayout(dlg)
        spin = QDoubleSpinBox()
        spin.setRange(0, 255)
        spin.setDecimals(0)
        spin.setValue(128)
        form.addRow("Value", spin)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._core.fill_active(int(spin.value()))

    def _dlg_denoise(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Denoise")
        form = QFormLayout(dlg)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(self._core._denoise.value())
        lab = QLabel(str(slider.value()))
        slider.valueChanged.connect(lambda v: lab.setText(str(v)))
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(lab)
        form.addRow("Strength", row)
        tip = QLabel("Median + soft blur · normal maps re-normalized · uses visible channels")
        tip.setWordWrap(True)
        form.addRow(tip)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._core._denoise.setValue(slider.value())
        self._core.apply_denoise(float(slider.value()))


class TexMapSidePanel(QWidget):
    """Sidebar Maps tab body."""

    status = Signal(str)
    saved = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.core = TexMapEditorCore(compact=True, parent=self)
        self.core.status.connect(self.status.emit)
        self.core.saved.connect(self.saved.emit)
        self.core.expand_requested.connect(self._expand)
        lay.addWidget(self.core, 1)
        self._maps: dict[str, Path] = {}
        self._prefer_path: Path | None = None

    def set_from_selection(
        self,
        paths: list[Path],
        selected: Path | None,
    ) -> None:
        if selected is None:
            self.core.clear()
            self._maps = {}
            self._prefer_path = None
            return
        fam, role = material_family(selected.name)
        maps = family_role_paths(paths, fam)
        if not maps and selected.is_file():
            maps = {}
        self._maps = maps
        self._prefer_path = selected
        self.core.set_family_maps(maps, prefer_role=role, prefer_path=selected)

    def _expand(self) -> None:
        maps = dict(self._maps)
        prefer = self.core.current_role()
        path = self._prefer_path
        if self.core.session() is not None:
            # Keep unsaved pixels? Expand reloads from disk — warn if dirty.
            s = self.core.session()
            if s is not None and s.dirty:
                ans = QMessageBox.question(
                    self,
                    "Expand",
                    "Save before Expand? Expand opens a fresh editor from disk.",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                )
                if ans == QMessageBox.StandardButton.Cancel:
                    return
                if ans == QMessageBox.StandardButton.Save:
                    self.core.save()
            path = s.path if s is not None else path
            maps = dict(self._maps)
            if s is not None and s.role:
                maps[s.role] = s.path
        dlg = TexMapExpandDialog(
            maps,
            prefer_role=prefer,
            prefer_path=path,
            parent=self.window(),
        )
        dlg.saved.connect(self.saved.emit)
        dlg.exec()
        # Reload sidebar from disk after expand closes.
        if path is not None:
            self.core.set_family_maps(maps, prefer_role=prefer, prefer_path=path)
