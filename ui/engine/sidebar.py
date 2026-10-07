"""Engine Tuner left sidebar — logo header · enginespec summary · action footer."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..frost import FROST_CONTENT_MARGINS, FrostGlassFrame
from ..smooth_scroll import enable_smooth_scroll_area
from ..theme import app_font
from .pressure import to_bar, to_kpa

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_LOGO_WHITE = _ASSETS / "mstn_logo_white.png"
_LOGO_CACHE: QPixmap | None = None


def _trim_transparent(pix: QPixmap) -> QPixmap:
    img = pix.toImage()
    if img.isNull():
        return pix
    w, h = img.width(), img.height()
    left, top, right, bottom = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < left:
        return pix
    return pix.copy(left, top, right - left + 1, bottom - top + 1)


def _logo_pixmap(width: int = 120, *, mode: str = "dark") -> QPixmap:
    global _LOGO_CACHE
    if not _LOGO_WHITE.is_file():
        empty = QPixmap(width, max(28, width // 4))
        empty.fill(QColor(0, 0, 0, 0))
        return empty
    if _LOGO_CACHE is None or _LOGO_CACHE.isNull():
        raw = QPixmap(str(_LOGO_WHITE))
        _LOGO_CACHE = _trim_transparent(raw) if not raw.isNull() else raw
    pix = _LOGO_CACHE.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    if mode == "light":
        out = QPixmap(pix.size())
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(out.rect(), QColor("#1d1d1f"))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawPixmap(0, 0, pix)
        p.end()
        return out
    return pix


def _hdr(cfg, key: str, default: str = "—") -> str:
    val = cfg.header.get(key)
    if val is None or val == "":
        return default
    return str(val)


class _NotchPick(QWidget):
    """Label above checkbox — numbers stay readable when the row is tight."""

    def __init__(self, notch: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.notch = notch
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lab = QLabel(str(notch))
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet("font-weight: 650; font-size: 11px;")
        self.cb = QCheckBox()
        self.cb.setToolTip(f"Clone target N{notch}")
        self.cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb_row = QHBoxLayout()
        cb_row.setContentsMargins(0, 0, 0, 0)
        cb_row.addStretch(1)
        cb_row.addWidget(self.cb)
        cb_row.addStretch(1)
        lay.addWidget(lab)
        lay.addLayout(cb_row)


class EngineSidebar(FrostGlassFrame):
    """Mesh-style frost side panel for Engine Tuner."""

    open_clicked = Signal()
    back_clicked = Signal()
    save_clicked = Signal()
    save_as_clicked = Signal()
    undo_clicked = Signal()
    redo_clicked = Signal()
    clone_requested = Signal(int, object)  # src, list[int] targets
    clone_higher_requested = Signal(int)  # src

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, radius=14.0)
        self.setObjectName("sidePanel")
        self.setMinimumWidth(280)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._theme = "dark"

        outer = QVBoxLayout(self)
        # inset for soft shadow ring painted inside FrostGlassFrame (same as Mesh)
        outer.setContentsMargins(*FROST_CONTENT_MARGINS)
        outer.setSpacing(10)

        # header — logo + Engine Tuner (Mesh sidebar style)
        logo_plate = QFrame()
        logo_plate.setObjectName("logoPlate")
        lp = QVBoxLayout(logo_plate)
        lp.setContentsMargins(2, 0, 2, 0)
        lp.setSpacing(6)
        self._logo = QLabel()
        self._logo.setObjectName("sideLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setPixmap(_logo_pixmap(108, mode=self._theme))
        lp.addWidget(self._logo)
        brand = QLabel("Engine Tuner")
        brand.setObjectName("brandTitle")
        brand.setFont(app_font(15, QFont.Weight.Bold))
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lp.addWidget(brand)
        outer.addWidget(logo_plate)

        from ..icons import apply_icon

        self.open_btn = QPushButton()
        apply_icon(
            self.open_btn,
            "file_open",
            tip="Open enginespec…",
            kind="accent",
            size=22,
            square=40,
        )
        self.open_btn.clicked.connect(self.open_clicked.emit)
        outer.addWidget(self.open_btn)

        self.back_btn = QPushButton()
        apply_icon(
            self.back_btn,
            "arrow_back",
            tip="Return to Assets / CDP without writing (Save writes back)",
            kind="accent",
            size=22,
            square=40,
        )
        self.back_btn.clicked.connect(self.back_clicked.emit)
        self.back_btn.setVisible(False)
        outer.addWidget(self.back_btn)

        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.setAlignment(Qt.AlignmentFlag.AlignTop)

        info = QFrame()
        info.setObjectName("statsCard")
        il = QVBoxLayout(info)
        il.setContentsMargins(10, 8, 10, 10)
        il.setSpacing(6)
        info_title = QLabel("Enginespec")
        info_title.setStyleSheet("font-weight: 650;")
        il.addWidget(info_title)
        self._info_rows: dict[str, QLabel] = {}
        for key, caption in (
            ("file", "File"),
            ("name", "Name"),
            ("kuid", "KUID"),
            ("kind", "Kind"),
            ("notches", "Notches"),
            ("vmax", "Vmax"),
            ("mr", "MR"),
            ("bp", "BP"),
            ("points", "TE points"),
        ):
            row = QHBoxLayout()
            k = QLabel(caption)
            k.setObjectName("statsKey")
            v = QLabel("—")
            v.setObjectName("statsValue")
            v.setWordWrap(True)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._info_rows[key] = v
            row.addWidget(k)
            row.addWidget(v, 1)
            il.addLayout(row)
        bl.addWidget(info)

        # Clone card — moved out of the cramped graph toolbar
        clone = QFrame()
        clone.setObjectName("statsCard")
        cl = QVBoxLayout(clone)
        cl.setContentsMargins(10, 8, 10, 10)
        cl.setSpacing(8)
        clone_title = QLabel("Clone curves")
        clone_title.setStyleSheet("font-weight: 650;")
        cl.addWidget(clone_title)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("From"))
        self.clone_src = QSpinBox()
        self.clone_src.setRange(0, 8)
        self.clone_src.setValue(5)
        self.clone_src.setToolTip("Source notch to copy from")
        src_row.addWidget(self.clone_src, 1)
        cl.addLayout(src_row)
        tgt_lab = QLabel("Targets")
        tgt_lab.setObjectName("mutedTip")
        cl.addWidget(tgt_lab)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.clone_targets: dict[int, QCheckBox] = {}
        for i, n in enumerate(range(1, 9)):
            pick = _NotchPick(n)
            self.clone_targets[n] = pick.cb
            grid.addWidget(pick, i // 4, i % 4)
        cl.addLayout(grid)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        clone_btn = QPushButton("Clone")
        clone_btn.setToolTip("Copy From → checked targets")
        clone_btn.clicked.connect(self._emit_clone)
        higher_btn = QPushButton("→ N+1..8")
        higher_btn.setToolTip("Copy From → all higher notches")
        higher_btn.clicked.connect(self._emit_clone_higher)
        btn_row.addWidget(clone_btn, 1)
        btn_row.addWidget(higher_btn, 1)
        cl.addLayout(btn_row)
        bl.addWidget(clone)

        tip = QLabel("Use the bottom bar to switch Tuner · Simulation · Parameters.")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        bl.addWidget(tip)
        # setWidget before enable_smooth (→ prepare_frost_scroll) —
        # otherwise body keeps Base fill (black slab, sharp corners)
        scroll.setWidget(body)
        enable_smooth_scroll_area(scroll)
        outer.addWidget(scroll, 1)

        foot = QFrame()
        foot.setObjectName("separatorLine")
        outer.addWidget(foot)
        foot_lab = QLabel("File")
        foot_lab.setObjectName("mutedTip")
        outer.addWidget(foot_lab)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.save_btn = QPushButton()
        apply_icon(self.save_btn, "save", tip="Save", kind="accent", size=20, square=36)
        self.save_btn.clicked.connect(self.save_clicked.emit)
        self.save_as_btn = QPushButton()
        apply_icon(self.save_as_btn, "save_as", tip="Save As…", kind="icon", size=20, square=36)
        self.save_as_btn.clicked.connect(self.save_as_clicked.emit)
        self.undo_btn = QPushButton()
        apply_icon(self.undo_btn, "undo", tip="Undo", kind="icon", size=20, square=36)
        self.undo_btn.clicked.connect(self.undo_clicked.emit)
        self.redo_btn = QPushButton()
        apply_icon(self.redo_btn, "redo", tip="Redo", kind="icon", size=20, square=36)
        self.redo_btn.clicked.connect(self.redo_clicked.emit)
        for b in (self.save_btn, self.save_as_btn, self.undo_btn, self.redo_btn):
            file_row.addWidget(b)
        file_row.addStretch(1)
        outer.addLayout(file_row)

    def _emit_clone(self) -> None:
        src = int(self.clone_src.value())
        targets = [n for n, cb in self.clone_targets.items() if cb.isChecked() and n != src]
        self.clone_requested.emit(src, targets)

    def _emit_clone_higher(self) -> None:
        self.clone_higher_requested.emit(int(self.clone_src.value()))

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        self.set_frost(None, dark=self._theme != "light")
        self._logo.setPixmap(_logo_pixmap(108, mode=self._theme))

    def set_cdp_session(self, active: bool, *, label: str = "") -> None:
        """CDP handoff from Packages — show Back; Save tip points at CDP write-back."""
        from ..icons import apply_icon

        self.back_btn.setVisible(active)
        self.open_btn.setVisible(not active)
        if active:
            tip = f"Return to Packages ({label})" if label else "Return to Packages / CDP"
            self.back_btn.setToolTip(tip)
            apply_icon(
                self.save_btn,
                "save",
                tip="Write enginespec back into the CDP and return",
                kind="accent",
                size=20,
                square=36,
            )
            self.save_as_btn.setEnabled(False)
        else:
            apply_icon(self.save_btn, "save", tip="Save", kind="accent", size=20, square=36)
            self.save_as_btn.setEnabled(True)

    def refresh_info(self, cfg) -> None:
        path = cfg.source_path
        self._info_rows["file"].setText(Path(path).name if path else "— unsaved —")
        self._info_rows["file"].setToolTip(str(path or ""))
        self._info_rows["name"].setText(_hdr(cfg, "username"))
        self._info_rows["kuid"].setText(_hdr(cfg, "kuid"))
        self._info_rows["kind"].setText(_hdr(cfg, "kind", "enginespec"))
        notches = int(cfg.motor.get("throttle-notches", 0) or 0)
        self._info_rows["notches"].setText(str(notches) if notches else "—")
        vmax = cfg.motor.get("maxspeed")
        if vmax:
            self._info_rows["vmax"].setText(f"{float(vmax) * 3.6:.1f} km/h")
        else:
            self._info_rows["vmax"].setText("—")
        mr = cfg.pressure.get("mainreservoir")
        bp = cfg.pressure.get("brakepipe") or cfg.pressure.get("brakeinitial")
        if mr is not None:
            self._info_rows["mr"].setText(
                f"{to_bar(float(mr)):.2f} bar · {to_kpa(float(mr)):.0f} kPa"
            )
        else:
            self._info_rows["mr"].setText("—")
        if bp is not None:
            self._info_rows["bp"].setText(
                f"{to_bar(float(bp)):.2f} bar · {to_kpa(float(bp)):.0f} kPa"
            )
        else:
            self._info_rows["bp"].setText("—")
        total = sum(len(pts) for pts in cfg.throttle_power.values())
        filled = sum(1 for pts in cfg.throttle_power.values() if pts)
        self._info_rows["points"].setText(f"{total} pts · {filled} notches")
