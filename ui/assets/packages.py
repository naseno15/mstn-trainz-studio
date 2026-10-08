"""Packages page — Finder · preview; queue lives in Assets left sidebar."""
from __future__ import annotations

import mimetypes
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

_MESH_PREVIEW_EXTS = {".trainzmesh", ".fbx", ".im", ".pm"}

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...io.cdp import (
    asset_config_text,
    browse_cdp,
    classify_size,
    discard_cdp_bak,
    estimate_pack_size,
    extract_cdp,
    format_bytes,
    load_cdp,
    open_cdp,
    pack_asset_folders,
    read_file_bytes,
    remove_asset,
    remove_file,
    replace_asset_config,
    replace_file,
    safe_stage_token,
    save_cdp,
    stage_asset_for_mesh_preview,
)
from ...io.cdp_lzss import decode_asset_text
from ...io.chump import ChumpFile
from ...io.tzarc import extract_tzarc, list_tzarc
from ...lib.engine_tuner.config_io import looks_like_enginespec
from ..code_edit import (
    CodeEdit,
    apply_code_edit_theme,
    bump_code_font_pt,
    code_font_pt,
    syntax_for_filename,
)
from ..frost import FROST_CONTENT_MARGINS, FrostGlassFrame
from ..smooth_scroll import enable_smooth_table
from ..theme import app_font


class _CdpMeshStageWorker(QThread):
    """Stage mesh file only (no textures) off the UI thread."""

    ok = Signal(str)
    err = Signal(str)

    def __init__(
        self,
        chump,
        kuid: str,
        mesh_rel: str,
        dest: Path,
        parent=None,
        *,
        with_textures: bool = False,
        wipe: bool = True,
    ) -> None:
        super().__init__(parent)
        self._chump = chump
        self._kuid = kuid
        self._mesh_rel = mesh_rel
        self._dest = Path(dest)
        self._with_textures = with_textures
        self._wipe = wipe

    def run(self) -> None:
        try:
            import shutil

            if self.isInterruptionRequested():
                return
            if self._wipe and self._dest.is_dir():
                shutil.rmtree(self._dest, ignore_errors=True)
            path = stage_asset_for_mesh_preview(
                self._chump,
                self._kuid,
                self._dest,
                mesh_rel=self._mesh_rel,
                mesh_only=not self._with_textures,
            )
            if self.isInterruptionRequested():
                return
            self.ok.emit(str(path))
        except Exception as exc:
            self.err.emit(str(exc))


class _WarmGeoWorker(QThread):
    """Parse mesh for fast preview off the UI thread."""

    ok = Signal(object, str)  # scene, path
    err = Signal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self._path = Path(path)

    def run(self) -> None:
        try:
            from ...io.loaders import load_any

            if self.isInterruptionRequested():
                return
            scene = load_any(self._path, preview_fast=True)
            if self.isInterruptionRequested():
                return
            self.ok.emit(scene, str(self._path))
        except Exception as exc:
            self.err.emit(str(exc))


_ROLE_PATH = int(Qt.ItemDataRole.UserRole)
_ROLE_KIND = int(Qt.ItemDataRole.UserRole) + 1
_ROLE_KUID = int(Qt.ItemDataRole.UserRole) + 2
_ROLE_REL = int(Qt.ItemDataRole.UserRole) + 3
_ROLE_ENTRY = int(Qt.ItemDataRole.UserRole) + 4

# Natural two-line cell fits ~45px after polish; clipping was ::item pad / bad label height.
_FINDER_ROW_H = 48

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga", ".dds"}
_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aiff", ".aif"}
_TEXT_EXTS = {
    ".txt",
    ".gs",
    ".gse",
    ".cfg",
    ".ini",
    ".xml",
    ".json",
    ".md",
    ".csv",
    ".lm",
    ".py",
    ".lua",
    ".html",
    ".css",
    ".log",
}
_TEXT_NAMES = {"config.txt", "config.chump", "mesh.txt", "license.txt", "readme.txt"}


def _finder_badge_for(e: "FinderEntry") -> tuple[str, str]:
    """(letter, color) for Finder row badge — no emoji."""
    if e.kind == "dir":
        return "F", "#ff5a1f"
    if e.kind == "asset":
        return "A", "#3d9cf0"
    if e.is_nested_cdp or e.kind == "cdp-file":
        return "C", "#e6a817"
    name = e.name.rstrip("/").lower()
    if name.endswith(".fbx"):
        return "X", "#ff9f0a"
    if name.endswith(tuple(_IMAGE_EXTS)):
        return "I", "#30d158"
    if name.endswith(tuple(_AUDIO_EXTS)):
        return "S", "#64d2ff"
    if name in _TEXT_NAMES or name.endswith(tuple(_TEXT_EXTS)):
        return "T", "#ffd60a"
    return "·", "#8e8e93"


def _finder_label(text: str, *, object_name: str, point: int, weight: QFont.Weight) -> QLabel:
    """Single-line Finder label — height after QSS polish so g/y are not clipped."""
    lab = QLabel(text)
    lab.setObjectName(object_name)
    lab.setFont(app_font(point, weight))
    lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    lab.ensurePolished()
    fm = lab.fontMetrics()
    # Paint box must cover ascent+descent; QLabel default height() clips faces.
    lab.setFixedHeight(max(fm.height(), fm.ascent() + fm.descent()) + 2)
    return lab


class _FinderNameCell(QWidget):
    """Badge + title / subtitle for Finder rows (+ optional Edited mark)."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        badge: str,
        color: str,
        edited: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Opaque cell widgets eat the rounded selection pill (Win Highlight slab).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(0)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
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
        text.setSpacing(0)
        text.addWidget(
            _finder_label(
                title, object_name="pkgFinderTitle", point=12, weight=QFont.Weight.DemiBold
            )
        )
        if subtitle:
            text.addWidget(
                _finder_label(
                    subtitle,
                    object_name="pkgFinderSub",
                    point=10,
                    weight=QFont.Weight.Normal,
                )
            )
        lay.addLayout(text, 1)
        if edited:
            edit = QLabel("E")
            edit.setObjectName("pkgFinderEdited")
            edit.setFixedSize(22, 22)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.setToolTip("Edited — Save CDP… to write to disk")
            edit.setStyleSheet(
                "QLabel#pkgFinderEdited {"
                "background: #ff5a1f44; color: #ff5a1f; border-radius: 7px;"
                "font-weight: 800; font-size: 11px;}"
            )
            lay.addWidget(edit, 0, Qt.AlignmentFlag.AlignVCenter)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, _FINDER_ROW_H)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(72, _FINDER_ROW_H)


@dataclass
class QueueItem:
    path: Path
    kind: str  # folder | cdp


@dataclass
class FinderEntry:
    name: str
    kind: str  # dir | file | asset | cdp-file
    size: int = -1
    mtime: float = 0.0
    detail: str = ""  # secondary line (kuid / kind / path hint)
    # disk
    path: Path | None = None
    # cdp virtual — cwd = [kuid, *folder_parts]; rel = file path inside asset
    kuid: str = ""
    rel: str = ""
    folder_part: str = ""  # for virtual dir drill-in
    is_nested_cdp: bool = False


def _dir_size_disk(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _cdp_level_entries(
    *,
    kuid: str,
    files: list,
    folder_parts: list[str],
) -> list[FinderEntry]:
    """Immediate children under asset / folder_parts (folders first)."""
    folders: dict[str, int] = {}
    file_entries: list[FinderEntry] = []
    n = len(folder_parts)
    for fn in files:
        parts = Path(str(fn.rel_path).replace("\\", "/")).parts
        if n and parts[:n] != tuple(folder_parts):
            continue
        rest = parts[n:]
        if not rest:
            continue
        size = max(0, int(fn.size))
        if len(rest) > 1:
            folders[rest[0]] = folders.get(rest[0], 0) + size
            continue
        name = rest[0]
        file_entries.append(
            FinderEntry(
                name=name,
                kind="cdp-file" if getattr(fn, "is_cdp", False) else "file",
                size=size,
                kuid=kuid,
                rel=str(fn.rel_path).replace("\\", "/"),
                is_nested_cdp=bool(getattr(fn, "is_cdp", False)),
            )
        )
    out: list[FinderEntry] = [
        FinderEntry(
            name=f"{name}/",
            kind="dir",
            size=sz,
            kuid=kuid,
            folder_part=name,
        )
        for name, sz in sorted(folders.items(), key=lambda kv: kv[0].lower())
    ]
    out.extend(sorted(file_entries, key=lambda e: e.name.lower()))
    return out


def _load_preview_pixmap(data: bytes, name: str) -> QPixmap | None:
    """Decode image bytes → QPixmap (PNG/JPEG/BMP; TGA via Pillow if present)."""
    suf = Path(name).suffix.lower().lstrip(".")
    img = QImage()
    if suf in ("png", "jpg", "jpeg", "bmp", "gif", "webp"):
        ok = img.loadFromData(data, suf.upper() if suf != "jpg" else "JPG")
        if not ok:
            ok = img.loadFromData(data)
        if ok and not img.isNull():
            return QPixmap.fromImage(img)
    if suf == "tga":
        try:
            from io import BytesIO

            from PIL import Image  # type: ignore

            pil = Image.open(BytesIO(data))
            pil = pil.convert("RGBA")
            raw = pil.tobytes("raw", "RGBA")
            qimg = QImage(raw, pil.width, pil.height, QImage.Format.Format_RGBA8888).copy()
            return QPixmap.fromImage(qimg)
        except Exception:
            pass
    pix = QPixmap()
    if pix.loadFromData(data) and not pix.isNull():
        return pix
    return None


def _local_paths(urls: list) -> list[Path]:
    out: list[Path] = []
    for url in urls:
        if not url.isLocalFile():
            continue
        raw = url.toLocalFile()
        if raw:
            out.append(Path(raw))
    return out


def _filter_queue_paths(paths: list[Path]) -> list[Path]:
    """Folders, config.txt parents, or .cdp files."""
    kept: list[Path] = []
    for p in paths:
        if p.suffix.lower() == ".cdp":
            if p.exists() and not p.is_file():
                continue
            kept.append(p)
        elif p.is_dir():
            kept.append(p)
        elif p.name.lower() == "config.txt":
            kept.append(p.parent)
    return kept


def _file_kind_label(name: str) -> str:
    low = name.lower()
    suf = Path(name).suffix.lower()
    if low.endswith(".cdp") or suf == ".cdp":
        return "CDP package"
    if low == "config.txt":
        return "Trainz config"
    if suf in _IMAGE_EXTS:
        return f"Image ({suf[1:].upper()})" if suf else "Image"
    if suf in {".im", ".trainzmesh", ".fbx", ".pm"}:
        return f"Mesh ({suf[1:]})"
    if suf in _AUDIO_EXTS:
        return f"Audio ({suf[1:]})"
    if suf in _TEXT_EXTS or low in _TEXT_NAMES:
        return f"Text ({suf[1:] or 'txt'})"
    if suf:
        return suf[1:].upper()
    mime, _ = mimetypes.guess_type(name)
    return mime or "File"


def _is_text_name(name: str) -> bool:
    low = name.lower()
    if low in _TEXT_NAMES:
        return True
    suf = Path(name).suffix.lower()
    if suf in _TEXT_EXTS:
        return True
    if low.endswith(".texture.txt") or low.endswith(".lm.txt"):
        return True
    return False


def _is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in _IMAGE_EXTS


def _is_audio_name(name: str) -> bool:
    return Path(name).suffix.lower() in _AUDIO_EXTS


class _DropTable(QTableWidget):
    """Queue table — sole drop target for asset folders / CDP."""

    paths_dropped = Signal(object)

    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(columns), parent)
        self._drag_over = False
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setHorizontalHeaderLabels(columns)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        enable_smooth_table(self)

    def _ok(self, event: QDragEnterEvent | QDragMoveEvent) -> bool:
        if not event.mimeData().hasUrls():
            return False
        return bool(_filter_queue_paths(_local_paths(event.mimeData().urls())))

    def _set_drag_over(self, active: bool) -> None:
        if self._drag_over == active:
            return
        self._drag_over = active
        self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._ok(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._ok(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        paths = _filter_queue_paths(
            _local_paths(event.mimeData().urls() if event.mimeData().hasUrls() else [])
        )
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        if not self._drag_over:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#ff5a1f"))
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([6.0, 5.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.viewport().rect().adjusted(3, 3, -3, -3), 10, 10)


class PackagesPage(QWidget):
    """Finder column; Viewer docks full-height at AssetsStudioHost (Mesh Editor style)."""

    status = Signal(str)
    # kuid, config text, display label — open Engine Tuner CDP session
    enginespec_open = Signal(str, str, str)
    # staged mesh path — open in Mesh Studio (textures already beside file)
    mesh_open = Signal(str)
    # True = hide Finder / grow studio right dock
    viewer_expand_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "dark"
        self._queue: list[QueueItem] = []
        self._active_cdp: Path | None = None
        self._chump: ChumpFile | None = None
        self._chump_dirty = False
        # per-path edits in open CDP (Finder "E" mark) — cleared on Save CDP / Clear / open
        self._dirty_paths: set[str] = set()
        self._dirty_assets: set[str] = set()
        self._nested_stack: list[tuple[str, ChumpFile, Path | None]] = []
        self._tzarc_path: Path | None = None
        self._pkg_kuids: list[str] = []
        # Finder navigation
        self._finder_mode = "empty"  # empty | disk | cdp
        self._disk_root: Path | None = None
        self._disk_cwd: Path | None = None
        self._cdp_cwd: list[str] = []  # [] = assets root; [kuid] = inside asset
        self._finder_scan: str | None = None  # e.g. "fbx" = flat match across CDP
        self._preview_src: tuple[str, str, str] | None = None  # disk|cdp, key, name
        self._preview_bytes: bytes | None = None
        self._audio_tmp: Path | None = None
        self._clip_player = None  # lazy ClipPlayer
        self._mesh_preview = None  # lazy _PreviewSurface
        self._mesh_stage_root = Path(tempfile.gettempdir()) / f"tzs_pkg_mesh_{os.getpid()}"
        self._mesh_staged: set[str] = set()  # kuid tokens staged while clean
        self._mesh_staged_path: Path | None = None
        self._mesh_stage_worker: _CdpMeshStageWorker | None = None
        self._warm_worker: _WarmGeoWorker | None = None
        self._mesh_req = 0  # ignore stale async stage / GL loads
        self._warm_key: str | None = None
        self._warm_path: Path | None = None
        self._warm_scene = None
        self._show_when_warm_ready: str | None = None
        self._tex_stage_worker: _CdpMeshStageWorker | None = None
        self._open_mesh_studio_after_stage = False
        self._viewer_expanded = False
        self._pane_mode = "viewer"  # viewer | editor
        self._build()

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        dark = self._theme != "light"
        panel = getattr(self, "viewer_panel", None)
        if panel is not None:
            panel.set_dark(dark)
            apply_code_edit_theme(panel, self._theme)
        apply_code_edit_theme(self, self._theme)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main = QFrame()
        main.setObjectName("glassPanel")
        main.setMinimumWidth(0)  # allow collapse on Viewer expand
        self._main_panel = main
        ml = QVBoxLayout(main)
        ml.setContentsMargins(16, 16, 16, 16)
        ml.setSpacing(8)

        title = QLabel("Packages")
        title.setObjectName("welcomeTitle")
        title.setFont(app_font(16, QFont.Weight.Bold))
        ml.addWidget(title)

        tip = QLabel(
            "ซ้าย (sidebar): queue · กลาง: Finder (ดับเบิลคลิกเข้าโฟลเดอร์ · breadcrumb ย้อน · ค้นหา) · "
            "ขวา: preview"
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        ml.addWidget(tip)

        from ..icons import apply_icon

        # Queue rail — mounted into Assets left sidebar (not this panel).
        self.queue_rail = QWidget()
        ll = QVBoxLayout(self.queue_rail)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        left_lab = QLabel("Folders & CDP")
        left_lab.setObjectName("mutedTip")
        ll.addWidget(left_lab)
        self.queue_table = _DropTable(["Kind", "Name", "Size", "Info"])
        self.queue_table.setColumnWidth(0, 56)
        self.queue_table.setColumnWidth(1, 120)
        self.queue_table.setColumnWidth(2, 64)
        self.queue_table.paths_dropped.connect(self.add_queue_paths)
        self.queue_table.itemSelectionChanged.connect(self._on_queue_selected)
        ll.addWidget(self.queue_table, 1)
        self.size_lab = QLabel("Pack estimate: —")
        self.size_lab.setObjectName("mutedTip")
        self.size_lab.setWordWrap(True)
        ll.addWidget(self.size_lab)

        # ── Finder (full main column) ─────────────────────────
        right = QFrame()
        right.setObjectName("pkgFinderShell")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(8)

        head_row = QHBoxLayout()
        right_lab = QLabel("Finder")
        right_lab.setObjectName("pkgFinderHeading")
        right_lab.setFont(app_font(13, QFont.Weight.DemiBold))
        head_row.addWidget(right_lab)
        head_row.addStretch(1)
        self.finder_space = QLabel("")
        self.finder_space.setObjectName("pkgFinderMeta")
        head_row.addWidget(self.finder_space)
        rl.addLayout(head_row)

        crumb_host = QFrame()
        crumb_host.setObjectName("pkgFinderCrumbs")
        self._crumb_lay = QHBoxLayout(crumb_host)
        self._crumb_lay.setContentsMargins(8, 6, 8, 6)
        self._crumb_lay.setSpacing(4)
        self._crumb_lay.addStretch(1)
        rl.addWidget(crumb_host)
        self.finder_path = QLabel("—")
        self.finder_path.setVisible(False)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.btn_finder_up = QPushButton("←")
        self.btn_finder_up.setObjectName("pkgFinderBack")
        self.btn_finder_up.setFixedSize(34, 32)
        self.btn_finder_up.setToolTip("ขึ้นหนึ่งชั้น (Backspace)")
        self.btn_finder_up.clicked.connect(self._finder_up)
        self.btn_finder_up.setEnabled(False)
        search_row.addWidget(self.btn_finder_up)
        self.finder_filter = QLineEdit()
        self.finder_filter.setObjectName("pkgFinderSearch")
        self.finder_filter.setPlaceholderText("ค้นหาในรายการ…")
        self.finder_filter.setClearButtonEnabled(True)
        self.finder_filter.setFixedHeight(32)
        self.finder_filter.textChanged.connect(self._on_finder_filter)
        search_row.addWidget(self.finder_filter, 1)
        self.btn_find_fbx = QPushButton(".fbx")
        self.btn_find_fbx.setObjectName("pkgFinderScan")
        self.btn_find_fbx.setCheckable(True)
        self.btn_find_fbx.setFixedHeight(32)
        self.btn_find_fbx.setToolTip(
            "สแกนทั้ง CDP หาไฟล์ .fbx — เลือกหลายไฟล์แล้ว Delete ได้"
        )
        self.btn_find_fbx.clicked.connect(self._toggle_fbx_scan)
        search_row.addWidget(self.btn_find_fbx)
        rl.addLayout(search_row)

        self.finder_table = QTableWidget(0, 2)
        self.finder_table.setObjectName("pkgFinder")
        self.finder_table.setHorizontalHeaderLabels(["Name", "Size"])
        hdr = self.finder_table.horizontalHeader()
        hdr.setObjectName("pkgFinderHeader")
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Fixed)
        self.finder_table.setColumnWidth(1, 108)
        vh = self.finder_table.verticalHeader()
        vh.setVisible(False)
        vh.setDefaultSectionSize(_FINDER_ROW_H)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.finder_table.setShowGrid(False)
        self.finder_table.setWordWrap(False)
        self.finder_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.finder_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.finder_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.finder_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.finder_table.setToolTip(
            "ดับเบิลคลิกเข้าโฟลเดอร์ · คลิกไฟล์เพื่อดู · Shift/Ctrl เลือกหลายไฟล์แล้ว Delete"
        )
        enable_smooth_table(self.finder_table)
        # enable_smooth_scroll forces alternating on — Finder stays flat.
        self.finder_table.setAlternatingRowColors(False)
        hdr.setObjectName("pkgFinderHeader")
        self.finder_table.itemDoubleClicked.connect(self._on_finder_dbl)
        self.finder_table.itemSelectionChanged.connect(self._on_finder_selected)
        rl.addWidget(self.finder_table, 1)
        self._finder_all: list[FinderEntry] = []
        self._finder_nav_lock = False

        fbtn = QHBoxLayout()
        self.btn_open_folder = QPushButton()
        apply_icon(
            self.btn_open_folder,
            "folder_open",
            tip="Open folder…",
            kind="accent",
            size=22,
            square=40,
        )
        self.btn_open_folder.clicked.connect(self._open_folder_dialog)
        fbtn.addWidget(self.btn_open_folder)
        fbtn.addStretch(1)
        rl.addLayout(fbtn)
        ml.addWidget(right, 1)

        self.tz_lab = QLabel("")
        self.tz_lab.setObjectName("mutedTip")
        self.tz_lab.setWordWrap(True)
        self.tz_lab.setVisible(False)
        ml.addWidget(self.tz_lab)

        root.addWidget(main, 1)
        # Full-height frost dock — AssetsStudioHost mounts into _right_dock.
        self._build_viewer_panel()
        apply_code_edit_theme(self, self._theme)
        self._sync_editor_tab()

    def _build_viewer_panel(self) -> None:
        """Mesh Editor-style right frost plate (padding = FROST_CONTENT_MARGINS)."""
        from ..icons import apply_icon

        side = FrostGlassFrame(radius=14.0)
        side.setObjectName("editorDock")
        side.setMinimumWidth(0)
        side.setMaximumWidth(16777215)
        side.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        side.set_dark(True)
        self.viewer_panel = side
        sl = QVBoxLayout(side)
        # Same inset as Mesh Studio EditorWorkspace / left sidebar.
        sl.setContentsMargins(*FROST_CONTENT_MARGINS)
        sl.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(6)
        st = QLabel("Viewer")
        st.setObjectName("welcomeTitle")
        st.setFont(app_font(14, QFont.Weight.DemiBold))
        st.setWordWrap(True)
        self._side_title = st
        head.addWidget(st, 1)
        # Lazy — SideTabStrip lives in app.py (avoid circular import at load).
        from ..app import SideTabStrip

        self._pane_mode_tabs = SideTabStrip(("Viewer", "Editor"))
        self._pane_mode_tabs.setMaximumWidth(200)
        self._pane_mode_tabs.index_changed.connect(self._on_pane_mode)
        head.addWidget(self._pane_mode_tabs)
        self.btn_font_minus = QPushButton("A−")
        self.btn_font_minus.setFixedWidth(36)
        self.btn_font_minus.setToolTip("Smaller text (Ctrl+-)")
        self.btn_font_minus.clicked.connect(lambda: self._bump_font(-1))
        head.addWidget(self.btn_font_minus)
        self.font_lab = QLabel(f"{code_font_pt()} pt")
        self.font_lab.setObjectName("mutedTip")
        self.font_lab.setMinimumWidth(40)
        self.font_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.font_lab)
        self.btn_font_plus = QPushButton("A+")
        self.btn_font_plus.setFixedWidth(36)
        self.btn_font_plus.setToolTip("Larger text (Ctrl+=)")
        self.btn_font_plus.clicked.connect(lambda: self._bump_font(1))
        head.addWidget(self.btn_font_plus)
        self.btn_nested = QPushButton()
        apply_icon(
            self.btn_nested,
            "arrow_back",
            tip="Back to parent CDP",
            kind="icon",
            size=20,
            square=36,
        )
        self.btn_nested.setEnabled(False)
        self.btn_nested.clicked.connect(self._nested_back)
        head.addWidget(self.btn_nested)
        self.btn_expand = QPushButton()
        apply_icon(
            self.btn_expand,
            "fullscreen",
            tip="Expand viewer — hide Finder (queue stays in sidebar)",
            kind="icon",
            size=20,
            square=36,
        )
        self.btn_expand.clicked.connect(self._toggle_viewer_expand)
        head.addWidget(self.btn_expand)
        sl.addLayout(head)
        self.preview_lab = QLabel("Select a file in Finder")
        self.preview_lab.setObjectName("mutedTip")
        self.preview_lab.setWordWrap(True)
        sl.addWidget(self.preview_lab)

        self.preview_stack = QStackedWidget()
        self.preview_empty = QLabel("No preview")
        self.preview_empty.setObjectName("mutedTip")
        self.preview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_stack.addWidget(self.preview_empty)  # 0
        self.preview_image = QLabel()
        self.preview_image.setObjectName("pkgImagePreview")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(200)
        self.preview_image.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_image.setScaledContents(False)
        self.preview_stack.addWidget(self.preview_image)  # 1
        self.preview_edit = CodeEdit(syntax="plain")
        self.preview_edit.setPlaceholderText("Text preview / editor…")
        self.preview_stack.addWidget(self.preview_edit)  # 2
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("mutedTip")
        self.preview_meta.setWordWrap(True)
        self.preview_meta.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.preview_stack.addWidget(self.preview_meta)  # 3
        audio_host = QWidget()
        al = QVBoxLayout(audio_host)
        al.setContentsMargins(8, 8, 8, 8)
        al.setSpacing(10)
        self.audio_title = QLabel("Audio")
        self.audio_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_title.setFont(app_font(13, QFont.Weight.DemiBold))
        al.addWidget(self.audio_title)
        self.audio_meta = QLabel("")
        self.audio_meta.setObjectName("mutedTip")
        self.audio_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_meta.setWordWrap(True)
        al.addWidget(self.audio_meta)
        arow = QHBoxLayout()
        arow.addStretch(1)
        self.btn_audio_play = QPushButton("Play")
        self.btn_audio_play.clicked.connect(self._audio_play)
        arow.addWidget(self.btn_audio_play)
        self.btn_audio_stop = QPushButton("Stop")
        self.btn_audio_stop.clicked.connect(self._audio_stop)
        arow.addWidget(self.btn_audio_stop)
        arow.addStretch(1)
        al.addLayout(arow)
        al.addStretch(1)
        self.preview_stack.addWidget(audio_host)  # 4
        self._mesh_host = QWidget()
        self._mesh_host_lay = QVBoxLayout(self._mesh_host)
        self._mesh_host_lay.setContentsMargins(0, 0, 0, 0)
        self._mesh_host_lay.setSpacing(0)
        self._mesh_placeholder = QLabel("Mesh preview…")
        self._mesh_placeholder.setObjectName("mutedTip")
        self._mesh_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mesh_host_lay.addWidget(self._mesh_placeholder, 1)
        self.preview_stack.addWidget(self._mesh_host)  # 5
        sl.addWidget(self.preview_stack, 1)

        pbtn = QHBoxLayout()
        pbtn.setSpacing(6)
        self.btn_save_text = QPushButton()
        apply_icon(
            self.btn_save_text,
            "save",
            tip="Save text…",
            kind="accent",
            size=20,
            square=36,
        )
        self.btn_save_text.clicked.connect(self._save_preview_text)
        self.btn_save_text.setEnabled(False)
        pbtn.addWidget(self.btn_save_text)
        self.btn_engine_tuner = QPushButton("Open in Engine Tuner")
        self.btn_engine_tuner.setToolTip(
            "enginespec ที่รองรับ — จูนแล้ว Save จะเขียนกลับเข้า CDP นี้"
        )
        self.btn_engine_tuner.clicked.connect(self._open_in_engine_tuner)
        self.btn_engine_tuner.setVisible(False)
        pbtn.addWidget(self.btn_engine_tuner)
        self.btn_fast_preview = QPushButton("Fast preview")
        self.btn_fast_preview.setToolTip(
            "ดู mesh แบบ solid เร็วๆ (ไม่โหลด texture / ไม่โชว์จุด a.*)"
        )
        self.btn_fast_preview.clicked.connect(self._start_fast_mesh_preview)
        self.btn_fast_preview.setVisible(False)
        pbtn.addWidget(self.btn_fast_preview)
        self.btn_mesh_studio = QPushButton("Open in Mesh Studio")
        self.btn_mesh_studio.setToolTip(
            "เปิดใน Mesh Studio พร้อม texture จาก CDP"
        )
        self.btn_mesh_studio.clicked.connect(self._open_in_mesh_studio)
        self.btn_mesh_studio.setVisible(False)
        pbtn.addWidget(self.btn_mesh_studio)
        self.btn_repl = QPushButton("Replace…")
        self.btn_repl.clicked.connect(self._replace_selected)
        pbtn.addWidget(self.btn_repl)
        self.btn_del = QPushButton()
        apply_icon(
            self.btn_del,
            "delete",
            tip="Delete",
            kind="icon",
            size=20,
            square=36,
        )
        self.btn_del.clicked.connect(self._delete_selected)
        pbtn.addWidget(self.btn_del)
        self.btn_save_cdp = QPushButton()
        apply_icon(
            self.btn_save_cdp,
            "save",
            tip="Save CDP…",
            kind="accent",
            size=20,
            square=36,
        )
        self.btn_save_cdp.clicked.connect(self.save_active_cdp)
        pbtn.addWidget(self.btn_save_cdp)
        sl.addLayout(pbtn)
        self.btn_del_all_fbx = QPushButton("Delete all .fbx in CDP…")
        self.btn_del_all_fbx.setToolTip("สแกนแล้วลบไฟล์ .fbx ทั้งหมดใน CDP ที่เปิดอยู่")
        self.btn_del_all_fbx.clicked.connect(self._delete_all_fbx)
        sl.addWidget(self.btn_del_all_fbx)

    def _msg(self, text: str) -> None:
        self.status.emit(text)

    def _bump_font(self, delta: int) -> None:
        pt = bump_code_font_pt(delta)
        self.font_lab.setText(f"{pt} pt")
        self._msg(f"Editor font {pt} pt (all text / .gs viewers)")

    def _toggle_viewer_expand(self) -> None:
        """Hide Finder / grow studio right dock (AssetsStudioHost animates sizes)."""
        self.set_viewer_expanded(not self._viewer_expanded)

    def set_viewer_expanded(self, expanded: bool) -> None:
        from ..icons import apply_icon

        expanded = bool(expanded)
        if expanded == self._viewer_expanded:
            return
        self._viewer_expanded = expanded
        self._main_panel.setVisible(not expanded)
        if expanded:
            apply_icon(
                self.btn_expand,
                "fullscreen_exit",
                tip="Restore Finder",
                kind="icon",
                size=20,
                square=36,
            )
            self._msg("Viewer expanded — Restore to show Finder")
        else:
            apply_icon(
                self.btn_expand,
                "fullscreen",
                tip="Expand viewer — hide Finder (queue stays in sidebar)",
                kind="icon",
                size=20,
                square=36,
            )
            self._msg("Finder restored")
        self.viewer_expand_toggled.emit(expanded)

    def reset_viewer_expand(self) -> None:
        """Leave expand without animating — used when navigating away from Packages."""
        if not self._viewer_expanded:
            return
        from ..icons import apply_icon

        self._viewer_expanded = False
        self._main_panel.setVisible(True)
        apply_icon(
            self.btn_expand,
            "fullscreen",
            tip="Expand viewer — hide Finder (queue stays in sidebar)",
            kind="icon",
            size=20,
            square=36,
        )

    def _on_pane_mode(self, index: int) -> None:
        if int(index) == 1 and not self._preview_can_edit():
            self._pane_mode_tabs.set_index(0, animate=True, emit=False)
            self._pane_mode = "viewer"
            self._msg("Editor unavailable — this file is view-only")
            return
        self._pane_mode = "editor" if int(index) == 1 else "viewer"
        self._apply_pane_mode()

    def _sync_side_title(self) -> None:
        mode = "Editor" if self._pane_mode == "editor" else "Viewer"
        name = self._preview_src[2] if self._preview_src else None
        title = self._side_title
        if name:
            title.setText(f"{mode} — {name}")
        else:
            title.setText(mode)

    def _preview_is_text(self) -> bool:
        if self._preview_src is None:
            return False
        name = self._preview_src[2]
        if _is_text_name(name):
            return True
        data = self._preview_bytes
        return bool(data) and self._looks_text(data)

    def _preview_can_edit(self) -> bool:
        """True only for text-like assets the Editor can change."""
        return self._preview_is_text()

    def _sync_editor_tab(self) -> None:
        """Disable Editor tab for images / audio / mesh / empty selection."""
        can = self._preview_can_edit()
        tip = (
            "Edit text in place"
            if can
            else "View-only — open a text file to use Editor"
        )
        tabs = getattr(self, "_pane_mode_tabs", None)
        if tabs is None:
            return
        tabs.set_tab_enabled(1, can, tip=tip)
        if not can and self._pane_mode == "editor":
            self._pane_mode = "viewer"
            tabs.set_index(0, animate=True, emit=False)
        self._sync_side_title()

    def _apply_pane_mode(self) -> None:
        """Honor Viewer vs Editor toggle for the open file."""
        self._sync_editor_tab()
        self._sync_side_title()
        if self._preview_src is None:
            return
        name = self._preview_src[2]
        editing = self._pane_mode == "editor" and self._preview_can_edit()
        if self._preview_is_text():
            self.preview_edit.setReadOnly(not editing)
            self.preview_stack.setCurrentIndex(2)
            self.btn_save_text.setEnabled(editing)
            self._update_engine_tuner_btn()
            return
        # Non-text: preview only — Editor tab stays disabled.
        if _is_image_name(name) and self.preview_image.pixmap() is not None:
            self.preview_stack.setCurrentIndex(1)
        elif _is_audio_name(name):
            self.preview_stack.setCurrentIndex(4)
        elif self._is_mesh_name(name):
            self.preview_stack.setCurrentIndex(5)
        self.btn_save_text.setEnabled(False)

    # ── queue ────────────────────────────────────────────────

    def add_queue_paths(self, paths: list[Path]) -> None:
        first_cdp: Path | None = None
        for raw in paths:
            p = Path(raw)
            if p.is_file() and p.name.lower() == "config.txt":
                p = p.parent
            if p.suffix.lower() == ".cdp" and (not p.exists() or p.is_file()):
                kind = "cdp"
                if any(q.path == p for q in self._queue):
                    continue
                self._queue.append(QueueItem(p, kind))
                if first_cdp is None:
                    first_cdp = p
            elif p.is_dir():
                if any(q.path == p for q in self._queue):
                    continue
                self._queue.append(QueueItem(p, "folder"))
            else:
                continue
        self._refresh_queue()
        if first_cdp is not None:
            self.open_cdp_path(first_cdp)
        elif paths:
            # select last added folder in finder
            for q in reversed(self._queue):
                if q.kind == "folder":
                    self._open_disk(q.path)
                    break

    def add_pack_folders(self, paths: list[Path]) -> None:
        self.add_queue_paths(paths)

    def add_cdp_paths(self, paths: list[Path]) -> None:
        self.add_queue_paths(paths)

    def clear_queue(self) -> None:
        # drop temp *.cdp.bak left from an interrupted overwrite
        if self._active_cdp is not None:
            discard_cdp_bak(self._active_cdp)
        for q in self._queue:
            if q.kind == "cdp":
                discard_cdp_bak(q.path)
        self._queue.clear()
        self._chump = None
        self._active_cdp = None
        self._clear_cdp_edits()
        self._nested_stack.clear()
        self._refresh_queue()
        self._finder_mode = "empty"
        self.btn_finder_up.setEnabled(False)
        self.finder_space.setText("")
        self._set_crumbs([("—", None)])
        self._fill_finder([])
        self._clear_preview()
        self._msg("Queue cleared")

    def remove_selected_queue(self) -> None:
        rows = sorted({i.row() for i in self.queue_table.selectedIndexes()}, reverse=True)
        if not rows:
            self._msg("Select queue row(s) to remove")
            return
        for r in rows:
            if 0 <= r < len(self._queue):
                del self._queue[r]
        self._refresh_queue()
        self._msg("Removed from queue")

    def _refresh_queue(self) -> None:
        self.queue_table.blockSignals(True)
        self.queue_table.setRowCount(0)
        pack_folders = [q.path for q in self._queue if q.kind == "folder"]
        for q in self._queue:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            kind_s = "CDP" if q.kind == "cdp" else "Folder"
            self.queue_table.setItem(row, 0, QTableWidgetItem(kind_s))
            name_item = QTableWidgetItem(q.path.name)
            name_item.setData(_ROLE_PATH, str(q.path))
            name_item.setData(_ROLE_KIND, q.kind)
            self.queue_table.setItem(row, 1, name_item)
            size = q.path.stat().st_size if q.path.is_file() else (
                sum(f.stat().st_size for f in q.path.rglob("*") if f.is_file())
                if q.path.is_dir()
                else 0
            )
            self.queue_table.setItem(row, 2, QTableWidgetItem(format_bytes(size)))
            info = ""
            if q.kind == "cdp":
                try:
                    info = f"{len(open_cdp(q.path).assets)} assets · {classify_size(size).band}"
                except Exception:
                    info = "error"
            else:
                info = "config.txt" if (q.path / "config.txt").is_file() else "no config.txt"
            self.queue_table.setItem(row, 3, QTableWidgetItem(info))
        self.queue_table.blockSignals(False)
        if pack_folders:
            est = estimate_pack_size(pack_folders)
            v = classify_size(est)
            self.size_lab.setText(
                f"Pack estimate ({len(pack_folders)} folder): {format_bytes(est)} — {v.label}"
            )
        else:
            self.size_lab.setText("Pack estimate: — (folders with config.txt only)")

    def _on_queue_selected(self) -> None:
        rows = self.queue_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.queue_table.item(rows[0].row(), 1)
        if item is None:
            return
        path = Path(str(item.data(_ROLE_PATH) or ""))
        kind = str(item.data(_ROLE_KIND) or "")
        if kind == "cdp":
            self.open_cdp_path(path)
        elif kind == "folder" and path.is_dir():
            self._open_disk(path)

    def _pack_folders(self) -> list[Path]:
        return [q.path for q in self._queue if q.kind == "folder" and q.path.is_dir()]

    def _selected_cdp(self) -> Path | None:
        if self._active_cdp is not None:
            return self._active_cdp
        rows = self.queue_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.queue_table.item(rows[0].row(), 1)
        if item is None or str(item.data(_ROLE_KIND) or "") != "cdp":
            return None
        return Path(str(item.data(_ROLE_PATH) or ""))

    # ── Finder ───────────────────────────────────────────────

    def _open_folder_dialog(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open folder", str(Path.home()))
        if d:
            self.add_queue_paths([Path(d)])
            self._open_disk(Path(d))

    def _open_disk(self, root: Path) -> None:
        root = Path(root)
        if not root.is_dir():
            return
        self._finder_mode = "disk"
        self._disk_root = root
        self._disk_cwd = root
        self._cdp_cwd = []
        self._refresh_finder()

    def open_cdp_path(self, path: Path, *, push_stack: bool = False) -> None:
        path = Path(path)
        try:
            chump = load_cdp(path)
            idx = open_cdp(path)
        except Exception as exc:
            QMessageBox.warning(self, "CDP", str(exc))
            return
        if push_stack and self._chump is not None:
            label = self._active_cdp.name if self._active_cdp else "memory"
            self._nested_stack.append((label, self._chump, self._active_cdp))
            self.btn_nested.setEnabled(True)
        else:
            self._nested_stack.clear()
            self.btn_nested.setEnabled(False)
            if not any(q.path == path for q in self._queue):
                self._queue.append(QueueItem(path, "cdp"))
                self._refresh_queue()
        self._active_cdp = path
        self._chump = chump
        self._clear_cdp_edits()
        self._pkg_kuids = [a.kuid for a in idx.assets if a.kuid]
        self._tzarc_path = None
        self.tz_lab.setVisible(False)
        self._finder_mode = "cdp"
        self._cdp_cwd = []
        self._clear_finder_scan()
        self._invalidate_mesh_stage()
        self._refresh_finder()
        self._clear_preview()
        self._msg(f"CDP {path.name} — {len(idx.assets)} asset(s)")

    def open_cdp_bytes(self, data: bytes, label: str) -> None:
        try:
            chump = load_cdp(data)
        except Exception as exc:
            QMessageBox.warning(self, "Nested CDP", str(exc))
            return
        if self._chump is not None:
            prev = self._active_cdp.name if self._active_cdp else "memory"
            self._nested_stack.append((prev, self._chump, self._active_cdp))
            self.btn_nested.setEnabled(True)
        self._active_cdp = None
        self._chump = chump
        self._clear_cdp_edits()
        nodes = browse_cdp(chump)
        self._pkg_kuids = [n.kuid for n in nodes if n.kuid]
        self._finder_mode = "cdp"
        self._cdp_cwd = []
        self._clear_finder_scan()
        self._refresh_finder()
        self._msg(f"Opened nested CDP {label}")

    def _nested_back(self) -> None:
        if not self._nested_stack:
            return
        label, chump, path = self._nested_stack.pop()
        self._chump = chump
        self._active_cdp = path
        self._clear_cdp_edits()
        self.btn_nested.setEnabled(bool(self._nested_stack))
        self._pkg_kuids = [n.kuid for n in browse_cdp(chump) if n.kuid]
        self._finder_mode = "cdp"
        self._cdp_cwd = []
        self._refresh_finder()
        self._msg(f"Back to {label}")

    def _finder_up(self) -> None:
        if self._finder_scan:
            self._clear_finder_scan()
            self._refresh_finder()
            return
        if self._finder_mode == "disk" and self._disk_cwd and self._disk_root:
            if self._disk_cwd != self._disk_root:
                self._disk_cwd = self._disk_cwd.parent
                self._refresh_finder()
        elif self._finder_mode == "cdp":
            if self._cdp_cwd:
                self._cdp_cwd = self._cdp_cwd[:-1]
                self._refresh_finder()

    def _cdp_edit_key(self, kuid: str, rel: str) -> str:
        return f"{kuid}/{(rel or '').replace(chr(92), '/')}"

    def _mark_cdp_edited(self, kuid: str, rel: str = "") -> None:
        """Flag asset / file as edited until Save CDP… (Finder shows E)."""
        if not kuid:
            return
        self._chump_dirty = True
        self._dirty_assets.add(kuid)
        if rel:
            self._dirty_paths.add(self._cdp_edit_key(kuid, rel))

    def _clear_cdp_edits(self) -> None:
        self._chump_dirty = False
        self._dirty_paths.clear()
        self._dirty_assets.clear()

    def _is_finder_edited(self, e: FinderEntry) -> bool:
        if self._finder_mode != "cdp" or not e.kuid:
            return False
        if e.kind == "asset":
            return e.kuid in self._dirty_assets
        if e.kind == "dir" and e.folder_part:
            parts = [*self._cdp_cwd[1:], e.folder_part]
            prefix = self._cdp_edit_key(e.kuid, "/".join(parts))
            return any(p == prefix or p.startswith(prefix + "/") for p in self._dirty_paths)
        if e.rel:
            return self._cdp_edit_key(e.kuid, e.rel) in self._dirty_paths
        return e.kuid in self._dirty_assets

    def _clear_finder_scan(self) -> None:
        self._finder_scan = None
        if hasattr(self, "btn_find_fbx"):
            self.btn_find_fbx.blockSignals(True)
            self.btn_find_fbx.setChecked(False)
            self.btn_find_fbx.blockSignals(False)

    def _toggle_fbx_scan(self) -> None:
        if self._chump is None or self._finder_mode != "cdp":
            self.btn_find_fbx.setChecked(False)
            QMessageBox.information(
                self, ".fbx", "เปิด CDP ใน Finder ก่อน แล้วค่อยสแกนหา .fbx"
            )
            return
        if self.btn_find_fbx.isChecked():
            self._finder_scan = "fbx"
            self._cdp_cwd = []
        else:
            self._finder_scan = None
        self._refresh_finder()

    def _scan_cdp_by_suffix(self, suffix: str) -> list[FinderEntry]:
        """Flat list of files across all assets matching suffix (e.g. .fbx)."""
        if self._chump is None:
            return []
        needle = suffix.lower()
        if not needle.startswith("."):
            needle = f".{needle}"
        out: list[FinderEntry] = []
        for a in browse_cdp(self._chump):
            uname = (a.username or "").strip() or a.kuid or "asset"
            for fn in a.files:
                rel = str(fn.rel_path).replace("\\", "/")
                if not rel.lower().endswith(needle):
                    continue
                out.append(
                    FinderEntry(
                        name=Path(rel).name,
                        kind="file",
                        size=max(0, int(fn.size)),
                        kuid=a.kuid,
                        rel=rel,
                        detail=f"{uname} · {rel}",
                    )
                )
        out.sort(key=lambda e: (e.kuid.lower(), e.rel.lower()))
        return out

    def _clear_crumbs(self) -> None:
        while self._crumb_lay.count():
            item = self._crumb_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _set_crumbs(self, parts: list[tuple[str, object | None]]) -> None:
        """parts: (label, depth|None). None = current (plain label). int = jump depth."""
        self._clear_crumbs()
        for i, (label, depth) in enumerate(parts):
            if i:
                sep = QLabel("›")
                sep.setObjectName("pkgCrumbSep")
                self._crumb_lay.addWidget(sep)
            short = label if len(label) <= 28 else label[:26] + "…"
            if depth is None:
                cur = QLabel(short)
                cur.setObjectName("pkgCrumbCurrent")
                cur.setToolTip(label)
                self._crumb_lay.addWidget(cur)
            else:
                btn = QPushButton(short)
                btn.setObjectName("pkgCrumbBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(f"ไปที่ {label}")
                d = int(depth)
                btn.clicked.connect(lambda _=False, depth=d: self._crumb_jump(depth))
                self._crumb_lay.addWidget(btn)
        self._crumb_lay.addStretch(1)

    def _crumb_jump(self, depth: int) -> None:
        self._clear_finder_scan()
        if self._finder_mode == "disk" and self._disk_root is not None:
            # depth 0 = root; 1.. = root + n parts under root
            parts = []
            cwd = self._disk_cwd or self._disk_root
            try:
                rel = cwd.relative_to(self._disk_root)
                parts = list(rel.parts) if str(rel) != "." else []
            except ValueError:
                parts = []
            if depth <= 0:
                self._disk_cwd = self._disk_root
            else:
                self._disk_cwd = self._disk_root.joinpath(*parts[:depth])
            self._refresh_finder()
            return
        if self._finder_mode == "cdp":
            # 0 = assets root; 1 = asset; 2+ = folders under asset
            if depth <= 0:
                self._cdp_cwd = []
            else:
                self._cdp_cwd = self._cdp_cwd[:depth]
            self._refresh_finder()

    def _on_finder_filter(self, *_args) -> None:  # noqa: ANN002
        self._fill_finder(self._finder_all, keep_filter=True)

    def _refresh_finder(self) -> None:
        if hasattr(self, "finder_filter"):
            self.finder_filter.blockSignals(True)
            self.finder_filter.clear()
            self.finder_filter.blockSignals(False)

        if self._finder_mode == "disk":
            cwd = self._disk_cwd or self._disk_root
            if cwd is None:
                self._set_crumbs([("—", None)])
                self.btn_finder_up.setEnabled(False)
                self._fill_finder([])
                return
            folder_bytes = _dir_size_disk(cwd)
            self.finder_space.setText(f"Folder · {format_bytes(folder_bytes)}")
            # crumbs under disk root
            crumbs: list[tuple[str, object | None]] = []
            if self._disk_root is not None:
                try:
                    rel = cwd.relative_to(self._disk_root)
                    under = list(rel.parts) if str(rel) != "." else []
                except ValueError:
                    under = []
                can_up = bool(under)
                self.btn_finder_up.setEnabled(can_up)
                crumbs.append(
                    (self._disk_root.name or str(self._disk_root), 0 if under else None)
                )
                for i, part in enumerate(under):
                    is_last = i == len(under) - 1
                    crumbs.append((part, None if is_last else i + 1))
            else:
                self.btn_finder_up.setEnabled(False)
                crumbs.append((str(cwd), None))
            self._set_crumbs(crumbs)
            entries: list[FinderEntry] = []
            try:
                children = sorted(cwd.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError as exc:
                self._msg(str(exc))
                children = []
            for p in children:
                if p.name.startswith("."):
                    continue
                st = p.stat()
                if p.is_dir():
                    entries.append(
                        FinderEntry(
                            name=f"{p.name}/",
                            kind="dir",
                            size=_dir_size_disk(p),
                            mtime=st.st_mtime,
                            path=p,
                            detail="Folder",
                        )
                    )
                else:
                    entries.append(
                        FinderEntry(
                            name=p.name,
                            kind="file",
                            size=st.st_size,
                            mtime=st.st_mtime,
                            path=p,
                            detail=_file_kind_label(p.name),
                        )
                    )
            self._fill_finder(entries)
            return

        if self._finder_mode == "cdp" and self._chump is not None:
            assets = browse_cdp(self._chump)
            label = self._active_cdp.name if self._active_cdp else "CDP"
            if self._finder_scan == "fbx":
                entries = self._scan_cdp_by_suffix(".fbx")
                total = sum(max(0, e.size) for e in entries)
                self.finder_space.setText(
                    f"{len(entries)} × .fbx · {format_bytes(total)}"
                )
                self.btn_finder_up.setEnabled(True)
                self._set_crumbs([(label, 0), ("*.fbx", None)])
                if hasattr(self, "btn_find_fbx"):
                    self.btn_find_fbx.blockSignals(True)
                    self.btn_find_fbx.setChecked(True)
                    self.btn_find_fbx.blockSignals(False)
                self._fill_finder(entries)
                if not entries:
                    self.preview_lab.setText("ไม่พบไฟล์ .fbx ใน CDP นี้")
                    self.preview_stack.setCurrentIndex(0)
                else:
                    self.preview_lab.setText(
                        f"พบ {len(entries)} ไฟล์ .fbx — เลือกแล้วกด Delete หรือ Delete all .fbx"
                    )
                return
            if not self._cdp_cwd:
                self.btn_finder_up.setEnabled(False)
                total = sum(sum(max(0, f.size) for f in a.files) for a in assets)
                self.finder_space.setText(f"{len(assets)} asset(s) · {format_bytes(total)}")
                self._set_crumbs([(label, None)])
                entries = []
                for a in assets:
                    uname = (a.username or "").strip() or "Untitled"
                    kind = (a.kind or "").strip()
                    detail = f"{kind} · {a.kuid}" if kind else (a.kuid or "Asset")
                    entries.append(
                        FinderEntry(
                            name=uname,
                            kind="asset",
                            size=sum(max(0, f.size) for f in a.files),
                            kuid=a.kuid,
                            detail=detail,
                        )
                    )
                self._fill_finder(entries)
                return

            kuid = self._cdp_cwd[0]
            folder_parts = self._cdp_cwd[1:]
            asset = next((a for a in assets if a.kuid == kuid), None)
            uname = (asset.username if asset else "") or kuid
            self.btn_finder_up.setEnabled(True)
            crumbs: list[tuple[str, object | None]] = [(label, 0)]
            if not folder_parts:
                crumbs.append((uname, None))
            else:
                crumbs.append((uname, 1))
                for i, part in enumerate(folder_parts):
                    is_last = i == len(folder_parts) - 1
                    crumbs.append((part, None if is_last else i + 2))
            self._set_crumbs(crumbs)
            entries: list[FinderEntry] = []
            if asset is not None:
                if not folder_parts:
                    try:
                        cfg = asset_config_text(self._chump, kuid)
                        cfg_size = len(cfg.encode("utf-8"))
                    except Exception:
                        cfg_size = 0
                    entries.append(
                        FinderEntry(
                            name="config.txt",
                            kind="file",
                            size=cfg_size,
                            kuid=kuid,
                            rel="__config__",
                            detail="Config",
                        )
                    )
                level = _cdp_level_entries(
                    kuid=kuid, files=asset.files, folder_parts=folder_parts
                )
                for e in level:
                    if e.kind == "dir":
                        e.detail = "Folder"
                    elif e.is_nested_cdp or e.kind == "cdp-file":
                        e.detail = "CDP package"
                    else:
                        e.detail = _file_kind_label(e.name.rstrip("/"))
                entries.extend(level)
                here = sum(max(0, e.size) for e in entries)
                self.finder_space.setText(f"This folder · {format_bytes(here)}")
            else:
                self.finder_space.setText("")
            self._fill_finder(entries)
            return

        self._set_crumbs([("—", None)])
        self.finder_space.setText("")
        self.btn_finder_up.setEnabled(False)
        self._fill_finder([])

    def _fill_finder(
        self, entries: list[FinderEntry], *, keep_filter: bool = False
    ) -> None:
        if not keep_filter:
            self._finder_all = list(entries)
        needle = ""
        if hasattr(self, "finder_filter"):
            needle = self.finder_filter.text().strip().lower()
        shown = self._finder_all
        if needle:
            shown = [
                e
                for e in self._finder_all
                if needle in e.name.lower()
                or needle in (e.detail or "").lower()
                or needle in (e.kuid or "").lower()
                or needle in (e.rel or "").lower()
            ]
        self._finder_nav_lock = True
        self.finder_table.blockSignals(True)
        self.finder_table.setRowCount(0)
        for e in shown:
            row = self.finder_table.rowCount()
            self.finder_table.insertRow(row)
            self.finder_table.setRowHeight(row, _FINDER_ROW_H)
            title = e.name.rstrip("/")
            if e.detail:
                sub = e.detail
            elif e.kind == "dir":
                sub = "Folder"
            elif e.kind == "asset":
                sub = e.kuid or "Asset"
            elif e.is_nested_cdp or e.kind == "cdp-file":
                sub = "CDP package"
            else:
                sub = _file_kind_label(title)
            # invisible item carries entry data for selection / dbl-click
            name_item = QTableWidgetItem("")
            name_item.setData(_ROLE_ENTRY, e)
            edited = self._is_finder_edited(e)
            tip = f"{title}\n{sub}" if sub else title
            if e.kuid and e.kuid not in tip:
                tip = f"{tip}\n{e.kuid}"
            if edited:
                tip = f"{tip}\nEdited — Save CDP… to write to disk"
            if e.kind in ("dir", "asset") or e.is_nested_cdp:
                tip = f"{tip}\nดับเบิลคลิกเพื่อเปิด"
            name_item.setToolTip(tip)
            self.finder_table.setItem(row, 0, name_item)
            letter, color = _finder_badge_for(e)
            cell = _FinderNameCell(
                title, sub, badge=letter, color=color, edited=edited
            )
            cell.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.finder_table.setCellWidget(row, 0, cell)
            if e.kind in ("dir", "asset"):
                size_s = format_bytes(max(0, e.size)) if e.size >= 0 else "—"
            else:
                size_s = "—" if e.size < 0 else format_bytes(e.size)
            size_item = QTableWidgetItem(size_s)
            size_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            size_item.setForeground(QColor("#98989d"))
            size_item.setFont(app_font(11, QFont.Weight.Medium))
            self.finder_table.setItem(row, 1, size_item)
        self.finder_table.blockSignals(False)
        self._finder_nav_lock = False

    def _current_finder_entry(self) -> FinderEntry | None:
        entries = self._selected_finder_entries()
        return entries[0] if entries else None

    def _selected_finder_entries(self) -> list[FinderEntry]:
        rows = self.finder_table.selectionModel().selectedRows()
        out: list[FinderEntry] = []
        for idx in rows:
            item = self.finder_table.item(idx.row(), 0)
            if item is None:
                continue
            e = item.data(_ROLE_ENTRY)
            if isinstance(e, FinderEntry):
                out.append(e)
        return out

    def _entry_from_item(self, item: QTableWidgetItem | None) -> FinderEntry | None:
        if item is None:
            return None
        e = item.data(_ROLE_ENTRY) if item.column() == 0 else None
        if e is None:
            name_item = self.finder_table.item(item.row(), 0)
            e = name_item.data(_ROLE_ENTRY) if name_item else None
        return e if isinstance(e, FinderEntry) else None

    def _enter_finder_entry(self, e: FinderEntry) -> bool:
        """Open folder / asset / nested CDP. Returns True if navigated."""
        if self._finder_scan and e.kind in ("dir", "asset"):
            self._clear_finder_scan()
        if e.kind == "dir":
            if e.path is not None:
                self._disk_cwd = e.path
            elif e.folder_part:
                if self._cdp_cwd:
                    self._cdp_cwd = [*self._cdp_cwd, e.folder_part]
                elif e.kuid:
                    self._cdp_cwd = [e.kuid, e.folder_part]
            self._refresh_finder()
            return True
        if e.kind == "asset" and e.kuid:
            self._cdp_cwd = [e.kuid]
            self._refresh_finder()
            self._update_engine_tuner_btn()
            return True
        if e.is_nested_cdp and self._chump is not None:
            try:
                data = read_file_bytes(self._chump, e.kuid, e.rel)
            except Exception as exc:
                QMessageBox.warning(self, "Nested CDP", str(exc))
                return True
            self.open_cdp_bytes(data, Path(e.rel).name)
            return True
        return False

    def _on_finder_selected(self, *_) -> None:  # noqa: ANN002
        if self._finder_nav_lock:
            return
        e = self._current_finder_entry()
        if e is None:
            return
        if e.kind in ("dir", "asset") or e.is_nested_cdp:
            self._audio_stop()
            self._clear_preview()
            label = e.name.rstrip("/")
            size_s = format_bytes(max(0, e.size)) if e.size >= 0 else "—"
            kind = (
                "CDP"
                if e.is_nested_cdp
                else "Asset"
                if e.kind == "asset"
                else "Folder"
            )
            self.preview_lab.setText(
                f"{label} · {kind} · {size_s} · ดับเบิลคลิกเพื่อเปิด"
            )
            return
        self._preview_entry(e)

    def _on_finder_dbl(self, item: QTableWidgetItem) -> None:
        e = self._entry_from_item(item)
        if e is None:
            return
        if self._enter_finder_entry(e):
            return
        name = e.path.name if e.path is not None else Path(e.rel or e.name).name
        if self._is_mesh_name(name):
            self._start_fast_mesh_preview()
            return
        self._preview_entry(e)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Back) and self.btn_finder_up.isEnabled():
            self._finder_up()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            e = self._current_finder_entry()
            if e is not None:
                if not self._enter_finder_entry(e):
                    self._preview_entry(e)
                event.accept()
                return
        super().keyPressEvent(event)

    # ── preview / editor ─────────────────────────────────────

    def _clear_preview(self) -> None:
        self._audio_stop()
        self._cancel_mesh_stage_worker()
        self._cancel_warm_worker()
        self._mesh_req += 1
        self._show_when_warm_ready = None
        self._warm_key = None
        self._warm_path = None
        self._warm_scene = None
        self._preview_src = None
        self._preview_bytes = None
        self._mesh_staged_path = None
        self.preview_stack.setCurrentIndex(0)
        self.preview_edit.setPlainText("")
        self.preview_image.clear()
        self.preview_meta.setText("")
        self.btn_save_text.setEnabled(False)
        self.btn_engine_tuner.setVisible(False)
        self.btn_fast_preview.setVisible(False)
        self.btn_mesh_studio.setVisible(False)
        self.preview_edit.setReadOnly(True)
        self.preview_lab.setText("Select a file in Finder")
        self._sync_editor_tab()

    def _invalidate_mesh_stage(self) -> None:
        self._mesh_staged.clear()
        self._mesh_staged_path = None

    def _cancel_mesh_stage_worker(self) -> None:
        worker = self._mesh_stage_worker
        self._mesh_stage_worker = None
        if worker is None:
            return
        for sig in (worker.ok, worker.err):
            try:
                sig.disconnect()
            except Exception:
                pass
        if worker.isRunning():
            worker.requestInterruption()
            # ponytail: don't wait() on UI thread — old worker finishes and is ignored

    def _cancel_warm_worker(self) -> None:
        worker = self._warm_worker
        self._warm_worker = None
        if worker is None:
            return
        for sig in (worker.ok, worker.err):
            try:
                sig.disconnect()
            except Exception:
                pass
        if worker.isRunning():
            worker.requestInterruption()

    def _is_mesh_name(self, name: str) -> bool:
        return Path(name).suffix.lower() in _MESH_PREVIEW_EXTS

    def _mesh_entry_key(self, e: FinderEntry) -> str:
        if e.path is not None:
            return f"disk:{e.path.resolve()}"
        return f"cdp:{e.kuid}/{e.rel.replace(chr(92), '/')}"

    def _mesh_entry_from_selection(self) -> FinderEntry | None:
        e = self._current_finder_entry()
        if e is None:
            return None
        name = e.path.name if e.path is not None else Path(e.rel or e.name).name
        if not self._is_mesh_name(name):
            return None
        return e

    def warm_fast_preview_infra(self) -> None:
        """Precache Finder solid-preview GL + loaders with Assets Tools boot warm.

        ponytail: first mesh click then only stages/parses — no cold MeshView import.
        """
        try:
            from ...io.loaders import load_any  # noqa: F401
        except Exception:
            pass
        self._ensure_fast_preview_gl_host()
        if self._mesh_preview is not None:
            self._mesh_preview.set_active(False)

    def _show_mesh_pick_card(self, e: FinderEntry) -> None:
        """Instant card + warm (stage+parse); opens solid preview when ready."""
        name = e.path.name if e.path is not None else Path(e.rel).name
        size = e.size if e.size >= 0 else 0
        if e.path is not None and e.path.is_file():
            size = e.path.stat().st_size
            self._preview_src = ("disk", str(e.path), name)
        else:
            self._preview_src = ("cdp", f"{e.kuid}/{e.rel}", name)
        self._sync_editor_tab()
        suf = Path(name).suffix.lower()
        key = self._mesh_entry_key(e)
        warm_ready = (
            self._warm_key == key
            and self._warm_scene is not None
            and self._warm_path is not None
            and self._warm_path.is_file()
        )
        im_note = (
            "\n\n.im ยังไม่มี geometry ใน fast preview — ใช้ Open in Mesh Studio"
            if suf == ".im"
            else ""
        )
        if warm_ready:
            status = "warm ready"
        elif suf == ".im":
            status = "ใช้ Open in Mesh Studio"
        else:
            status = "warming fast preview…"
        self.preview_lab.setText(f"{name} · {format_bytes(size)} · {status}")
        self.preview_meta.setText(
            f"{name}\n{_file_kind_label(name)}\n{format_bytes(size)}\n\n"
            f"{status}\n"
            f"Fast preview = solid mesh เท่านั้น (ไม่ texture / ไม่จุด a.*)"
            f"{im_note}"
        )
        self.preview_stack.setCurrentIndex(3)
        self.btn_fast_preview.setVisible(suf != ".im")
        self.btn_mesh_studio.setVisible(True)
        self.btn_engine_tuner.setVisible(False)
        self.btn_save_text.setEnabled(False)
        if warm_ready:
            self._show_warm_preview(self._mesh_req, self._warm_path, self._warm_scene)
            return
        if suf != ".im":
            self._start_warm_fast_preview(e)

    def _start_warm_fast_preview(self, e: FinderEntry) -> None:
        """Background: stage mesh-only + parse solid scene; GL host warms in parallel."""
        key = self._mesh_entry_key(e)
        if (
            self._warm_key == key
            and self._warm_scene is not None
            and self._warm_path is not None
            and self._warm_path.is_file()
        ):
            return
        if self._warm_key == key and (
            (self._mesh_stage_worker is not None and self._mesh_stage_worker.isRunning())
            or (self._warm_worker is not None and self._warm_worker.isRunning())
        ):
            return

        self._cancel_mesh_stage_worker()
        self._cancel_warm_worker()
        self._warm_key = key
        self._warm_scene = None
        self._warm_path = None
        self._mesh_req += 1
        req = self._mesh_req
        # GL construct overlaps stage/parse — apply_scene is then hitch-free
        QTimer.singleShot(0, self._ensure_fast_preview_gl_host)

        def after_path(path: Path, r: int = req, k: str = key) -> None:
            if r != self._mesh_req or self._warm_key != k:
                return
            self._mesh_staged_path = path
            self._warm_path = path
            self.preview_lab.setText(f"{path.name} · parsing warm…")
            self._start_warm_geo(path, r, k)

        if e.path is not None and e.path.is_file():
            after_path(e.path)
            return
        if self._chump is None or not e.kuid or not e.rel:
            return
        cached = self._cached_mesh_stage(e.kuid, e.rel)
        if cached is not None:
            after_path(cached)
            return
        rel = e.rel.replace("\\", "/")
        token = safe_stage_token(e.kuid)
        dest = self._mesh_stage_root / token
        worker = _CdpMeshStageWorker(
            self._chump,
            e.kuid,
            rel,
            dest,
            parent=self,
            with_textures=False,
            wipe=True,
        )
        self._mesh_stage_worker = worker

        def on_ok(path_s: str, r: int = req, t: str = token, k: str = key) -> None:
            if r != self._mesh_req or self._warm_key != k:
                return
            self._mesh_staged.add(t)
            self._mesh_stage_worker = None
            after_path(Path(path_s), r, k)

        def on_err(msg: str, r: int = req, k: str = key) -> None:
            if r != self._mesh_req or self._warm_key != k:
                return
            self._mesh_stage_worker = None
            self.preview_lab.setText(f"Warm failed: {msg}")

        worker.ok.connect(on_ok)
        worker.err.connect(on_err)
        worker.start()

    def _start_warm_geo(self, path: Path, req: int, key: str) -> None:
        self._cancel_warm_worker()
        worker = _WarmGeoWorker(path, parent=self)
        self._warm_worker = worker

        def on_ok(scene, path_s: str, r: int = req, k: str = key) -> None:
            if r != self._mesh_req or self._warm_key != k:
                return
            self._warm_worker = None
            self._warm_scene = scene
            self._warm_path = Path(path_s)
            name = self._warm_path.name
            self.preview_lab.setText(f"{name} · warm ready")
            self.preview_meta.setText(
                f"{name}\n{_file_kind_label(name)}\n"
                f"{scene.vertex_count:,}v · {scene.face_count:,}f\n\n"
                f"warm ready (solid, ไม่ texture / ไม่จุด)"
            )
            self._show_when_warm_ready = None
            # still on this mesh → open solid preview immediately
            cur = self._mesh_entry_from_selection()
            if cur is not None and self._mesh_entry_key(cur) == k:
                self._show_warm_preview(r, self._warm_path, scene)

        def on_err(msg: str, r: int = req, k: str = key) -> None:
            if r != self._mesh_req or self._warm_key != k:
                return
            self._warm_worker = None
            self.preview_lab.setText(f"Warm parse failed: {msg}")

        worker.ok.connect(on_ok)
        worker.err.connect(on_err)
        worker.start()

    def _ensure_fast_preview_gl_host(self) -> None:
        if self._mesh_preview is not None:
            return
        try:
            from ..mesh_preview import _PreviewSurface
        except Exception:
            return
        self._mesh_placeholder.hide()
        self._mesh_preview = _PreviewSurface(None, self._mesh_host, preview_fast=True)
        self._mesh_preview.set_active(False)
        self._mesh_host_lay.addWidget(self._mesh_preview, 1)

    def _drop_mesh_warm(self) -> None:
        """Invalidate in-flight Finder mesh warm (non-mesh preview selected)."""
        self._mesh_req += 1
        self._show_when_warm_ready = None
        self._cancel_warm_worker()
        self._cancel_mesh_stage_worker()
        self._warm_key = None
        self._warm_path = None
        self._warm_scene = None
        if self._mesh_preview is not None:
            self._mesh_preview.set_active(False)

    def _start_fast_mesh_preview(self) -> None:
        e = self._mesh_entry_from_selection()
        if e is None:
            QMessageBox.information(
                self, "Fast preview", "เลือกไฟล์ .trainzmesh / .fbx ก่อน"
            )
            return
        name = e.path.name if e.path is not None else Path(e.rel).name
        if Path(name).suffix.lower() == ".im":
            QMessageBox.information(
                self,
                "Fast preview",
                ".im ยังไม่มี mesh geometry ใน preview — ใช้ Open in Mesh Studio",
            )
            return
        key = self._mesh_entry_key(e)
        # use warm scene if ready
        if (
            self._warm_key == key
            and self._warm_scene is not None
            and self._warm_path is not None
            and self._warm_path.is_file()
        ):
            self._mesh_req += 1
            self._show_warm_preview(self._mesh_req, self._warm_path, self._warm_scene)
            return
        # warm still running — show waiting GL page; finish will apply scene
        if self._warm_key == key and (
            (self._warm_worker is not None and self._warm_worker.isRunning())
            or (self._mesh_stage_worker is not None and self._mesh_stage_worker.isRunning())
        ):
            self.preview_stack.setCurrentIndex(5)
            self._mesh_placeholder.setText(f"Waiting warm · {name}…")
            self._mesh_placeholder.show()
            self.preview_lab.setText(f"{name} · waiting warm…")
            self._open_mesh_studio_after_stage = False
            # when warm completes, auto-show if still selected
            self._show_when_warm_ready = key
            return
        self._show_when_warm_ready = key
        self._start_warm_fast_preview(e)
        self.preview_stack.setCurrentIndex(5)
        self._mesh_placeholder.setText(f"Warming {name}…")
        self._mesh_placeholder.show()

    def _cached_mesh_stage(self, kuid: str, mesh_rel: str) -> Path | None:
        rel = mesh_rel.replace("\\", "/")
        token = safe_stage_token(kuid)
        mesh_path = self._mesh_stage_root / token / rel
        if (
            not self._chump_dirty
            and token in self._mesh_staged
            and mesh_path.is_file()
        ):
            return mesh_path
        return None

    def _show_warm_preview(self, req: int, path: Path, scene) -> None:
        del req  # warm apply uses current selection; req already gated by caller
        self._mesh_staged_path = path
        self.btn_mesh_studio.setVisible(True)
        self.btn_fast_preview.setVisible(True)
        self.preview_lab.setText(
            f"{path.name} · {format_bytes(path.stat().st_size)} · solid (warm)"
        )
        self._ensure_fast_preview_gl_host()
        if self._mesh_preview is None:
            self.preview_stack.setCurrentIndex(3)
            self.preview_meta.setText("Mesh preview unavailable")
            return
        self._mesh_placeholder.hide()
        self._mesh_preview.set_active(True)
        self._mesh_preview.apply_scene(scene, path, preview_fast=True)
        self.preview_stack.setCurrentIndex(5)

    def _release_mesh_preview_for_studio(self) -> None:
        """Stop Packages GL + workers — dual MeshView timers cause progressive freeze."""
        self._show_when_warm_ready = None
        self._cancel_warm_worker()
        self._cancel_mesh_stage_worker()
        tex = self._tex_stage_worker
        self._tex_stage_worker = None
        if tex is not None:
            for sig in (tex.ok, tex.err):
                try:
                    sig.disconnect()
                except Exception:
                    pass
            if tex.isRunning():
                tex.requestInterruption()
        if self._mesh_preview is not None:
            self._mesh_preview.set_active(False)
        self.preview_stack.setCurrentIndex(0)
        self._mesh_placeholder.setText("Mesh preview paused (Mesh Studio)")
        self._mesh_placeholder.show()

    def _open_in_mesh_studio(self) -> None:
        """Open Mesh Studio after stopping Packages preview GL.

        Stage mesh+textures *before* open (never write into the folder while
        Mesh Studio is loading — that GIL fight stutters until freeze).
        """
        e = self._mesh_entry_from_selection()
        self._release_mesh_preview_for_studio()

        if e is not None and e.path is not None and e.path.is_file():
            self.mesh_open.emit(str(e.path))
            return

        if e is None or self._chump is None or not e.kuid or not e.rel:
            if self._mesh_staged_path is not None and self._mesh_staged_path.is_file():
                self.mesh_open.emit(str(self._mesh_staged_path))
                return
            QMessageBox.information(
                self, "Mesh Studio", "เลือกไฟล์ .im / .trainzmesh / .fbx ก่อน"
            )
            return

        rel = e.rel.replace("\\", "/")
        token = safe_stage_token(e.kuid)
        dest = self._mesh_stage_root / token
        self.preview_lab.setText("Preparing mesh + textures for Mesh Studio…")
        self.preview_meta.setText(
            f"{Path(rel).name}\n\nStaging from CDP (preview GL paused)…"
        )
        self.preview_stack.setCurrentIndex(3)
        self._cancel_mesh_stage_worker()
        self._mesh_req += 1
        req = self._mesh_req
        worker = _CdpMeshStageWorker(
            self._chump,
            e.kuid,
            rel,
            dest,
            parent=self,
            with_textures=True,
            wipe=True,
        )
        self._mesh_stage_worker = worker

        def on_ok(path_s: str, r: int = req, t: str = token) -> None:
            if r != self._mesh_req:
                return
            self._mesh_staged.add(t)
            self._mesh_stage_worker = None
            self._mesh_staged_path = Path(path_s)
            self.preview_lab.setText(f"Opening Mesh Studio — {Path(path_s).name}")
            self.mesh_open.emit(path_s)

        def on_err(msg: str, r: int = req) -> None:
            if r != self._mesh_req:
                return
            self._mesh_stage_worker = None
            QMessageBox.warning(self, "Mesh Studio", msg)

        worker.ok.connect(on_ok)
        worker.err.connect(on_err)
        worker.start()

    def _enginespec_target(self) -> tuple[str, str] | None:
        """(kuid, config text) only when preview is that asset's config.txt and kind is enginespec."""
        if self._chump is None:
            return None
        src = self._preview_src
        if src is None or src[0] != "cdp":
            return None
        key = src[1]
        # only the virtual / real config — never .gse / mesh.txt / random txt in the asset
        if "/__config__" not in key and not key.lower().endswith("/config.txt"):
            return None
        kuid = key.split("/", 1)[0]
        if not kuid:
            return None
        if self.preview_stack.currentIndex() == 2:
            text = self.preview_edit.toPlainText()
        else:
            try:
                text = asset_config_text(self._chump, kuid)
            except Exception:
                return None
        # parsed kind == enginespec (or real throttle-power block) — not substring "enginespec"
        if not looks_like_enginespec(text):
            return None
        return kuid, text

    def _update_engine_tuner_btn(self) -> None:
        self.btn_engine_tuner.setVisible(self._enginespec_target() is not None)

    def _open_in_engine_tuner(self) -> None:
        target = self._enginespec_target()
        if target is None:
            QMessageBox.information(
                self,
                "Engine Tuner",
                "Select an enginespec asset / config.txt that Engine Tuner supports.",
            )
            return
        kuid, text = target
        cdp_name = self._active_cdp.name if self._active_cdp else "CDP"
        label = f"{cdp_name} · {kuid}"
        self.enginespec_open.emit(kuid, text, label)

    def apply_enginespec_save(self, kuid: str, text: str) -> Path | None:
        """Write tuned config into open CDP; save to disk when path known."""
        if self._chump is None:
            raise RuntimeError("No CDP open")
        replace_asset_config(self._chump, kuid, text)
        self._mark_cdp_edited(kuid, "__config__")
        out: Path | None = self._active_cdp
        if out is not None:
            save_cdp(out, self._chump)
            self._clear_cdp_edits()
        else:
            start = str(Path.home() / "edited.cdp")
            path, _ = QFileDialog.getSaveFileName(
                self, "Save CDP", start, "Trainz CDP (*.cdp);;All (*.*)"
            )
            if not path:
                raise RuntimeError("Save cancelled — CDP path required")
            out = Path(path)
            if out.suffix.lower() != ".cdp":
                out = out.with_suffix(".cdp")
            save_cdp(out, self._chump)
            self._active_cdp = out
            self._clear_cdp_edits()
            if not any(q.path == out for q in self._queue):
                self._queue.append(QueueItem(out, "cdp"))
            self._refresh_queue()
        self._refresh_finder()
        # refresh preview if still on this config
        if (
            self._preview_src
            and self._preview_src[0] == "cdp"
            and self._preview_src[1].startswith(f"{kuid}/")
        ):
            try:
                data = asset_config_text(self._chump, kuid).encode("utf-8")
                self._preview_bytes = data
                if self.preview_stack.currentIndex() == 2:
                    self.preview_edit.setPlainText(decode_asset_text(data))
            except Exception:
                pass
        return out

    def _preview_entry(self, e: FinderEntry) -> None:
        self._audio_stop()
        self.btn_engine_tuner.setVisible(False)
        self.btn_fast_preview.setVisible(False)
        self.btn_mesh_studio.setVisible(False)
        self._mesh_staged_path = None
        try:
            if e.path is not None and e.path.is_file():
                name = e.path.name
                if self._is_mesh_name(name):
                    self._show_mesh_pick_card(e)
                    return
                self._drop_mesh_warm()
                data = e.path.read_bytes()
                self._preview_src = ("disk", str(e.path), name)
            elif e.rel == "__config__" and self._chump is not None:
                self._drop_mesh_warm()
                data = asset_config_text(self._chump, e.kuid).encode("utf-8")
                name = "config.txt"
                self._preview_src = ("cdp", f"{e.kuid}/__config__", name)
            elif self._chump is not None and e.rel:
                name = Path(e.rel).name
                if self._is_mesh_name(name):
                    self._show_mesh_pick_card(e)
                    return
                self._drop_mesh_warm()
                data = read_file_bytes(self._chump, e.kuid, e.rel)
                self._preview_src = ("cdp", f"{e.kuid}/{e.rel}", name)
            else:
                self._clear_preview()
                return
        except Exception as exc:
            self.preview_lab.setText(f"Cannot open: {exc}")
            self.preview_stack.setCurrentIndex(3)
            self.preview_meta.setText(str(exc))
            return

        self._preview_bytes = data
        self.preview_lab.setText(f"{name} · {format_bytes(len(data))} · {_file_kind_label(name)}")
        self.btn_save_text.setEnabled(False)

        if _is_image_name(name):
            pix = _load_preview_pixmap(data, name)
            if pix is not None and not pix.isNull():
                w = max(280, self.preview_image.width() or 420)
                h = max(220, self.preview_image.height() or 360)
                scaled = pix.scaled(
                    w,
                    h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_image.setPixmap(scaled)
                self.preview_stack.setCurrentIndex(1)
            else:
                self.preview_stack.setCurrentIndex(3)
                self.preview_meta.setText(
                    f"Image decode failed\n{name}\n{format_bytes(len(data))}\n"
                    "(TGA needs Pillow; PNG/JPG/BMP via Qt)"
                )
            self._sync_editor_tab()
            return

        if _is_audio_name(name):
            self.audio_title.setText(name)
            self.audio_meta.setText(f"{_file_kind_label(name)} · {format_bytes(len(data))}")
            self.preview_stack.setCurrentIndex(4)
            self._sync_editor_tab()
            return

        if _is_text_name(name) or self._looks_text(data):
            text = decode_asset_text(data)
            self.preview_edit.set_syntax(syntax_for_filename(name))
            self.preview_edit.setPlainText(text)
            self._apply_pane_mode()
            return

        head = data[:64].hex(" ")
        self.preview_meta.setText(
            f"{name}\n{_file_kind_label(name)}\n{format_bytes(len(data))}\n\n"
            f"Header:\n{head}"
        )
        self.preview_stack.setCurrentIndex(3)
        self._update_engine_tuner_btn()
        self._sync_editor_tab()

    def _ensure_player(self):
        if self._clip_player is None:
            from ..sounds.player import ClipPlayer

            self._clip_player = ClipPlayer()
        return self._clip_player

    def _audio_play(self) -> None:
        if self._preview_bytes is None or self._preview_src is None:
            return
        name = self._preview_src[2]
        tmp = Path(tempfile.gettempdir()) / f"tzs_pkg_aud_{os.getpid()}_{time.time_ns()}{Path(name).suffix}"
        try:
            tmp.write_bytes(self._preview_bytes)
            self._audio_tmp = tmp
            from ...audio.decode import load_mono_pcm16

            mono, sr = load_mono_pcm16(tmp)
            player = self._ensure_player()
            player.load(mono, sr)
            player.play(loop=False)
            self.btn_audio_play.setText("Playing…")
            self._msg(f"Playing {name}")
        except Exception as exc:
            QMessageBox.warning(self, "Audio", str(exc))

    def _audio_stop(self) -> None:
        if self._clip_player is not None:
            try:
                self._clip_player.stop()
            except Exception:
                pass
        if hasattr(self, "btn_audio_play"):
            self.btn_audio_play.setText("Play")
        if self._audio_tmp is not None:
            try:
                self._audio_tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._audio_tmp = None

    @staticmethod
    def _looks_text(data: bytes) -> bool:
        if not data:
            return True
        sample = data[:2048]
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def _save_preview_text(self) -> None:
        if self._preview_src is None:
            return
        text = self.preview_edit.toPlainText()
        data = text.encode("utf-8")
        src, key, name = self._preview_src
        if src == "disk":
            path = Path(key)
            # ponytail: temp sibling .bak only for the overwrite; delete on success
            bak_path = path.with_suffix(path.suffix + ".bak")
            wrote_bak = False
            if path.is_file():
                bak_path.write_bytes(path.read_bytes())
                wrote_bak = True
            try:
                path.write_text(
                    text if text.endswith("\n") else text + "\n", encoding="utf-8"
                )
            except Exception:
                raise
            if wrote_bak and bak_path.is_file():
                try:
                    bak_path.unlink()
                except OSError:
                    pass
            self._msg(f"Saved {path.name}")
            self._refresh_finder()
            return
        # cdp — config is virtual tags; other paths are BINARY blobs
        if key.endswith("/__config__"):
            kuid = key[: -len("/__config__")]
            if self._chump is None or not kuid:
                return
            try:
                replace_asset_config(self._chump, kuid, text)
            except Exception as exc:
                QMessageBox.warning(self, "Save into CDP", str(exc))
                return
            self._mark_cdp_edited(kuid, "__config__")
            self._invalidate_mesh_stage()
            self._preview_bytes = data
            self._refresh_finder()
            self._msg(f"Updated config.txt for {kuid} (Save CDP… to write)")
            return
        kuid, _, rel = key.partition("/")
        if self._chump is None or not rel:
            return
        try:
            replace_file(self._chump, kuid, rel, data)
        except Exception as exc:
            QMessageBox.warning(self, "Save into CDP", str(exc))
            return
        self._mark_cdp_edited(kuid, rel)
        self._invalidate_mesh_stage()
        self._preview_bytes = data
        self._refresh_finder()
        self._msg(f"Updated {rel} in CDP (Save CDP… to write)")

    def _replace_selected(self) -> None:
        e = self._current_finder_entry()
        if e is None or e.kind in ("dir", "asset"):
            QMessageBox.information(self, "Replace", "Select a file in Finder.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Replace with file", str(Path.home()), "All (*.*)"
        )
        if not path:
            return
        data = Path(path).read_bytes()
        if e.path is not None and e.path.is_file():
            e.path.write_bytes(data)
            self._msg(f"Replaced {e.path.name}")
            self._refresh_finder()
            self._preview_entry(e)
            return
        if self._chump is None or not e.rel or e.rel == "__config__":
            QMessageBox.information(self, "Replace", "Cannot replace this entry.")
            return
        try:
            replace_file(self._chump, e.kuid, e.rel, data)
        except Exception as exc:
            QMessageBox.warning(self, "Replace", str(exc))
            return
        self._mark_cdp_edited(e.kuid, e.rel)
        self._invalidate_mesh_stage()
        self._refresh_finder()
        self._msg(f"Replaced {e.rel} (Save CDP… to write)")

    def _delete_selected(self) -> None:
        entries = self._selected_finder_entries()
        if not entries:
            return
        if self._finder_mode == "disk":
            QMessageBox.information(
                self, "Delete", "Finder disk mode ไม่ลบไฟล์บนดิสก์ — ใช้ Remove ใน Queue"
            )
            return
        if self._chump is None:
            return

        files = [e for e in entries if e.rel and e.rel != "__config__" and e.kind not in ("dir", "asset")]
        assets = [e for e in entries if e.kind == "asset" and e.kuid]

        if files and assets:
            QMessageBox.information(
                self, "Delete", "เลือกได้แค่ไฟล์ หรือ asset อย่างใดอย่างหนึ่งต่อครั้ง"
            )
            return

        if assets:
            if len(assets) > 1:
                QMessageBox.information(self, "Delete", "ลบ asset ได้ทีละตัว")
                return
            e = assets[0]
            if not remove_asset(self._chump, e.kuid):
                return
            self._mark_cdp_edited(e.kuid)
            self._dirty_paths = {p for p in self._dirty_paths if not p.startswith(e.kuid + "/")}
            self._invalidate_mesh_stage()
            self._cdp_cwd = []
            self._refresh_finder()
            self._clear_preview()
            self._msg(f"Removed asset {e.kuid} (Save CDP…)")
            return

        if not files:
            return
        if len(files) > 1:
            ans = QMessageBox.question(
                self,
                "Delete files",
                f"ลบ {len(files)} ไฟล์ออกจาก CDP?\n(ต้อง Save CDP… เพื่อเขียนลงดิสก์)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        removed = 0
        for e in files:
            if remove_file(self._chump, e.kuid, e.rel):
                removed += 1
                # keep path in dirty set so parent folders still show E
                self._mark_cdp_edited(e.kuid, e.rel)
        if removed <= 0:
            return
        self._invalidate_mesh_stage()
        self._refresh_finder()
        self._clear_preview()
        if removed == 1:
            self._msg(f"Removed {files[0].rel} (Save CDP…)")
        else:
            self._msg(f"Removed {removed} files (Save CDP…)")

    def _delete_all_fbx(self) -> None:
        if self._chump is None or self._finder_mode != "cdp":
            QMessageBox.information(self, ".fbx", "เปิด CDP ก่อน")
            return
        hits = self._scan_cdp_by_suffix(".fbx")
        if not hits:
            QMessageBox.information(self, ".fbx", "ไม่พบไฟล์ .fbx ใน CDP นี้")
            self._finder_scan = "fbx"
            if hasattr(self, "btn_find_fbx"):
                self.btn_find_fbx.setChecked(True)
            self._refresh_finder()
            return
        ans = QMessageBox.question(
            self,
            "Delete all .fbx",
            f"พบ {len(hits)} ไฟล์ .fbx\nลบทั้งหมดออกจาก CDP?\n(ต้อง Save CDP… เพื่อเขียนลงดิสก์)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self._finder_scan = "fbx"
            if hasattr(self, "btn_find_fbx"):
                self.btn_find_fbx.setChecked(True)
            self._refresh_finder()
            return
        removed = 0
        for e in hits:
            if remove_file(self._chump, e.kuid, e.rel):
                removed += 1
                self._mark_cdp_edited(e.kuid, e.rel)
        self._invalidate_mesh_stage()
        self._finder_scan = "fbx"
        if hasattr(self, "btn_find_fbx"):
            self.btn_find_fbx.setChecked(True)
        self._refresh_finder()
        self._clear_preview()
        self._msg(f"Removed {removed} × .fbx (Save CDP…)")

    def save_active_cdp(self) -> None:
        if self._chump is None:
            QMessageBox.information(self, "Save CDP", "Open a CDP first.")
            return
        start = str(self._active_cdp or (Path.home() / "edited.cdp"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CDP", start, "Trainz CDP (*.cdp);;All (*.*)"
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != ".cdp":
            out = out.with_suffix(".cdp")
        try:
            save_cdp(out, self._chump)
        except Exception as exc:
            QMessageBox.critical(self, "Save CDP", str(exc))
            return
        # save_cdp already drops temp .bak on success; sweep any leftover
        discard_cdp_bak(out)
        self._active_cdp = out
        self._clear_cdp_edits()
        if not any(q.path == out for q in self._queue):
            self._queue.append(QueueItem(out, "cdp"))
        self._refresh_queue()
        self._refresh_finder()
        self._msg(f"Saved {out.name}")

    # ── sidebar actions ──────────────────────────────────────

    def action_open_cdp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CDP", str(Path.home()), "Trainz CDP (*.cdp);;All (*.*)"
        )
        if path:
            self.add_queue_paths([Path(path)])

    def action_pack_cdp(self) -> None:
        folders = self._pack_folders()
        if not folders:
            d = QFileDialog.getExistingDirectory(
                self, "Pick asset folder (with config.txt)", str(Path.home())
            )
            if not d:
                return
            self.add_queue_paths([Path(d)])
            folders = self._pack_folders()
        missing = [f for f in folders if not (f / "config.txt").is_file()]
        if missing:
            QMessageBox.warning(
                self,
                "Pack CDP",
                "Missing config.txt:\n" + "\n".join(str(m) for m in missing[:8]),
            )
            return
        est = estimate_pack_size(folders)
        verdict = classify_size(est)
        if verdict.band == "refuse":
            QMessageBox.critical(self, "Pack CDP", f"{verdict.label}\n{format_bytes(est)}")
            return
        if verdict.band in ("soft", "warn"):
            ok = QMessageBox.question(
                self,
                "Pack CDP — size",
                f"{verdict.label}\nประมาณ {format_bytes(est)}\nPack ต่อไหม?",
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        suggest = folders[0].parent / f"{folders[0].name}.cdp"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save packed CDP", str(suggest), "Trainz CDP (*.cdp);;All (*.*)"
        )
        if not path:
            return
        try:
            out, actual = pack_asset_folders(folders, Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Pack CDP", str(exc))
            return
        self.add_queue_paths([out])
        self._msg(f"Packed → {out.name} ({format_bytes(out.stat().st_size)}) — {actual.label}")

    def action_extract_cdp(self) -> None:
        path = self._selected_cdp()
        if path is None:
            path_s, _ = QFileDialog.getOpenFileName(
                self, "Extract CDP", str(Path.home()), "Trainz CDP (*.cdp);;All (*.*)"
            )
            if not path_s:
                return
            path = Path(path_s)
        dest = QFileDialog.getExistingDirectory(self, "Extract into folder", str(path.parent))
        if not dest:
            return
        try:
            written = extract_cdp(path, Path(dest))
        except Exception as exc:
            QMessageBox.warning(self, "Extract CDP", str(exc))
            return
        discard_cdp_bak(path)
        self._msg(f"Extracted {len(written)} file(s) → {dest}")
        # open extract dest in Finder
        self.add_queue_paths([Path(dest)])
        self._open_disk(Path(dest))

    def action_open_tzarc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TZarc", str(Path.home()), "Trainz archive (*.tzarc);;All (*.*)"
        )
        if not path:
            return
        try:
            names = list_tzarc(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "TZarc", str(exc))
            return
        self._tzarc_path = Path(path)
        self.tz_lab.setVisible(True)
        self.tz_lab.setText(
            f"TZarc {Path(path).name}: " + ", ".join(names[:40]) + ("…" if len(names) > 40 else "")
        )
        self._msg(f"TZarc {Path(path).name} — {len(names)} file(s)")

    def action_extract_tzarc(self) -> None:
        path = self._tzarc_path
        if path is None:
            path_s, _ = QFileDialog.getOpenFileName(
                self, "Extract TZarc", str(Path.home()), "Trainz archive (*.tzarc);;All (*.*)"
            )
            if not path_s:
                return
            path = Path(path_s)
        dest = QFileDialog.getExistingDirectory(self, "Extract into folder", str(path.parent))
        if not dest:
            return
        try:
            written = extract_tzarc(path, Path(dest))
        except Exception as exc:
            QMessageBox.warning(self, "TZarc extract", str(exc))
            return
        self._msg(f"Extracted {len(written)} file(s) → {dest}")
        self.add_queue_paths([Path(dest)])
        self._open_disk(Path(dest))

    def action_copy_kuids(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = "\n".join(self._pkg_kuids)
        if not text:
            self._msg("No KUIDs to copy")
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(text)
        self._msg(f"Copied {len(self._pkg_kuids)} KUID(s)")
