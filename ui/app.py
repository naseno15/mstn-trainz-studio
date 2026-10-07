"""Main window — Apple chrome, material groups, PBR modes, loading overlay."""
from __future__ import annotations

import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPoint, QEvent, QObject, QRect, QRectF
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# HOME boot: no Sounds / Editor / loaders / OpenGL here — assembled on demand.
from ..io.anim import peek_kin
from ..io.history import EditSnapshot, UndoStack
from ..io.mesh_meta import (
    apply_meta_two_sided_to_parts,
    find_mesh_meta,
    mesh_meta_path,
    read_two_sided,
)
from ..io.project import (
    ProjectState,
    clear_crash_backup,
    has_crash_recovery,
    load_crash_backup,
    load_project,
    save_project,
    write_crash_backup,
)
from ..io.scene import AnimClip, Scene
from ..io.texture import (
    TextureReport,
    check_texture_txt,
    format_report,
    material_family,
    resolve_primary_image,
    scan_folder,
    stems_match,
    texture_stem,
)
from ..lamps import (
    MAX_LAMPS,
    Lamp,
    discover_lamps,
    lamp_from_stem,
    lamps_from_stem,
    lamp_uid,
    merge_lamps,
)
from ..render.env import ENVIRONMENTS, env_keys
from ..render.hdri import list_hdri_assets
from .code_edit import apply_code_edit_theme
from .frost import (
    FROST_CONTENT_MARGINS,
    FrostGlassFrame,
    make_frost_pixmap,
    paint_glass_chip,
    prepare_frost_scroll,
    set_glass_dark,
)
from .home import build_home_page
from .motion import (
    HUB_DIR_DOWN,
    HUB_DIR_LEFT,
    HUB_DIR_RIGHT,
    HUB_DIR_UP,
    HubRevealOverlay,
    animate_geometry,
    animate_max_height,
    SCRUB_LERP,
    apple_pop_pill,
    attach_hover_bubble,
    fade_overlay,
    fade_stack_to,
    lerp_pill_rects,
    nearest_index_at_x,
    pulse_checkbox,
    slide_to,
    stack_selector_chrome,
    stop_slide,
)
from .theme import apply_theme, app_font, palette, qpalette_for
from .title_chrome import (
    EDGE_GRIP,
    TITLE_CONTENT_INSET,
    FloatTitleBar,
    edge_at,
    install_frameless,
)

if TYPE_CHECKING:
    from ..lamps.bake import BakeResult, BakeSettings
    from .editor import EditorWorkspace

from .. import PKG_ROOT

HERE = PKG_ROOT
FIXTURES = HERE / "fixtures"
ASSETS = HERE / "assets"
LOGO_WHITE = ASSETS / "mstn_logo_white.png"
MESH_EXTS = {".fbx", ".im", ".trainzmesh"}
EDITOR_DOCK_W = 480
EDITOR_DOCK_MS = 220  # overlay slide — viewport stays put (crop, not resize)
SIDE_PANEL_W = 420
SIDE_PANEL_MARGIN = 10
SIDE_PANEL_RADIUS = 14.0
PANEL_EDGE_W = 22
KIN_EXT = ".kin"
STACK_HUB = 0
STACK_GL = 1
HUB_HOME = 0
HUB_MESH = 1
HUB_SOUNDS = 2
HUB_ENGINE = 3
HUB_ASSETS = 4
DUMMY_FRAMES = 120
# Keep shading keys here so boot does not import OpenGL/view3d.
SHADING_WIRE = "wire"
SHADING_SOLID = "solid"
SHADING_MATERIAL = "material"
SHADING_RENDERED = "rendered"
CRASH_LOG = Path.home() / ".cache" / "trainz_studio" / "last_error.txt"
CRASH_NOTIFY = CRASH_LOG.parent / "last_error.notify"
_FAULT_LOG_FH = None  # keep faulthandler stream alive


def _compact_tip(lab: QLabel) -> None:
    """Sidebar tip style — muted, wrap, no stretch greed."""
    lab.setObjectName("mutedTip")
    lab.setWordWrap(True)
    lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)


def _install_crash_log() -> Path:
    """pythonw swallows tracebacks — file + optional dialog + next-launch notify."""
    import faulthandler

    global _FAULT_LOG_FH
    CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        fault_path = CRASH_LOG.parent / "fault.log"
        _FAULT_LOG_FH = open(fault_path, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_FAULT_LOG_FH, all_threads=True)
    except OSError:
        _FAULT_LOG_FH = None

    def _hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            CRASH_LOG.write_text(text, encoding="utf-8")
            CRASH_NOTIFY.write_text("1", encoding="utf-8")
        except OSError:
            pass
        # Best-effort glass dialog before the process dies (may fail under hard abort).
        try:
            app = QApplication.instance()
            if app is not None:
                from .crash_dialog import show_crash_dialog

                short = f"{getattr(exc_type, '__name__', exc_type)}: {exc}"
                body = text if len(text) <= 4000 else text[:1600] + "\n…\n" + text[-2000:]
                show_crash_dialog(
                    title="Unexpected error",
                    summary=short,
                    detail=body,
                    log_path=CRASH_LOG,
                    kind="error",
                    parent=app.activeWindow(),
                )
                # OK starts MainWindow quit fade — let the event loop finish it.
                return
        except SystemExit:
            raise
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    return CRASH_LOG


def offer_pending_crash_report(parent: QWidget | None = None) -> None:
    """Show last crash cause once after a session that died mid-run."""
    if not CRASH_NOTIFY.is_file() or not CRASH_LOG.is_file():
        return
    try:
        text = CRASH_LOG.read_text(encoding="utf-8")
        CRASH_NOTIFY.unlink(missing_ok=True)
    except OSError:
        return
    if not text.strip():
        return
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    summary = lines[-1] if lines else "Unknown error"
    for ln in reversed(lines):
        if ln.startswith(("File ", "Traceback", "~^", "^")):
            continue
        summary = ln
        break
    if len(summary) > 160:
        summary = summary[:157] + "…"
    body = text if len(text) <= 4500 else text[:1800] + "\n…\n" + text[-2200:]
    try:
        from .crash_dialog import show_crash_dialog

        show_crash_dialog(
            title="Previous session crashed",
            summary=summary,
            detail=body,
            log_path=CRASH_LOG,
            kind="warning",
            parent=parent,
        )
    except Exception:
        QMessageBox.warning(
            parent,
            "Trainz Studio — previous session crashed",
            f"{summary}\n\n{body}\n\nLog:\n{CRASH_LOG}",
        )

def _trim_transparent(pix: QPixmap) -> QPixmap:
    img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return pix
    min_x, min_y, max_x, max_y = w, h, 0, 0
    # stride sample for speed, then refine edges
    step = max(1, min(w, h) // 128)
    found = False
    for y in range(0, h, step):
        for x in range(0, w, step):
            if img.pixelColor(x, y).alpha() > 12:
                found = True
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if not found:
        return pix
    # expand by step to cover skipped pixels
    min_x = max(0, min_x - step)
    min_y = max(0, min_y - step)
    max_x = min(w - 1, max_x + step)
    max_y = min(h - 1, max_y + step)
    return QPixmap.fromImage(img.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))


_LOGO_BASE: QPixmap | None = None
_LOGO_CACHE: dict[tuple[int, str], QPixmap] = {}


def _logo_pixmap(width: int = 120, *, mode: str = "dark") -> QPixmap:
    global _LOGO_BASE
    mode = mode if mode in ("dark", "light") else "dark"
    key = (int(width), mode)
    hit = _LOGO_CACHE.get(key)
    if hit is not None and not hit.isNull():
        return hit
    out = QPixmap()
    if LOGO_WHITE.is_file():
        if _LOGO_BASE is None or _LOGO_BASE.isNull():
            raw = QPixmap(str(LOGO_WHITE))
            _LOGO_BASE = _trim_transparent(raw) if not raw.isNull() else raw
        pix = _LOGO_BASE
        if not pix.isNull():
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            if mode == "light":
                out = QPixmap(pix.size())
                out.fill(Qt.GlobalColor.transparent)
                p = QPainter(out)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.fillRect(out.rect(), QColor("#1d1d1f"))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                p.drawPixmap(0, 0, pix)
                p.end()
            else:
                out = pix
    if out.isNull():
        out = QPixmap(width, max(28, width // 4))
        out.fill(QColor(0, 0, 0, 0))
    _LOGO_CACHE[key] = out
    return out


def warm_logo_cache() -> None:
    """Pre-scale dark/light logos used by chrome — theme toggle just swaps pixmaps."""
    for w in (108, 140, 160, 180):
        for mode in ("dark", "light"):
            _logo_pixmap(w, mode=mode)


PBR_MODES = (
    ("Lit", 0),
    ("Albedo", 1),
    ("Normal", 2),
    ("Rough", 3),
    ("Metal", 4),
    ("AO", 5),
)

SHADING_MODES = (
    ("Wire", SHADING_WIRE),
    ("Solid", SHADING_SOLID),
    ("Material", SHADING_MATERIAL),
    ("Rendered", SHADING_RENDERED),
)

# Editor Tab pie — View = select/look only; Move = Blender translate gizmo
ATT_EDIT_VIEW = "view"
ATT_EDIT_MOVE = "move"
ATT_EDIT_MODES = (
    ("View", ATT_EDIT_VIEW),
    ("Move", ATT_EDIT_MOVE),
)

# tree / list item roles
ROLE_STEM = Qt.ItemDataRole.UserRole
ROLE_REPORT = Qt.ItemDataRole.UserRole + 1
ROLE_KIND = Qt.ItemDataRole.UserRole + 2  # group | map | lone | scene | folder | mesh
ROLE_PATH = Qt.ItemDataRole.UserRole + 3
ROLE_MAP_ROLE = Qt.ItemDataRole.UserRole + 4
ROLE_GROUP_STEMS = Qt.ItemDataRole.UserRole + 5
ROLE_MESH_KEY = Qt.ItemDataRole.UserRole + 6


@dataclass
class TexEntry:
    stem: str
    label: str
    kind: str  # scene | folder
    report: TextureReport | None = None
    path: Path | None = None
    map_role: str | None = None
    family: str = ""
    mesh_key: str = ""


@dataclass
class MatGroup:
    key: str
    entries: list[TexEntry] = field(default_factory=list)


class LoadWorker(QThread):
    """Load one or more meshes + warm albedos off the UI thread."""

    ok = Signal(object, object)  # Scene, decoded tex dict
    err = Signal(str)
    progress = Signal(str, int)  # stage, pct 0-100

    def __init__(
        self,
        paths: Path | list[Path],
        parent=None,
        *,
        base_scene: Scene | None = None,
    ) -> None:
        super().__init__(parent)
        if isinstance(paths, Path):
            self.paths = [paths]
        else:
            self.paths = [Path(p) for p in paths]
        self.base_scene = base_scene

    def run(self) -> None:
        try:
            parts: list = list(self.base_scene.parts) if self.base_scene else []
            attachments: list = list(self.base_scene.attachments) if self.base_scene else []
            anims: list = list(self.base_scene.anims) if self.base_scene else []
            decoded: dict[str, tuple[int, int, bytes]] = {}
            sources: list[str] = []
            kinds: list[str] = []
            n = len(self.paths)
            multi = n > 1 or bool(self.base_scene and self.base_scene.parts)

            for i, path in enumerate(self.paths):
                size_mb = path.stat().st_size / (1024 * 1024)
                base_pct = int(5 + (80 * i) / max(n, 1))

                def on_prog(msg: str, pct: int | None = None, _i=i, _bp=base_pct) -> None:
                    # nest file progress into overall band
                    local = int(pct if pct is not None else 0)
                    overall = _bp + int(local * 0.7 / max(n, 1))
                    prefix = f"[{_i + 1}/{n}] " if n > 1 else ""
                    self.progress.emit(f"{prefix}{msg}", min(90, overall))

                on_prog(f"Opening {path.name} ({size_mb:.1f} MB)…", 2)
                from ..io.loaders import load_any

                scene = load_any(path, progress=on_prog)
                key = path.name
                for part in scene.parts:
                    part.mesh_key = key
                for att in scene.attachments:
                    if multi:
                        att.name = f"{path.stem}/{att.name}"
                parts.extend(scene.parts)
                attachments.extend(scene.attachments)
                anims.extend(scene.anims)
                sources.append(str(path))
                if scene.kind:
                    kinds.append(scene.kind)

            # --- parallel texture precache (albedo 2k + full normal/param) ---
            from ..io.texcache import (
                PREVIEW_MAX_DIM_ALBEDO,
                collect_scene_texture_paths_split,
                preload_textures,
            )

            albedos, others = collect_scene_texture_paths_split(parts)
            n_tex = len(albedos) + len(others)
            if n_tex:
                self.progress.emit(f"Precaching {n_tex} textures…", 88)

                def on_tex(msg: str, pct: int) -> None:
                    # map 0-100 into 88-98
                    self.progress.emit(msg, min(98, 88 + int(pct * 0.10)))

                if albedos:
                    decoded.update(
                        preload_textures(
                            albedos,
                            flip_v=False,
                            max_dim=PREVIEW_MAX_DIM_ALBEDO,
                            progress=on_tex,
                        )
                    )
                if others:
                    decoded.update(
                        preload_textures(
                            others, flip_v=False, max_dim=0, progress=on_tex
                        )
                    )

            mesh_keys = {p.mesh_key for p in parts if p.mesh_key}
            kind = "multi" if len(mesh_keys) > 1 else (kinds[0] if kinds else "unknown")
            note = f"{len(mesh_keys)} mesh(es)" if len(mesh_keys) > 1 else ""
            # Keep raw tzMF bytes only for a single trainzmesh (Editor Save buffer).
            src_bytes = None
            if (
                kind == "trainzmesh"
                and len(self.paths) == 1
                and not self.base_scene
            ):
                src_bytes = getattr(scene, "source_bytes", None)
            out = Scene(
                source="; ".join(sources),
                kind=kind,
                parts=parts,
                attachments=attachments,
                anims=anims,
                note=note,
                source_bytes=src_bytes,
            )
            self.progress.emit(
                f"Handing off · {len(decoded)} textures ready",
                100,
            )
            self.ok.emit(out, decoded)
        except Exception as e:
            self.err.emit(str(e))


class VeScanWorker(QThread):
    """App-wide VE Rules scan off the UI thread (any studio)."""

    done = Signal(object, object)  # list[VeReport], summary dict
    err = Signal(str)

    def __init__(self, paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self._paths = [Path(p) for p in paths]

    def run(self) -> None:
        try:
            from ..io.ve_rules import scan_paths, summarize_reports

            reports = scan_paths(self._paths)
            self.done.emit(reports, summarize_reports(reports))
        except Exception as e:  # noqa: BLE001
            self.err.emit(str(e))


class AccentPill(QWidget):
    """Orange selector — paintEvent (QSS pills vanish on Preview/Editor GL pages)."""

    def __init__(self, parent: QWidget | None = None, *, radius: float = 12.0) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

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


class ModePie(QWidget):
    """Blender-style hold-Tab pie — aim, release (or click) to pick a mode key."""

    mode_picked = Signal(str)
    dismissed = Signal()  # click/Esc path when parent wants to commit/cancel

    def __init__(
        self,
        modes: tuple[tuple[str, str], ...] | list[tuple[str, str]],
        *,
        title: str = "Mode",
        default_hover: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modePie")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        self.setMouseTracking(True)
        self._modes = list(modes)  # (label, key)
        self._title = str(title)
        n = max(1, len(self._modes))
        self._hover = int(default_hover) % n
        self._default_hover = self._hover
        self._cx = 0.0
        self._cy = 0.0
        self.hide()

    def popup_at(self, global_pos: QPoint) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.setGeometry(host.rect())
        local = self.mapFromGlobal(global_pos)
        self._cx = float(local.x())
        self._cy = float(local.y())
        self._hover = self._sector_at(local)
        self.show()
        self.raise_()
        self.grabMouse()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self.update()

    def commit(self) -> str | None:
        if not self.isVisible():
            return None
        self.releaseMouse()
        self.hide()
        if 0 <= self._hover < len(self._modes):
            return str(self._modes[self._hover][1])
        return None

    def cancel(self) -> None:
        if self.isVisible():
            self.releaseMouse()
            self.hide()

    def _sector_at(self, pos: QPoint) -> int:
        import math

        n = len(self._modes)
        if n <= 0:
            return 0
        dx = float(pos.x()) - self._cx
        dy = float(pos.y()) - self._cy
        if dx * dx + dy * dy < 36.0:
            return self._hover
        # 0 = up, then clockwise
        ang = math.atan2(dx, -dy)
        if ang < 0:
            ang += 2 * math.pi
        return int(ang / (2 * math.pi / n)) % n

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        idx = self._sector_at(event.position().toPoint())
        if idx != self._hover:
            self._hover = idx
            self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Sticky / click-to-confirm — parent commits via dismissed
        if event.button() == Qt.MouseButton.LeftButton:
            self._hover = self._sector_at(event.position().toPoint())
            self.dismissed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        import math

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        r_outer, r_inner = 118.0, 36.0
        pie = QRectF(
            self._cx - r_outer, self._cy - r_outer, r_outer * 2, r_outer * 2
        )
        n = max(1, len(self._modes))
        sector = 360.0 / n
        for i, (label, _key) in enumerate(self._modes):
            # Qt angles: 1/16°, 0=east, CCW. Sector 0 = up.
            start = int((90 - i * sector + sector / 2) * 16)
            span = int(-sector * 16)
            hot = i == self._hover
            p.setBrush(QColor(255, 90, 31, 210) if hot else QColor(40, 46, 54, 220))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
            p.drawPie(pie, start, span)
            mid_deg = -90.0 + i * sector
            mid = math.radians(mid_deg)
            tx = self._cx + math.cos(mid) * (r_outer * 0.62)
            ty = self._cy + math.sin(mid) * (r_outer * 0.62)
            p.setPen(QColor("#ffffff") if hot else QColor("#c8ccd0"))
            font = p.font()
            font.setBold(hot)
            font.setPointSize(11)
            p.setFont(font)
            p.drawText(QRectF(tx - 48, ty - 12, 96, 24), Qt.AlignmentFlag.AlignCenter, label)
        p.setBrush(QColor(22, 26, 32, 240))
        p.setPen(QPen(QColor(255, 90, 31, 180), 2.0))
        p.drawEllipse(QPoint(int(self._cx), int(self._cy)), int(r_inner), int(r_inner))
        p.setPen(QColor("#ff5a1f"))
        p.drawText(
            QRectF(self._cx - 40, self._cy - 10, 80, 20),
            Qt.AlignmentFlag.AlignCenter,
            self._title,
        )


class ShadingPie(ModePie):
    """Preview Tab pie — Wire / Solid / Material / Rendered."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            SHADING_MODES, title="Shading", default_hover=3, parent=parent
        )
        self.setObjectName("shadingPie")


class EditModePie(ModePie):
    """Editor Tab pie — View (look) / Move (translate gizmo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            ATT_EDIT_MODES, title="Edit", default_hover=0, parent=parent
        )
        self.setObjectName("editModePie")


class SegmentedControl(QFrame):
    """Exclusive Lit | Albedo | … pills — click or press-drag scrub, commit on release."""

    mode_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
        modes: tuple[tuple[str, int], ...] | None = None,
    ) -> None:
        super().__init__(parent)
        if compact:
            self.setObjectName("pbrHud")
        self._pill = AccentPill(self, radius=11.0 if compact else 12.0)
        self._pill.lower()
        self._drag = False
        self._mode = 0
        self._committed = 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        self._modes: list[int] = []
        items = modes if modes is not None else PBR_MODES
        for i, (label, mode) in enumerate(items):
            mid = int(mode) if isinstance(mode, int) else i
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if mid == 0:
                btn.setChecked(True)
                self._mode = mid
                self._committed = mid
            if compact:
                btn.setFixedHeight(30)  # #segBtn 4px pad + 12px glyphs + descenders
            self._group.addButton(btn, mid)
            btn.installEventFilter(self)
            lay.addWidget(btn)
            self._buttons.append(btn)
            self._modes.append(mid)
        attach_hover_bubble(self, self._buttons, radius=11.0 if compact else 12.0, pad=1)
        # scrub handles commit — idClicked would fire mid-drag
        QTimer.singleShot(0, self._sync_pill)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        # Compact PBR HUD floats at top — same capsule language as bottom nav.
        paint_glass_chip(self, radius=22.0 if self.objectName() == "pbrHud" else 16.0)

    def eventFilter(self, obj, event) -> bool:
        if obj in self._buttons:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                ctl = getattr(self, "_hover_ctl", None)
                if ctl is not None:
                    ctl.hide_now()
                self._drag = True
                self.grabMouse()
                local = obj.mapTo(self, event.position().toPoint())
                self._scrub_to_x(local.x(), commit=False)
                return True
            if et == QEvent.Type.MouseButtonRelease and self._drag:
                return True  # release handled on self after grab
        return super().eventFilter(obj, event)

    def _mode_at_x(self, x: int) -> int:
        for b, m in zip(self._buttons, self._modes):
            if b.geometry().left() <= x <= b.geometry().right():
                return m
        best, best_d = self._modes[0], 1e9
        for b, m in zip(self._buttons, self._modes):
            d = abs(b.geometry().center().x() - x)
            if d < best_d:
                best_d, best = d, m
        return best

    def _scrub_to_x(self, x: int, *, commit: bool) -> None:
        mode = self._mode_at_x(x)
        if commit:
            self._apply_mode(mode, animate=True, emit=True, commit=True, pop=True)
            return
        # live: pill tracks finger — no setChecked (avoids style stutter)
        self._mode = mode
        stop_slide(self._pill)
        rects = [b.geometry().adjusted(-1, -1, 1, 1) for b in self._buttons]
        self._pill.setGeometry(lerp_pill_rects(rects, float(x)))
        stack_selector_chrome(self, self._buttons)

    def _apply_mode(
        self, mode: int, *, animate: bool, emit: bool, commit: bool, pop: bool = False
    ) -> None:
        if mode not in self._modes:
            mode = self._modes[0] if self._modes else 0
        self._mode = mode
        for b, m in zip(self._buttons, self._modes):
            b.blockSignals(True)
            b.setChecked(m == mode)
            b.blockSignals(False)
        self._sync_pill(animate=animate, pop=pop and commit)
        if commit:
            changed = mode != self._committed
            self._committed = mode
            if emit and changed:
                self.mode_changed.emit(mode)

    def set_mode(self, mode: int) -> None:
        self._apply_mode(int(mode), animate=True, emit=False, commit=True, pop=False)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            ctl = getattr(self, "_hover_ctl", None)
            if ctl is not None:
                ctl.hide_now()
            self._drag = True
            self.grabMouse()
            self._scrub_to_x(int(event.position().x()), commit=False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag:
            self._scrub_to_x(int(event.position().x()), commit=False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag and event.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.releaseMouse()
            self._scrub_to_x(int(event.position().x()), commit=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_pill(self, animate: bool = False, *, pop: bool = False) -> None:
        btn = self._group.checkedButton()
        if btn is None:
            return
        r = btn.geometry().adjusted(-1, -1, 1, 1)
        if animate and self._pill.isVisible() and self._pill.width() > 4:
            anim = slide_to(self._pill, r)
            if pop:
                anim.finished.connect(lambda: apple_pop_pill(self._pill))
        else:
            stop_slide(self._pill)
            self._pill.setGeometry(r)
            if pop:
                QTimer.singleShot(0, lambda: apple_pop_pill(self._pill))
        stack_selector_chrome(self, self._buttons)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_pill(animate=False)


class SideTabStrip(QFrame):
    """Sidebar Scene|Mat|Lamps|… — spring scrub, wheel blocked, Apple pop on commit."""

    index_changed = Signal(int)

    def __init__(self, labels: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideTabStrip")
        self.setFixedHeight(44)
        self._pill = AccentPill(self, radius=11.0)
        self._pill.lower()
        self._drag = False
        self._index = 0
        self._committed = 0
        self._drag_rects: list = []
        self._scrub_x = 0.0
        self._scrub_target = 0.0
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setInterval(8)
        self._scrub_timer.timeout.connect(self._tick_scrub)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setObjectName("sideTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0:
                btn.setChecked(True)
            self._group.addButton(btn, i)
            btn.installEventFilter(self)
            lay.addWidget(btn, 1)
            self._buttons.append(btn)
        attach_hover_bubble(self, self._buttons, radius=11.0, pad=1)
        QTimer.singleShot(0, lambda: self._sync_pill(False))

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Never change sidebar page via wheel — it desyncs the viewer/stack.
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        if obj in self._buttons:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                local = obj.mapTo(self, event.position().toPoint())
                self._begin_scrub(local.x())
                return True
            if et == QEvent.Type.MouseButtonRelease and self._drag:
                return True
            if et == QEvent.Type.Wheel:
                return True  # block wheel on tab buttons too
        return super().eventFilter(obj, event)

    def set_index(self, index: int, *, animate: bool = True, emit: bool = False) -> None:
        self._apply_index(int(index), animate=animate, emit=emit, commit=True, pop=False)

    def set_tab_enabled(self, index: int, enabled: bool, *, tip: str = "") -> None:
        """Enable/disable a tab (e.g. Editor when file is view-only)."""
        if index < 0 or index >= len(self._buttons):
            return
        btn = self._buttons[index]
        btn.setEnabled(bool(enabled))
        if tip:
            from .motion import attach_glass_tip

            attach_glass_tip(btn, tip, highlight=True)
        if not enabled and self._committed == index:
            # Fall back to first enabled tab.
            for i, b in enumerate(self._buttons):
                if b.isEnabled():
                    self._apply_index(i, animate=True, emit=True, commit=True, pop=False)
                    break
        elif not self._drag:
            self._sync_pill(False)

    def current_index(self) -> int:
        return self._committed

    def _stack_pill(self) -> None:
        self._pill.show()
        stack_selector_chrome(self, self._buttons)

    def _snapshot_rects(self) -> list:
        return [b.geometry().adjusted(-1, -1, 1, 1) for b in self._buttons]

    def _nearest_enabled_index(self, x: float) -> int:
        rects = self._drag_rects or self._snapshot_rects()
        if not rects:
            return 0
        best_i, best_d = 0, 1e18
        for i, r in enumerate(rects):
            if i < len(self._buttons) and not self._buttons[i].isEnabled():
                continue
            d = abs(float(r.center().x()) - float(x))
            if d < best_d:
                best_d, best_i = d, i
        if best_i < len(self._buttons) and not self._buttons[best_i].isEnabled():
            for i, b in enumerate(self._buttons):
                if b.isEnabled():
                    return i
            return 0
        return best_i

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

    def _apply_index(
        self,
        index: int,
        *,
        animate: bool,
        emit: bool,
        commit: bool,
        pop: bool,
    ) -> None:
        if not self._buttons:
            return
        index = max(0, min(len(self._buttons) - 1, int(index)))
        if not self._buttons[index].isEnabled():
            index = self._nearest_enabled_index(
                float(self._buttons[index].geometry().center().x())
            )
        self._index = index
        for i, b in enumerate(self._buttons):
            b.blockSignals(True)
            b.setChecked(i == index)
            b.blockSignals(False)
        self._sync_pill(animate, pop=pop and commit)
        if commit:
            changed = index != self._committed
            self._committed = index
            if emit and changed:
                self.index_changed.emit(index)

    def _sync_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        btn = self._group.checkedButton() or self._buttons[0]
        r = btn.geometry().adjusted(-1, -1, 1, 1)
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_scrub(int(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag:
            self._scrub_target = float(event.position().x())
            if not self._scrub_timer.isActive():
                self._scrub_timer.start()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag and event.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.releaseMouse()
            x = float(event.position().x())
            idx = self._nearest_enabled_index(x)
            self._scrub_timer.stop()
            self._drag_rects = []
            self._apply_index(idx, animate=True, emit=True, commit=True, pop=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._drag:
            self._sync_pill(False)


class MeshInfoSection(QFrame):
    """Collapsible Mesh Info — lives inside #sideScroll with the tab page."""

    expanded_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("meshInfoSection")
        self._expanded = True
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._toggle = QPushButton("▾  Mesh Info")
        self._toggle.setObjectName("meshInfoToggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle)
        root.addWidget(self._toggle)

        self._body = QFrame()
        self._body.setObjectName("meshInfoBody")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(0)
        root.addWidget(self._body)

    def set_content(self, widget: QWidget) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._body_lay.addWidget(widget)

    def _on_toggle(self, checked: bool) -> None:
        self.set_expanded(bool(checked), animate=True)

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        self._expanded = expanded
        self._toggle.setChecked(expanded)
        self._toggle.setText(("▾  Mesh Info" if expanded else "▸  Mesh Info"))
        body = self._body

        def _tick(*_a) -> None:
            self.expanded_changed.emit()

        def _done_expand() -> None:
            body.setMaximumHeight(16777215)
            _tick()

        def _done_collapse() -> None:
            body.setVisible(False)
            _tick()

        if expanded:
            body.setVisible(True)
            body.setMaximumHeight(16777215)
            hint = max(body.sizeHint().height(), 1)
            body.setMaximumHeight(0)
            if animate:
                anim = animate_max_height(body, hint, 260, on_done=_done_expand)
                anim.valueChanged.connect(_tick)
            else:
                body.setMaximumHeight(16777215)
                _tick()
            return
        # collapse
        cur = body.height() if body.isVisible() else 0
        body.setMaximumHeight(max(cur, 1))
        if animate:
            anim = animate_max_height(body, 0, 220, on_done=_done_collapse)
            anim.valueChanged.connect(_tick)
        else:
            body.setMaximumHeight(0)
            body.setVisible(False)
            _tick()


class GlassProgressBar(QWidget):
    """Orange rounded load bar — shallow groove + lit chunk (not flat QSS)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("glassLoadBar")
        self._value = 0
        self.setFixedHeight(16)
        self.setMinimumWidth(180)

    def setValue(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        self.update()

    def value(self) -> int:
        return self._value

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(self.rect()).adjusted(1.0, 3.0, -1.0, -3.0)
        radius = track.height() * 0.5

        # inset groove
        groove = QPainterPath()
        groove.addRoundedRect(track, radius, radius)
        gfill = QLinearGradient(track.topLeft(), track.bottomLeft())
        gfill.setColorAt(0.0, QColor(0, 0, 0, 110))
        gfill.setColorAt(0.55, QColor(255, 255, 255, 18))
        gfill.setColorAt(1.0, QColor(255, 255, 255, 28))
        p.fillPath(groove, gfill)
        p.setPen(QPen(QColor(0, 0, 0, 70), 1.0))
        p.drawPath(groove)

        if self._value <= 0:
            return

        # ponytail: min width so round pill still reads at 1–8%
        fill_w = max(track.height(), track.width() * (self._value / 100.0))
        fill_w = min(fill_w, track.width())
        chunk = QRectF(track.x(), track.y(), fill_w, track.height())
        cpath = QPainterPath()
        cpath.addRoundedRect(chunk, radius, radius)

        body = QLinearGradient(chunk.topLeft(), chunk.bottomLeft())
        body.setColorAt(0.0, QColor("#ffc09a"))
        body.setColorAt(0.28, QColor("#ff7a45"))
        body.setColorAt(0.62, QColor("#ff5a1f"))
        body.setColorAt(1.0, QColor("#c43a10"))
        p.fillPath(cpath, body)

        # soft top specular
        sheen = QRectF(chunk.x() + 2, chunk.y() + 1, max(0.0, chunk.width() - 4), chunk.height() * 0.42)
        spath = QPainterPath()
        spath.addRoundedRect(sheen, sheen.height(), sheen.height())
        p.fillPath(spath, QColor(255, 255, 255, 70))

        # warm rim
        p.setPen(QPen(QColor(255, 140, 70, 160), 1.0))
        p.drawPath(cpath)


class LoadingOverlay(QWidget):
    """Full-window frosted glass overlay — blurred backdrop + brand card."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()
        self._frost: QPixmap | None = None

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("loadingCard")
        card.setFixedWidth(380)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 30, 32, 28)
        card_lay.setSpacing(12)

        self.logo = QLabel()
        self.logo.setObjectName("sideLogo")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setPixmap(_logo_pixmap(140))

        self.brand = QLabel("Trainz Studio")
        self.brand.setObjectName("overlayBrand")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stage = QLabel("Opening file…")
        self.stage.setObjectName("overlayStage")
        self.stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage.setWordWrap(True)

        self.pct = QLabel("")
        self.pct.setObjectName("overlayPct")
        self.pct.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bar = GlassProgressBar()

        card_lay.addWidget(self.logo)
        card_lay.addWidget(self.brand)
        card_lay.addSpacing(4)
        card_lay.addWidget(self.bar)
        card_lay.addWidget(self.pct)
        card_lay.addWidget(self.stage)
        root.addWidget(card)
        self._card = card

    def set_brand(self, text: str) -> None:
        self.brand.setText(text)

    def set_frost(self, pm: QPixmap | None) -> None:
        self._frost = pm
        self.update()

    def set_stage(self, text: str, pct: int | None = None) -> None:
        self.stage.setText(text)
        if pct is None:
            return
        pct = max(0, min(100, int(pct)))
        self.bar.setValue(pct)
        self.pct.setText(f"{pct}%")

    def paintEvent(self, event) -> None:  # noqa: ARG002
        # Real glass: blurred snapshot of UI under overlay + dim veil (not flat tint).
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._frost is not None and not self._frost.isNull():
            p.drawPixmap(self.rect(), self._frost)
        else:
            p.fillRect(self.rect(), QColor(12, 14, 18, 230))

        veil = QRadialGradient(
            self.rect().center(),
            max(self.width(), self.height()) * 0.72,
        )
        veil.setColorAt(0.0, QColor(18, 22, 26, 90))
        veil.setColorAt(0.55, QColor(11, 13, 15, 130))
        veil.setColorAt(1.0, QColor(8, 10, 12, 170))
        p.fillRect(self.rect(), veil)

        # soft glass bloom behind card
        if hasattr(self, "_card") and self._card is not None:
            cr = self._card.geometry()
            bloom = QRectF(cr).adjusted(-18, -14, 18, 22)
            glow = QRadialGradient(bloom.center(), bloom.width() * 0.55)
            glow.setColorAt(0.0, QColor(255, 90, 31, 36))
            glow.setColorAt(0.45, QColor(255, 90, 31, 14))
            glow.setColorAt(1.0, QColor(255, 90, 31, 0))
            p.fillRect(bloom, glow)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())


class BottomNav(QFrame):
    """Floating capsule: pages L/R · Home center (Theme is top-bar menu)."""

    page_changed = Signal(str)  # preview | meshes | attachs | settings

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        from .float_chrome import (
            bind_split_wells,
            hit_page_cluster,
            make_home_button,
            mount_center_icon_nav,
            paint_float_nav,
            prepare_float_nav,
        )

        prepare_float_nav(self)
        self._paint_float = paint_float_nav
        self._hit_page = hit_page_cluster
        self._pill = AccentPill(self, radius=14.0)
        self._pill.lower()
        self._drag = False
        self._page = "preview"
        self._committed = "preview"
        self._drag_rects: list = []
        self._scrub_x = 0.0
        self._scrub_target = 0.0
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setInterval(8)  # ~120 Hz spring
        self._scrub_timer.timeout.connect(self._tick_scrub)

        lay = QHBoxLayout(self)

        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("navBtn")
        self.preview_btn.setCheckable(True)
        self.preview_btn.setChecked(True)
        self.preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Editor modes flank Home: Meshes on the left, Attachs on the right.
        self.meshes_btn = QPushButton("Meshes Editor")
        self.meshes_btn.setObjectName("navBtn")
        self.meshes_btn.setCheckable(True)
        self.meshes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.meshes_btn.setToolTip("Materials, textures, and colors")

        self.attachs_btn = QPushButton("Attachs Editor")
        self.attachs_btn.setObjectName("navBtn")
        self.attachs_btn.setCheckable(True)
        self.attachs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attachs_btn.setToolTip("Attachment points (a.*)")

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("navBtn")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.home_btn = make_home_button(self)
        self.theme_btn = None  # Theme lives in top FloatTitleBar → Theme menu

        # Order is the split: Preview+Meshes | Home | Attachs+Settings.
        self._nav_btns = (
            self.preview_btn,
            self.meshes_btn,
            self.attachs_btn,
            self.settings_btn,
        )
        self._pages = ("preview", "meshes", "attachs", "settings")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        measure = self.meshes_btn.font()
        measure.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(measure)
        # navBtn padding is 18+18; lock one width so the scrub pill never reflows.
        nav_w = max(fm.horizontalAdvance(b.text()) for b in self._nav_btns) + 48
        nav_w = max(nav_w, 108)
        for i, b in enumerate(self._nav_btns):
            self._group.addButton(b, i)
            b.setAutoExclusive(True)
            b.setFixedWidth(nav_w)
            b.installEventFilter(self)

        left, right = mount_center_icon_nav(
            lay,
            home_btn=self.home_btn,
            page_btns=self._nav_btns,
        )
        self._left_btns = left
        self._right_btns = right
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

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        self._paint_float(self)

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
        stack_selector_chrome(self, [*self._nav_btns, self.home_btn])

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
        # start from current pill center so first frame doesn't jump
        self._scrub_x = float(self._pill.geometry().center().x()) if self._pill.width() > 8 else float(x)
        self._scrub_target = float(x)
        self._stack_pill()
        self.grabMouse()
        if not self._scrub_timer.isActive():
            self._scrub_timer.start()
        self._tick_scrub()

    def _tick_scrub(self) -> None:
        if not self._drag_rects:
            return
        # exponential ease toward finger — smooth even with sparse mouse events
        self._scrub_x += (self._scrub_target - self._scrub_x) * SCRUB_LERP
        if abs(self._scrub_target - self._scrub_x) < 0.4:
            self._scrub_x = self._scrub_target
        self._pill.setGeometry(lerp_pill_rects(self._drag_rects, self._scrub_x))
        if not self._drag and abs(self._scrub_target - self._scrub_x) < 0.4:
            self._scrub_timer.stop()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            # Translucent float chrome can swallow child presses — fire Home here.
            if self.home_btn.geometry().contains(pt):
                self.home_btn.click()
                event.accept()
                return
            # Scrub only on left/right page labels — not the center Home island.
            if not self._hit_page(self._nav_btns, pt):
                super().mousePressEvent(event)
                return
            self._begin_scrub(int(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag:
            self._scrub_target = float(event.position().x())
            if not self._scrub_timer.isActive():
                self._scrub_timer.start()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag and event.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.releaseMouse()
            x = float(event.position().x())
            self._scrub_target = x
            # settle onto nearest button center, then commit with slide
            page = self._page_at_x(x)
            idx = self._pages.index(page)
            if self._drag_rects:
                self._scrub_target = float(self._drag_rects[idx].center().x())
                self._scrub_x = self._scrub_target  # land immediately; slide_to does the polish
            self._scrub_timer.stop()
            self._drag_rects = []
            self._apply_page(page, animate=True, emit=True, commit=True, pop=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_page(
        self, page: str, *, animate: bool, emit: bool, commit: bool, pop: bool = False
    ) -> None:
        if page not in self._pages:
            page = "preview"
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

    def set_page(self, page: str, *, animate: bool = True, emit: bool = False) -> None:
        self._apply_page(page, animate=animate, emit=emit, commit=True, pop=False)

    def _sync_pill(self, animate: bool = True, *, pop: bool = False) -> None:
        btn = next((b for b in self._nav_btns if b.isChecked()), self.preview_btn)
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

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        hint = max(self.sizeHint().width(), 400)
        w = min(hint, max(260, parent.width() - 24))
        self.setFixedWidth(w)
        x = (parent.width() - w) // 2
        y = parent.height() - self.height() - 18
        self.move(max(10, x), max(10, y))
        self.show()
        self.raise_()
        self._sync_pill(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._drag:
            self._sync_pill(False)


class BakeProgressBar(QFrame):
    """Glass strip at bottom-nav position — % + ETA while lamp bake runs."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("bakeNav")
        self.setFixedHeight(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)
        self._stage = QLabel("Bake")
        self._stage.setObjectName("bakeStage")
        self._eta = QLabel("")
        self._eta.setObjectName("mutedTip")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self._pct = QLabel("0%")
        self._pct.setFixedWidth(40)
        from .icons import apply_icon

        self._cancel = QPushButton()
        apply_icon(self._cancel, "close", tip="Cancel", kind="icon", size=18, square=32)
        self._cancel.clicked.connect(self.cancel_requested.emit)
        lay.addWidget(self._stage, 0)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self._pct, 0)
        lay.addWidget(self._eta, 0)
        lay.addWidget(self._cancel, 0)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        paint_glass_chip(self, radius=30.0)

    def set_progress(self, stage: str, pct: int, eta_sec: float) -> None:
        self._stage.setText(stage)
        pct = max(0, min(100, int(pct)))
        self.bar.setValue(pct)
        self._pct.setText(f"{pct}%")
        if eta_sec > 0.5:
            m, s = divmod(int(eta_sec + 0.5), 60)
            self._eta.setText(f"ETA {m}:{s:02d}" if m else f"ETA {s}s")
        else:
            self._eta.setText("")

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        w = max(min(parent.width() - 24, 720), 220)
        self.setFixedWidth(w)
        x = (parent.width() - w) // 2
        y = parent.height() - self.height() - 20
        self.move(max(8, x), max(8, y))
        self.show()
        self.raise_()


class BakeWorker(QThread):
    progress = Signal(str, int, float)  # stage, pct, eta_sec
    finished_ok = Signal(object)  # BakeResult
    failed = Signal(str)

    def __init__(
        self,
        scene: Scene,
        lamps: list,
        out_dir: Path,
        settings: BakeSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.scene = scene
        self.lamps = lamps
        self.out_dir = out_dir
        self.settings = settings
        self._cancel = [False]

    def cancel(self) -> None:
        self._cancel[0] = True

    def run(self) -> None:
        try:
            from ..lamps.bake import bake_lamps_to_textures

            def on_prog(stage: str, done: int, total: int, eta: float) -> None:
                self.progress.emit(stage, done, eta)

            result = bake_lamps_to_textures(
                self.scene,
                self.lamps,
                self.out_dir,
                settings=self.settings,
                on_progress=on_prog,
                cancel_flag=self._cancel,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


SIDE_TABLE_ROWS = 10
_SIDE_ROW_FALLBACK = 34  # matches theme item min-height + padding

# Scene "Meshes in scene" — same column language as Assets Mesh Ops (LOD|Width|Mesh file)
_MESH_COL_SHOW, _MESH_COL_FACES, _MESH_COL_NAME = 0, 1, 2

# Re-export: Mesh side tables share Studio-wide damped scroll.
from .smooth_scroll import DampedScrollFilter as _DampedScrollFilter  # noqa: E402
from .smooth_scroll import enable_smooth_scroll, enable_smooth_table  # noqa: E402


def _side_table_band_height(
    view: QAbstractItemView, rows: int = SIDE_TABLE_ROWS
) -> int:
    """Viewport tall enough for `rows` items (+ tree/table header if any)."""
    row = 0
    if isinstance(view, QListWidget) and view.count() > 0:
        row = int(view.sizeHintForRow(0))
    elif isinstance(view, QTreeWidget) and view.topLevelItemCount() > 0:
        row = int(view.sizeHintForRow(0))
    elif isinstance(view, QTableWidget) and view.rowCount() > 0:
        row = int(view.rowHeight(0) or view.sizeHintForRow(0))
    if row <= 0:
        row = _SIDE_ROW_FALLBACK
    frame = 2 * view.frameWidth() + 8
    header = 0
    if isinstance(view, QTreeWidget) and not view.isHeaderHidden():
        hh = view.header().height()
        if hh <= 0:
            hh = view.header().sizeHint().height()
        header = max(int(hh), 28)
    elif isinstance(view, QTableWidget) and not view.horizontalHeader().isHidden():
        hh = view.horizontalHeader().height()
        if hh <= 0:
            hh = view.horizontalHeader().sizeHint().height()
        header = max(int(hh), 28)
    return header + rows * row + frame


def _enable_side_table_scroll(
    view: QAbstractItemView, *, rows: int = SIDE_TABLE_ROWS
) -> None:
    """Show ~`rows` items; wheel scrolls with Studio-wide damped inertia."""
    enable_smooth_scroll(view)
    bar = view.verticalScrollBar()
    bar.setPageStep(max(40, rows * 8))
    h = _side_table_band_height(view, rows)
    view.setMinimumHeight(h)
    view.setMaximumHeight(h)
    view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _refit_side_table(view: QAbstractItemView, *, rows: int = SIDE_TABLE_ROWS) -> None:
    """Recompute 10-row band after items land (sizeHint becomes real)."""
    h = _side_table_band_height(view, rows)
    view.setMinimumHeight(h)
    view.setMaximumHeight(h)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MSTN Trainz Studio")
        self.resize(1280, 780)
        self.setAcceptDrops(True)
        self._studio_mode = "home"  # home | mesh | sounds | engine | assets | texmesh
        self._chrome_ready = False  # Mesh Editor/sidebar/settings/chrome
        self._sounds_ready = False
        self._engine_ready = False
        self._assets_ready = False
        self._assets_host = None
        self._scene = Scene()
        self._mesh_folder: Path | None = None
        self._mesh_path: Path | None = None
        self._mesh_paths: list[Path] = []
        self._hidden_mesh_keys: set[str] = set()
        self._mesh_hl: tuple[str, frozenset[str]] | None = None
        self._suppress_mesh_hl = 0
        self.view = None
        self.editor = None  # type: ignore[assignment]
        self._sounds_host = None
        self._engine_host = None
        self._side_panel = None
        self._settings_panel = None
        self._chrome_layer = None
        self.pbr_hud = None
        self._nav = None
        self._im_doc = None  # lib.im_editor.core.ImDocument when kind==im
        self._tzmf_bytes: bytearray | None = None  # live .trainzmesh edit buffer
        self._tzmf_dirty = False
        self._two_sided_pending: dict[str, bool] = {}
        self._tzmf_mats_cache: list = []
        self._editor_populated_key: str = ""
        self._history = UndoStack()
        self._project_path: Path | None = None
        self._pending_project: ProjectState | None = None
        self._autosave_pending = False  # set only when edits land; cleared after write
        self._mat_preview_timer = QTimer(self)
        self._mat_preview_timer.setSingleShot(True)
        self._mat_preview_timer.setInterval(80)
        self._mat_preview_timer.timeout.connect(self._flush_mat_preview)
        self._crash_timer = QTimer(self)
        self._crash_timer.setInterval(60_000)  # 1 min — only writes if _autosave_pending
        self._crash_timer.timeout.connect(self._autosave_tick)
        self._crash_timer.start()
        self._undo_act: QAction | None = None
        self._redo_act: QAction | None = None
        self._lamps: list[Lamp] = []
        self._lamp_block = False
        self._worker: LoadWorker | None = None
        self._bake_worker: BakeWorker | None = None
        self._busy = False
        self._bake_busy = False
        self._anim_playing = False
        self._anim_clip: AnimClip | None = None
        self._theme_mode = "dark"
        self._tex_mode = "all"  # all | selected
        self._applying_filter = False
        self._debug_mode = 0
        self._shading_mode = SHADING_RENDERED
        self._att_edit_mode = ATT_EDIT_VIEW  # Editor default: look only
        self._flip_texture_v = False  # Trainz/D3D: V=0 = top; do not flip PIL upload
        self._show_axes = True
        self._show_grid = True
        self._show_atts = True
        self._show_corner_gizmo = True
        self._show_fps = False
        self._face_orient = False  # Blender Face Orientation (Scene tab)
        self._sun_mode = False
        self._emissive_boost = 0.15
        self._editor_tex_stems: set[str] = set()
        self._pbr_controls: list[SegmentedControl] = []
        self._view_acts: dict[str, QAction] = {}
        self._stat_labels: dict[str, QLabel] = {}
        self._tab_pie: ModePie | None = None
        self._tab_pie_armed = False
        self._tab_pie_sticky = False
        self._tab_pie_t0 = 0.0
        self._shading_pie = None
        self._edit_pie = None
        self._pending_sound_paths: list[Path] = []

        # HOME only — Mesh chrome / Sounds assemble after first paint.
        install_frameless(self)
        self._build_home_shell()
        self._build_menu()
        self._install_title_bar()
        apply_theme(self, self._theme_mode)
        # Freeze English sources + apply persisted language (no anim on boot).
        from .i18n import apply_language_font, snapshot_and_apply, t

        apply_language_font()
        snapshot_and_apply(self)
        if hasattr(self._home_page, "retranslate"):
            self._home_page.retranslate()
        self._status.showMessage(t("MSTN Trainz Studio"))
        self._overlay = LoadingOverlay(self)
        self._overlay.hide()
        self._hub_reveal = HubRevealOverlay(self)
        self._hub_reveal.hide()
        self._theme_busy = False
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._tick_anim)

    # ── widgets ──────────────────────────────────────────────

    def _build_widgets(self) -> None:
        self.att_list = QListWidget()
        self.mesh_list = QTableWidget(0, 3)
        self.mesh_list.setObjectName("studioTable")
        self.mesh_list.setHorizontalHeaderLabels(["Show", "Faces", "Mesh file"])
        self.mesh_list.horizontalHeader().setStretchLastSection(True)
        self.mesh_list.setColumnWidth(_MESH_COL_SHOW, 48)
        self.mesh_list.setColumnWidth(_MESH_COL_FACES, 72)
        self.mesh_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mesh_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.mesh_list.verticalHeader().setVisible(False)
        self.mesh_list.setShowGrid(False)
        enable_smooth_table(self.mesh_list)
        _enable_side_table_scroll(self.mesh_list)
        self.mesh_list.setToolTip(
            "Loaded meshes — tick Show to draw (multi-select ok). "
            "Drop/Open adds more; Clear empties the preview."
        )
        self._hidden_mesh_keys: set[str] = set()
        _enable_side_table_scroll(self.att_list)
        # Scene-tab material list (Editor ↔ left link); not the multi-file mesh_list
        self.scene_mesh_list = QListWidget()
        self.scene_mesh_list.setUniformItemSizes(True)
        _enable_side_table_scroll(self.scene_mesh_list)
        self.scene_mesh_list.setToolTip(
            "Tick rows, then Apply Double Sided. Click a name to edit it on the right."
        )
        self.scene_mesh_list.hide()
        self._mesh_ds_bar = QWidget()
        ds_lay = QVBoxLayout(self._mesh_ds_bar)
        ds_lay.setContentsMargins(0, 2, 0, 0)
        ds_lay.setSpacing(4)
        self._mesh_ds_all = QCheckBox("Select all")
        self._mesh_ds_all.setToolTip("Tick every mesh in this list")
        self._mesh_ds_apply = QPushButton("Apply Double Sided (0)")
        self._mesh_ds_apply.setEnabled(False)
        self._mesh_ds_apply.setToolTip(
            "Turn Double Sided on for every ticked mesh. Preview updates now; camera stays."
        )
        ds_lay.addWidget(self._mesh_ds_all)
        ds_lay.addWidget(self._mesh_ds_apply)
        self._mesh_ds_bar.hide()
        self._scene_list_mode = "atts"  # atts | meshes
        self._face_orient_cb = QCheckBox("Face Orientation")
        self._face_orient_cb.setChecked(False)
        self._face_orient_cb.setToolTip(
            "Blender-style: blue = front face, red = back face (triangle winding). "
            "Trainz culls / shades by facing — red outside usually means flipped normals."
        )
        self._mesh_remove_btn = QPushButton("Remove selected mesh")
        self._mesh_clear_btn = QPushButton("Clear meshes")
        self._mesh_clear_btn.setToolTip("Unload every mesh so you can open a fresh preview")
        self.tex_tree = QTreeWidget()
        self.tex_tree.setObjectName("matTable")
        self.tex_tree.setColumnCount(3)
        self.tex_tree.setHeaderLabels(["Material", "Maps", "Status"])
        self.tex_tree.setHeaderHidden(False)
        self.tex_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tex_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tex_tree.setAnimated(False)
        self.tex_tree.setIndentation(12)
        self.tex_tree.setRootIsDecorated(True)
        self.tex_tree.setItemsExpandable(True)
        self.tex_tree.setExpandsOnDoubleClick(True)
        self.tex_tree.setUniformRowHeights(True)
        self.tex_tree.setAlternatingRowColors(True)
        self.tex_tree.setAllColumnsShowFocus(True)
        self.tex_tree.setSortingEnabled(False)
        _enable_side_table_scroll(self.tex_tree)
        hdr = self.tex_tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, hdr.ResizeMode.ResizeToContents)
        self.anim_list = QListWidget()
        self.anim_list.setAcceptDrops(True)
        _enable_side_table_scroll(self.anim_list)

        self.tex_detail = QLabel("")
        self.tex_detail.setWordWrap(True)
        self.tex_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.tex_detail.setObjectName("mutedTip")

        self.tex_mode_combo = QComboBox()
        self.tex_mode_combo.addItem("All materials", "all")
        self.tex_mode_combo.addItem("Selected only", "selected")

        self._anim_empty = QLabel("No .kin beside this mesh")
        self._anim_empty.setObjectName("mutedTip")
        self._anim_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._play_btn = QPushButton("Play")
        self._frame_slider = QSlider(Qt.Orientation.Horizontal)
        self._frame_slider.setMinimum(0)
        self._frame_slider.setMaximum(DUMMY_FRAMES)

        self._light_checks: list[QCheckBox] = []
        for label in ("Left", "Right", "Front", "Back", "Top fill"):
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._light_checks.append(cb)

        self._sun_mode_cb = QCheckBox("Sun mode")
        self._sun_mode_cb.setToolTip("One directional sun (+ soft fill) instead of L/R/F/B array")
        self._sun_mode_cb.setChecked(True)
        self._sun_az = QSlider(Qt.Orientation.Horizontal)
        self._sun_az.setRange(0, 360)
        self._sun_az.setValue(135)
        self._sun_el = QSlider(Qt.Orientation.Horizontal)
        self._sun_el.setRange(-10, 89)
        self._sun_el.setValue(45)
        self._sun_int = QSlider(Qt.Orientation.Horizontal)
        self._sun_int.setRange(20, 500)  # 0.2–5.0 ×100
        self._sun_int.setValue(140)
        self._sun_az_lab = QLabel("Azimuth 135°")
        self._sun_el_lab = QLabel("Elevation 45°")
        self._sun_int_lab = QLabel("Intensity 1.40")

        self._emis_slider = QSlider(Qt.Orientation.Horizontal)
        self._emis_slider.setRange(0, 200)  # 0–2.0 ×100
        self._emis_slider.setValue(15)
        self._emis_lab = QLabel("Emissive boost 0.15 (preview only)")
        self._emis_lab.setObjectName("mutedTip")

        self.lamp_tree = QTreeWidget()
        self.lamp_tree.setObjectName("lampTable")
        self.lamp_tree.setColumnCount(3)
        self.lamp_tree.setHeaderLabels(["Bulb / part", "Mesh", "Texture"])
        self.lamp_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.lamp_tree.setRootIsDecorated(False)
        self.lamp_tree.setUniformRowHeights(True)
        self.lamp_tree.setAlternatingRowColors(True)
        self.lamp_tree.setAllColumnsShowFocus(True)
        self.lamp_tree.setAnimated(False)
        _enable_side_table_scroll(self.lamp_tree)
        lamp_hdr = self.lamp_tree.header()
        lamp_hdr.setStretchLastSection(False)
        lamp_hdr.setSectionResizeMode(0, lamp_hdr.ResizeMode.Stretch)
        lamp_hdr.setSectionResizeMode(1, lamp_hdr.ResizeMode.ResizeToContents)
        lamp_hdr.setSectionResizeMode(2, lamp_hdr.ResizeMode.ResizeToContents)
        self._lamp_enabled = QCheckBox("Glow + cast (selected)")
        self._lamp_enabled.setChecked(False)
        self._lamp_enabled.setToolTip(
            "Off by default. On = texture self-illum (tube looks lit) + cast onto nearby mesh"
        )
        self._lamp_bright = QSlider(Qt.Orientation.Horizontal)
        self._lamp_bright.setRange(0, 800)  # 0–8.0
        self._lamp_bright.setValue(50)
        self._lamp_bright_lab = QLabel("Brightness 0.50")
        self._lamp_range = QSlider(Qt.Orientation.Horizontal)
        self._lamp_range.setRange(5, 3000)  # 0.05–30 m ×100
        self._lamp_range.setValue(30)
        self._lamp_range_lab = QLabel("Cast range 0.3 m")
        self._lamp_range.setToolTip("How far light from this texture reaches other mesh")
        self._lamp_mode = QComboBox()
        self._lamp_mode.addItem("Omni (bulb)", "omni")
        self._lamp_mode.addItem("Spot", "spot")
        self._lamp_mode.addItem("Wide", "wide")
        self._lamp_cone = QSlider(Qt.Orientation.Horizontal)
        self._lamp_cone.setRange(10, 80)
        self._lamp_cone.setValue(40)
        self._lamp_cone_lab = QLabel("Spot cone 40°")
        self._lamp_color_btn = QPushButton("Color")
        self._lamp_color_btn.setMinimumHeight(32)
        # fluorescent orange default
        self._lamp_color = QColor(255, 158, 56)
        self._moon_cb = QCheckBox("Moonlight (when Sun off)")
        self._moon_cb.setChecked(True)
        self._moon_cb.setToolTip("Soft cool fill — turn Sun off to see cabin glow clearly")
        self._moon_int = QSlider(Qt.Orientation.Horizontal)
        self._moon_int.setRange(5, 120)
        self._moon_int.setValue(45)
        self._moon_int_lab = QLabel("Moon 0.45")
        self._lamp_rescan_btn = QPushButton("Rescan onetex / lights")
        self._lamp_add_btn = QPushButton("Add from Mat selection")
        self._lamp_remove_btn = QPushButton("Remove selected")
        self._lamp_gizmo_cb = QCheckBox("Show lamp gizmos")
        self._lamp_gizmo_cb.setChecked(True)
        self._lamp_gizmo_cb.setToolTip(
            "Markers at bulb islands: gray cross = off, soft glow = Glow+cast on"
        )
        self._bake_quality = QComboBox()
        self._bake_quality.addItem("Draft (fast)", "draft")
        self._bake_quality.addItem("High (default)", "high")
        self._bake_quality.addItem("Production (clean)", "production")
        self._bake_quality.setCurrentIndex(1)
        # ponytail: cupy import is slow + noisy — probe after first paint
        self._bake_cuda_cb = QCheckBox("CUDA (CuPy)")
        self._bake_cuda_cb.setChecked(False)
        self._bake_cuda_cb.setEnabled(False)
        self._bake_cuda_cb.setToolTip("Probing CUDA after startup…")
        self._bake_btn = QPushButton("Bake lamps -> albedo + parameter")
        self._bake_btn.setObjectName("accentBtn")
        self._bake_btn.setToolTip(
            "Ray-traced bake into sidecars under baked_lamps/ (does not overwrite sources). "
            "Enable lamps in the list first (checkbox Glow + cast)."
        )

        self._scene_cap_tip = QLabel("")
        self._scene_cap_tip.setObjectName("mutedTip")
        self._scene_cap_tip.setWordWrap(True)

        from .icons import apply_icon

        self._open_btn = QPushButton()
        apply_icon(
            self._open_btn,
            "file_open",
            tip="Open mesh / texture / .kin…",
            kind="accent",
            size=22,
            square=40,
        )
        self._folder_btn = QPushButton()
        apply_icon(
            self._folder_btn,
            "folder_open",
            tip="Check textures in folder…",
            kind="icon",
            size=20,
            square=40,
        )

    def _build_home_shell(self) -> None:
        """Minimal HOME UI — first paint before Mesh chrome / Sounds."""
        self._stack = QStackedWidget()
        self._hub = QStackedWidget()
        home_logo = QLabel()
        home_logo.setPixmap(_logo_pixmap(180, mode=self._theme_mode))
        self._home_logo = home_logo
        self._home_page = build_home_page(
            logo=home_logo,
            on_mesh=self.enter_mesh_studio,
            on_sounds=self.enter_sounds_studio,
            on_engine=self.enter_engine_tuner,
            on_assets=self.enter_assets_studio,
            on_texmesh=self.enter_texmesh_studio,
            on_drop=self._handle_dropped_paths,
            theme_mode=self._theme_mode,
        )
        self._hub.addWidget(self._home_page)  # HUB_HOME
        # Placeholders — swapped when chrome / sounds / engine / assets warm up
        self._mesh_hub_ph = QWidget()
        self._sounds_hub_ph = QWidget()
        self._engine_hub_ph = QWidget()
        self._assets_hub_ph = QWidget()
        self._hub.addWidget(self._mesh_hub_ph)  # HUB_MESH
        self._hub.addWidget(self._sounds_hub_ph)  # HUB_SOUNDS
        self._hub.addWidget(self._engine_hub_ph)  # HUB_ENGINE
        self._hub.addWidget(self._assets_hub_ph)  # HUB_ASSETS
        self._stack.addWidget(self._hub)  # STACK_HUB

        self._gl_host = QWidget()
        self._gl_host.setObjectName("glHost")
        self._gl_layout = QVBoxLayout(self._gl_host)
        self._gl_layout.setContentsMargins(0, 0, 0, 0)
        self._gl_placeholder = QLabel("3D view appears after you open a mesh.")
        self._gl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gl_placeholder.setObjectName("glPlaceholder")
        self._gl_layout.addWidget(self._gl_placeholder)
        self._stack.addWidget(self._gl_host)  # STACK_GL

        self._viewer_pane = QWidget()
        self._viewer_pane.setObjectName("viewerPane")
        self._stack.setParent(self._viewer_pane)

        self._center_host = QWidget()
        self._center_host.setObjectName("centerHost")
        center_lay = QVBoxLayout(self._center_host)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)
        center_lay.addWidget(self._viewer_pane, 1)

        self._editor_dock_open = False
        self._page = "preview"
        self._editor_mode = "meshes"
        self._side_open = True
        self._settings_open = False
        self._side_edge_btn = None
        self._editor_edge_btn = None
        self._bake_bar = None
        self._shortcut_bar = None

        shell = QWidget()
        shell.setObjectName("appShell")
        shell_lay = QVBoxLayout(shell)
        # Leave room under the floating title bar so logos/content never bleed through.
        shell_lay.setContentsMargins(0, TITLE_CONTENT_INSET, 0, 0)
        shell_lay.setSpacing(0)
        shell_lay.addWidget(self._center_host, 1)
        self.setCentralWidget(shell)
        # Initial geometry so HOME is centered before first resize/showEvent.
        self._layout_viewer_pane()

        from .status_toast import (
            StudioStatusBar,
            ToastHost,
            show_save_toast,
            show_status_log_dialog,
        )

        self._status = StudioStatusBar(self)
        self.setStatusBar(self._status)
        self._toasts = ToastHost(self)
        self._status.log_open_requested.connect(self._open_status_log)
        self._status.save_noticed.connect(self._on_save_noticed)
        self._status.progress_noticed.connect(self._on_progress_noticed)
        self._status.progress_cleared.connect(self._on_progress_cleared)
        self._ve_last_reports: list = []
        self._ve_worker: VeScanWorker | None = None
        self._ve_btn = QPushButton("VE")
        self._ve_btn.setObjectName("statusVeBtn")
        self._ve_btn.setFlat(True)
        self._ve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ve_btn.setToolTip("VE Rules — click to open last scan (Tools → VE Rules)")
        self._ve_btn.clicked.connect(self._ve_show_last)
        self._status.addPermanentWidget(self._ve_btn)
        foot = QLabel("Copyright MSTN Production")
        foot.setObjectName("mutedTip")
        self._status.addPermanentWidget(foot)
        # keep helpers bound for type checkers / hot paths
        self._show_save_toast = show_save_toast
        self._show_status_log_dialog = show_status_log_dialog

    def ensure_studio_chrome(self) -> None:
        """Build Mesh Editor / sidebar / settings / nav — once, after HOME paints."""
        if self._chrome_ready:
            return
        self._chrome_ready = True

        from .editor import EditorWorkspace

        self._build_widgets()
        # Swap Mesh hub placeholder → welcome
        welcome = self._build_welcome()
        old = self._hub.widget(HUB_MESH)
        self._hub.removeWidget(old)
        self._hub.insertWidget(HUB_MESH, welcome)
        if old is not None:
            old.deleteLater()
        self._mesh_hub_ph = None

        self.editor = EditorWorkspace()
        self._att_x = self.editor.att_x
        self._att_y = self.editor.att_y
        self._att_z = self.editor.att_z
        self._att_name = self.editor.att_name
        self._ed_att_list = self.editor.att_list
        _enable_side_table_scroll(self._ed_att_list)

        side = self._build_sidebar()
        side.setParent(self._center_host)
        self._side_panel = side

        self.editor.setParent(self._center_host)
        self.editor.setFixedWidth(EDITOR_DOCK_W)
        self.editor.hide()

        self._settings_panel = self._build_settings()
        self._settings_panel.setParent(self._center_host)
        self._settings_panel.hide()

        self._side_edge_btn = QToolButton(self._center_host)
        self._side_edge_btn.setObjectName("panelEdgeBtn")
        self._side_edge_btn.setFixedSize(PANEL_EDGE_W, 56)
        self._side_edge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._side_edge_btn.setToolTip("Collapse / expand left sidebar  ([)")
        self._side_edge_btn.clicked.connect(self._toggle_side_panel)
        self._editor_edge_btn = QToolButton(self._center_host)
        self._editor_edge_btn.setObjectName("panelEdgeBtn")
        self._editor_edge_btn.setFixedSize(PANEL_EDGE_W, 56)
        self._editor_edge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._editor_edge_btn.setToolTip("Collapse / expand right Editor  (])")
        self._editor_edge_btn.clicked.connect(self._toggle_editor_panel)

        self._chrome_layer = QWidget(self._center_host)
        self._chrome_layer.setObjectName("chromeLayer")
        self._chrome_layer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._chrome_layer.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        self._nav = BottomNav(self._chrome_layer)
        self._bake_bar = BakeProgressBar(self._chrome_layer)
        self._bake_bar.hide()
        self.pbr_hud = SegmentedControl(self._chrome_layer, compact=True)
        self._pbr_controls.append(self.pbr_hud)
        self.pbr_hud.hide()
        self._shortcut_bar = QLabel(
            "LMB Orbit   ·   MMB Pan L/R · U/D   ·   Wheel Dolly   ·   "
            "Ctrl+Wheel FOV (mm)   ·   Tab Shading pie   ·   "
            "[ ] Side panels   ·   ← ↑ ↓ → Walk   ·   R Reset   ·   F3 Frame stats",
            self._chrome_layer,
        )
        self._shortcut_bar.setObjectName("shortcutBar")
        self._shortcut_bar.setFixedHeight(26)  # 11px + pad — was 22, clipped descenders
        self._shortcut_bar.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._viewer_pane.installEventFilter(self)
        self._center_host.installEventFilter(self)

        host = self._center_host
        self._shading_pie = ShadingPie(host)
        self._shading_pie.hide()
        self._edit_pie = EditModePie(host)
        self._edit_pie.hide()
        self._shading_pie.dismissed.connect(lambda: self._commit_tab_pie(force=True))
        self._edit_pie.dismissed.connect(lambda: self._commit_tab_pie(force=True))

        self._wire()
        self._strip_sidebar_tab_focus()
        self._update_stats(None)
        self._apply_studio_chrome()
        # Chrome may assemble after a HOME theme toggle — sync glass/frost tint.
        self._retint_glass_chips()
        self._retint_frost_panels()
        # Boot batch: one snapshot_and_apply at end of warmup_hub_studios.
        if not getattr(self, "_boot_batch", False):
            from .i18n import snapshot_and_apply

            snapshot_and_apply(self)
        QTimer.singleShot(0, self._layout_side_panel)
        # Frost grab after first real GL frame — skip during boot batch.
        if not getattr(self, "_boot_batch", False):
            QTimer.singleShot(80, self._refresh_side_frost)
        QTimer.singleShot(0, self._probe_cuda_bake)
        QTimer.singleShot(0, self._strip_sidebar_tab_focus)

    def _ensure_sounds_host(self) -> None:
        if self._sounds_ready:
            return
        self._sounds_ready = True
        from .sounds import build_sounds_studio

        host = build_sounds_studio(
            on_home=self.go_home,
            on_theme=self._toggle_theme,
            theme_mode=self._theme_mode,
        )
        host.status.connect(self._status_from_sounds)
        _imp = host.import_paths

        def _import_and_ve(paths: list[Path]) -> None:
            _imp(paths)
            QTimer.singleShot(
                0, lambda ps=list(paths): self._ve_scan_auto([Path(p) for p in ps])
            )

        host.import_paths = _import_and_ve  # type: ignore[method-assign]
        old = self._hub.widget(HUB_SOUNDS)
        self._hub.removeWidget(old)
        self._hub.insertWidget(HUB_SOUNDS, host)
        if old is not None:
            old.deleteLater()
        self._sounds_host = host
        self._sounds_hub_ph = None
        if not getattr(self, "_boot_batch", False):
            from .i18n import snapshot_and_apply

            snapshot_and_apply(host)

    def _ensure_engine_host(self) -> None:
        if self._engine_ready:
            return
        self._engine_ready = True
        from .engine import build_engine_tuner

        host = build_engine_tuner(
            on_home=self.go_home,
            on_theme=self._toggle_theme,
            theme_mode=self._theme_mode,
        )
        host.status.connect(self._status_from_sounds)
        _open = host.open_file

        def _open_and_ve() -> bool:
            ok = _open()
            if ok:
                sp = getattr(getattr(host, "cfg", None), "source_path", None)
                if sp:
                    QTimer.singleShot(0, lambda p=Path(sp): self._ve_scan_auto([p]))
            return ok

        host.open_file = _open_and_ve  # type: ignore[method-assign]
        old = self._hub.widget(HUB_ENGINE)
        self._hub.removeWidget(old)
        self._hub.insertWidget(HUB_ENGINE, host)
        if old is not None:
            old.deleteLater()
        self._engine_host = host
        self._engine_hub_ph = None
        if not getattr(self, "_boot_batch", False):
            from .i18n import snapshot_and_apply

            snapshot_and_apply(host)

    def _ensure_assets_host(self) -> None:
        if self._assets_ready:
            return
        self._assets_ready = True
        from .assets import build_assets_studio

        host = build_assets_studio(
            on_home=self.go_home,
            on_theme=self._toggle_theme,
            theme_mode=self._theme_mode,
        )
        host.status.connect(self._status_from_sounds)
        host.enginespec_open.connect(self._on_packages_enginespec_open)
        host.mesh_open.connect(self._on_packages_mesh_open)
        old = self._hub.widget(HUB_ASSETS)
        self._hub.removeWidget(old)
        self._hub.insertWidget(HUB_ASSETS, host)
        if old is not None:
            old.deleteLater()
        self._assets_host = host
        self._assets_hub_ph = None
        if not getattr(self, "_boot_batch", False):
            from .i18n import snapshot_and_apply

            snapshot_and_apply(host)
            self._idle_warm_assets_preview()

    def _idle_warm_assets_preview(self) -> None:
        """Finder GL surface — after HOME is up (creating QOpenGLWidget at boot stalls)."""
        host = getattr(self, "_assets_host", None)
        if host is None:
            return
        try:
            host.packages_page.warm_fast_preview_infra()
        except Exception:
            pass

    def warmup_hub_studios(self, *, on_stage=None) -> None:
        """Precache Mesh / Sounds / Engine / Assets under the boot frost.

        ponytail: build once at boot so HOME card clicks only swap the stack —
        no first-click hitch from EditorWorkspace / Sounds / Engine imports.
        GL fast-preview warms idle after overlay hide (not under frost).
        """
        self._boot_batch = True
        try:
            if on_stage is not None:
                on_stage("Warming Mesh Studio…", 40)
            warm_logo_cache()
            self.ensure_studio_chrome()
            if on_stage is not None:
                on_stage("Warming Sounds Studio…", 60)
            self._ensure_sounds_host()
            if on_stage is not None:
                on_stage("Warming Engine Tuner…", 78)
            self._ensure_engine_host()
            if on_stage is not None:
                on_stage("Warming Assets Tools…", 92)
            self._ensure_assets_host()
        finally:
            self._boot_batch = False
        from .i18n import snapshot_and_apply

        snapshot_and_apply(self)
        # Assets Finder GL after HOME is interactive — studios themselves are warm.
        QTimer.singleShot(0, self._idle_warm_assets_preview)

    def hubs_are_warm(self) -> bool:
        return bool(
            self._chrome_ready
            and self._sounds_ready
            and self._engine_ready
            and self._assets_ready
        )

    def _build_stats_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("statsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        # Always listed when any mesh is loaded — Show ticks control viewport draw.
        self._mesh_list_block = QWidget()
        mlay = QVBoxLayout(self._mesh_list_block)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(6)
        mesh_title = QLabel("Meshes in scene")
        mesh_title.setStyleSheet("font-weight: 600;")
        mlay.addWidget(mesh_title)
        mlay.addWidget(self.mesh_list)
        mesh_btns = QHBoxLayout()
        mesh_btns.setContentsMargins(0, 0, 0, 0)
        mesh_btns.setSpacing(6)
        mesh_btns.addWidget(self._mesh_remove_btn, 1)
        mesh_btns.addWidget(self._mesh_clear_btn, 1)
        mlay.addLayout(mesh_btns)
        lay.addWidget(self._mesh_list_block)
        self._mesh_list_block.hide()

        detail_title = QLabel("Mesh detail")
        detail_title.setStyleSheet("font-weight: 600;")
        lay.addWidget(detail_title)
        self._mesh_detail_hint = QLabel("Select a mesh above")
        self._mesh_detail_hint.setObjectName("mutedTip")
        self._mesh_detail_hint.setWordWrap(True)
        lay.addWidget(self._mesh_detail_hint)

        form = QFormLayout()
        form.setContentsMargins(2, 0, 2, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for key, title in (
            ("file", "File"),
            ("kind", "Kind"),
            ("mesh", "Verts / Faces"),
            ("parts", "Parts"),
            ("atts", "Attachments"),
            ("anims", "Anims"),
            ("maps", "Albedo / Normal / Param"),
            ("bounds", "Bounds (m)"),
        ):
            lab = QLabel(title)
            lab.setObjectName("statsKey")
            val = QLabel("—")
            val.setObjectName("statsValue")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._stat_labels[key] = val
            form.addRow(lab, val)
        lay.addLayout(form)
        return card

    def _parts_for_mesh_key(self, mesh_key: str | None) -> list:
        if not mesh_key:
            return list(self._scene.parts)
        return [p for p in self._scene.parts if (p.mesh_key or "") == mesh_key]

    def _update_stats(self, path: Path | None, scene: Scene | None = None) -> None:
        """Refresh header detail for the selected mesh (or scene totals)."""
        if scene is not None:
            # caller already assigned self._scene; keep detail in sync
            pass
        key = self._selected_mesh_table_key()
        self._fill_mesh_detail(key or None)

    def _selected_mesh_table_key(self) -> str:
        """Filename key from the Scene mesh table selection (or current row)."""
        rows = self.mesh_list.selectionModel().selectedRows(_MESH_COL_NAME)
        row = rows[0].row() if rows else self.mesh_list.currentRow()
        if row < 0:
            return ""
        it = self.mesh_list.item(row, _MESH_COL_NAME)
        if it is None:
            return ""
        return str(it.data(Qt.ItemDataRole.UserRole) or it.text() or "")

    def _fill_mesh_detail(self, mesh_key: str | None) -> None:
        sc = self._scene
        parts = self._parts_for_mesh_key(mesh_key)
        if not sc.parts and not self._mesh_paths:
            for lab in self._stat_labels.values():
                lab.setText("—")
            self._stat_labels["file"].setText("No mesh loaded")
            self._mesh_detail_hint.setText("Drop or Open mesh file(s)")
            return

        if mesh_key:
            path = next((p for p in self._mesh_paths if p.name == mesh_key), None)
            self._mesh_detail_hint.setText(
                str(path) if path is not None else f"Mesh key: {mesh_key}"
            )
            self._stat_labels["file"].setText(mesh_key)
            kind = path.suffix.lstrip(".") if path is not None else (sc.kind or "—")
        else:
            self._mesh_detail_hint.setText(
                f"All meshes · {len(self._mesh_paths)} file(s) — click a row for per-file detail"
            )
            self._stat_labels["file"].setText(
                f"{len(self._mesh_paths)} meshes" if self._mesh_paths else (Path(sc.source).name if sc.source else "—")
            )
            kind = sc.kind or "—"

        n_verts = int(sum(p.vertices.shape[0] for p in parts)) if parts else 0
        n_faces = int(sum(p.indices.shape[0] // 3 for p in parts)) if parts else 0
        n_tex = sum(1 for p in parts if p.albedo_path or p.albedo_ref)
        n_nrm = sum(1 for p in parts if p.normal_path or p.normal_ref)
        n_prm = sum(1 for p in parts if p.parameter_path or p.parameter_ref)
        self._stat_labels["kind"].setText(kind)
        self._stat_labels["mesh"].setText(f"{n_verts:,} / {n_faces:,}")
        self._stat_labels["parts"].setText(str(len(parts)))
        if mesh_key:
            # attachments tagged with mesh stem prefix when multi
            stem = Path(mesh_key).stem
            n_att = sum(
                1
                for a in sc.attachments
                if a.name.startswith(f"{stem}/") or "/" not in a.name
            )
            # single-mesh scene: all atts belong to it
            if len(self._mesh_paths) <= 1:
                n_att = len(sc.attachments)
            self._stat_labels["atts"].setText(str(n_att))
            self._stat_labels["anims"].setText("—" if len(self._mesh_paths) > 1 else str(len(sc.anims)))
        else:
            self._stat_labels["atts"].setText(str(len(sc.attachments)))
            self._stat_labels["anims"].setText(str(len(sc.anims)))
        self._stat_labels["maps"].setText(f"{n_tex} / {n_nrm} / {n_prm}")
        if parts:
            import numpy as np

            mins = np.min(np.vstack([p.vertices for p in parts]), axis=0)
            maxs = np.max(np.vstack([p.vertices for p in parts]), axis=0)
            ext = maxs - mins
            self._stat_labels["bounds"].setText(
                f"{ext[0]:.2f} × {ext[1]:.2f} × {ext[2]:.2f}"
            )
        else:
            self._stat_labels["bounds"].setText("—")

    def _on_mesh_head_select(self, *_args) -> None:
        key = self._selected_mesh_table_key()
        self._fill_mesh_detail(key or None)
        self._set_mesh_hl("file", self._mesh_table_selected_keys(), frame=True)

    def _mesh_hl_blocked(self) -> bool:
        return int(getattr(self, "_suppress_mesh_hl", 0)) > 0

    def _mesh_table_selected_keys(self) -> set[str]:
        keys: set[str] = set()
        table = getattr(self, "mesh_list", None)
        if table is None:
            return keys
        sel = table.selectionModel()
        if sel is None:
            return keys
        for idx in sel.selectedRows(_MESH_COL_NAME):
            it = table.item(idx.row(), _MESH_COL_NAME)
            if it is None:
                continue
            key = str(it.data(Qt.ItemDataRole.UserRole) or it.text() or "")
            if key:
                keys.add(key)
        return keys

    def _mesh_part_name_at(self, row: int) -> str:
        lst = getattr(self, "scene_mesh_list", None)
        if lst is not None and 0 <= row < lst.count():
            item = lst.item(row)
            if item is not None and item.text():
                return item.text()
        page = getattr(self.editor, "meshes_page", None) if self.editor is not None else None
        names = page.material_names() if page is not None else []
        if 0 <= row < len(names) and names[row]:
            return str(names[row])
        if 0 <= row < len(self._scene.parts) and self._scene.parts[row].name:
            return str(self._scene.parts[row].name)
        return ""

    def _set_mesh_hl(self, kind: str, values: set[str], *, frame: bool) -> None:
        """Remember a mesh pick so Mat rebuilds don't drop the outline."""
        if self._mesh_hl_blocked():
            return
        clean = {v for v in values if v}
        if not clean:
            self._mesh_hl = None
            if self.view is not None:
                self.view.set_part_highlight(None)
            return
        self._mesh_hl = (kind, frozenset(clean))
        self._apply_mesh_hl(frame=frame)

    def _apply_mesh_hl(self, *, frame: bool, quiet: bool = False) -> None:
        if self.view is None or not self._mesh_hl:
            return
        kind, values = self._mesh_hl
        if kind == "part":
            n = self.view.set_part_highlight(set(values), frame=frame)
        else:
            n = self.view.set_mat_highlight(set(), set(values), frame=frame)
        if quiet:
            return
        label = ", ".join(sorted(values))
        if n <= 0:
            self._status.showMessage(f"Mesh highlight: no geometry for {label}")
        else:
            self._status.showMessage(
                f"Mesh highlight: {label} · {n} part(s) · glowing outline"
            )

    def _on_mesh_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item is None or item.column() != _MESH_COL_SHOW:
            return
        self._sync_mesh_visibility_from_table()

    def _sync_mesh_visibility_from_table(self) -> None:
        hidden: set[str] = set()
        for r in range(self.mesh_list.rowCount()):
            show_it = self.mesh_list.item(r, _MESH_COL_SHOW)
            name_it = self.mesh_list.item(r, _MESH_COL_NAME)
            if show_it is None or name_it is None:
                continue
            key = str(name_it.data(Qt.ItemDataRole.UserRole) or name_it.text() or "")
            if not key:
                continue
            if show_it.checkState() != Qt.CheckState.Checked:
                hidden.add(key)
        self._hidden_mesh_keys = hidden
        self._push_mesh_visibility()

    def _push_mesh_visibility(self) -> None:
        if self.view is not None:
            self.view.set_hidden_mesh_keys(self._hidden_mesh_keys)

    def _build_sidebar(self) -> FrostGlassFrame:
        side = FrostGlassFrame(radius=SIDE_PANEL_RADIUS)
        side.setObjectName("sidePanel")
        side.setMinimumWidth(0)
        side.setMaximumWidth(SIDE_PANEL_W + 40)
        outer = QVBoxLayout(side)
        # inset for soft shadow ring painted inside FrostGlassFrame
        outer.setContentsMargins(*FROST_CONTENT_MARGINS)
        outer.setSpacing(10)

        # Pinned: logo + tab strip + Open/Folder. Scroll body = Mesh Info + tab page
        # as one document (expand Mesh Info → scroll through it into the tab).
        logo_plate = QFrame()
        logo_plate.setObjectName("logoPlate")
        logo_lay = QVBoxLayout(logo_plate)
        logo_lay.setContentsMargins(2, 0, 2, 0)
        logo_lay.setSpacing(0)
        logo = QLabel()
        logo.setObjectName("sideLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(_logo_pixmap(108, mode=self._theme_mode))
        self._side_logo = logo
        logo_lay.addWidget(logo)
        outer.addWidget(logo_plate)

        strip = SideTabStrip(("Scene", "Mat", "Lamps", "Motion", "Lights"))
        stack = QStackedWidget()
        stack.setObjectName("sideTabStack")
        for page in (
            self._tab_scene(),
            self._tab_materials(),
            self._tab_lamps(),
            self._tab_anims(),
            self._tab_lights(),
        ):
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            stack.addWidget(page)
        self._side_tabs = strip  # scrub strip (was QTabWidget)
        self._side_stack = stack
        strip.index_changed.connect(stack.setCurrentIndex)
        strip.index_changed.connect(self._sync_side_scroll_body)
        outer.addWidget(strip)

        mesh_info = MeshInfoSection()
        mesh_info.set_content(self._build_stats_card())
        self._mesh_info = mesh_info
        mesh_info.expanded_changed.connect(self._sync_side_scroll_body)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(10)
        body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_lay.addWidget(mesh_info)
        body_lay.addWidget(stack)

        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        scroll.setWidget(body)
        prepare_frost_scroll(scroll)
        self._side_scroll_body = body
        outer.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._open_btn)
        btn_row.addWidget(self._folder_btn)
        outer.addLayout(btn_row)
        return side

    def _sync_side_scroll_body(self, *_args) -> None:
        """Size scroll body to Mesh Info + current tab (one continuous document)."""
        stack = getattr(self, "_side_stack", None)
        body = getattr(self, "_side_scroll_body", None)
        info = getattr(self, "_mesh_info", None)
        if stack is not None:
            cur = stack.currentWidget()
            for i in range(stack.count()):
                page = stack.widget(i)
                if page is None:
                    continue
                if page is cur:
                    page.updateGeometry()
                    need = max(page.sizeHint().height(), page.minimumSizeHint().height())
                    page.setMinimumHeight(need)
                else:
                    page.setMinimumHeight(0)
            if cur is not None:
                stack.setMinimumHeight(cur.minimumHeight())
            stack.updateGeometry()
        info_h = 0
        if info is not None:
            info.setMinimumHeight(0)  # don't fight collapse maxHeight anim
            info.updateGeometry()
            info_h = max(info.sizeHint().height(), info.minimumSizeHint().height())
        if body is not None:
            body.updateGeometry()
            gap = 10  # body_lay spacing between Mesh Info and stack
            stack_h = stack.minimumHeight() if stack is not None else 0
            need = info_h + (gap if info_h and stack_h else 0) + stack_h
            need = max(
                need,
                body.sizeHint().height(),
                body.minimumSizeHint().height(),
            )
            body.setMinimumHeight(need)

    def _tab_scene(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(4)

        self._scene_att_block = QWidget()
        att_lay = QVBoxLayout(self._scene_att_block)
        att_lay.setContentsMargins(0, 0, 0, 0)
        att_lay.setSpacing(4)
        self._scene_list_title = QLabel("Attachments (a.*)")
        self._scene_list_title.setStyleSheet("font-weight: 600;")
        self._scene_list_title.setToolTip(
            "Click to select. On Editor page, right dock edits the selection."
        )
        att_lay.addWidget(self._scene_list_title)
        att_lay.addWidget(self._scene_cap_tip)
        att_lay.addWidget(self.att_list)
        att_lay.addWidget(self.scene_mesh_list)
        att_lay.addWidget(self._mesh_ds_bar)

        self._scene_editor_note = QLabel("")
        _compact_tip(self._scene_editor_note)
        self._scene_editor_note.hide()

        overlay_title = QLabel("Viewport")
        overlay_title.setStyleSheet("font-weight: 600;")
        face_tip = QLabel("Blue front · red back (winding)")
        _compact_tip(face_tip)

        lay.addWidget(self._scene_att_block)
        lay.addWidget(self._scene_editor_note)
        lay.addWidget(overlay_title)
        lay.addWidget(self._face_orient_cb)
        lay.addWidget(face_tip)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._update_scene_cap_tip()
        return w

    def _tab_materials(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        row = QHBoxLayout()
        row.addWidget(QLabel("Texture view"))
        row.addWidget(self.tex_mode_combo, 1)
        lay.addLayout(row)

        tip = QLabel("Family row → expand maps. PBR HUD on viewer.")
        _compact_tip(tip)
        tip.setToolTip("Select a material family; expand for albedo / normal / parameter roles.")
        lay.addWidget(tip)
        lay.addWidget(self.tex_tree)
        lay.addWidget(self.tex_detail)
        return w

    def _tab_lamps(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel("Cabin glow (onetex)")
        title.setStyleSheet("font-weight: 600;")
        title.setToolTip(
            "One cast point per lamp island. Live Lit: soft fill + shadow maps. "
            "Sun off + Moon for night."
        )
        lay.addWidget(title)
        tip = QLabel("Island cast · Lit shadows · tick Glow + cast.")
        _compact_tip(tip)
        lay.addWidget(tip)
        lay.addWidget(self._moon_cb)
        lay.addWidget(self._moon_int_lab)
        lay.addWidget(self._moon_int)
        lay.addWidget(self.lamp_tree)

        controls = QFrame()
        controls.setObjectName("lampControls")
        controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        ctrl = QVBoxLayout(controls)
        ctrl.setContentsMargins(0, 6, 0, 0)
        ctrl.setSpacing(6)
        ctrl.addWidget(self._lamp_enabled)
        ctrl.addWidget(self._lamp_bright_lab)
        ctrl.addWidget(self._lamp_bright)
        ctrl.addWidget(self._lamp_range_lab)
        ctrl.addWidget(self._lamp_range)
        ctrl.addWidget(self._lamp_color_btn)
        ctrl.addWidget(self._lamp_gizmo_cb)
        row = QHBoxLayout()
        row.addWidget(self._lamp_add_btn)
        row.addWidget(self._lamp_remove_btn)
        ctrl.addLayout(row)
        ctrl.addWidget(self._lamp_rescan_btn)
        bake_title = QLabel("Bake to textures")
        bake_title.setStyleSheet("font-weight: 600;")
        bake_title.setToolTip(
            "Bake → albedo + parameter (AO in B) under baked_lamps/. "
            "Does not write .trainzmesh."
        )
        ctrl.addWidget(bake_title)
        bake_tip = QLabel("Sidecar albedo + AO · no .trainzmesh write.")
        _compact_tip(bake_tip)
        ctrl.addWidget(bake_tip)
        qrow = QHBoxLayout()
        qrow.addWidget(QLabel("Quality"))
        qrow.addWidget(self._bake_quality, 1)
        ctrl.addLayout(qrow)
        ctrl.addWidget(self._bake_cuda_cb)
        ctrl.addWidget(self._bake_btn)
        lay.addWidget(controls)
        return w

    def _tab_anims(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel("Animations (.kin)")
        title.setStyleSheet("font-weight: 600;")
        lay.addWidget(title)
        lay.addWidget(self._anim_empty)
        lay.addWidget(self.anim_list)
        anim_row = QHBoxLayout()
        anim_row.addWidget(self._play_btn)
        anim_row.addWidget(self._frame_slider, 1)
        lay.addLayout(anim_row)
        tip = QLabel("Drop .kin · scrub only (no bone matrices)")
        _compact_tip(tip)
        lay.addWidget(tip)
        return w

    def _tab_lights(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel("Lighting & scene")
        title.setStyleSheet("font-weight: 600;")
        lay.addWidget(title)

        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("Environment"))
        self._env_combo = QComboBox()
        # none first — no procedural mesh scene / no HDRI until chosen
        self._env_combo.addItem("None", "none")
        hdri_assets = list_hdri_assets()
        for a in hdri_assets:
            self._env_combo.addItem(f"HDRI · {a.label}", a.key)
        for key in env_keys():
            if key == "none":
                continue
            # procedural presets = clear/ambient only (no mesh sky built)
            self._env_combo.addItem(f"{ENVIRONMENTS[key].label} (clear)", key)
        self._env_combo.setCurrentIndex(0)  # None
        self._env_combo.currentIndexChanged.connect(self._on_env_changed)
        env_row.addWidget(self._env_combo, 1)
        lay.addLayout(env_row)

        shade_tip = QLabel("Shading · hold Tab (Blender pie)")
        _compact_tip(shade_tip)
        shade_tip.setToolTip(
            "Hold Tab → drag toward Wire / Solid / Material / Rendered → release Tab"
        )
        lay.addWidget(shade_tip)

        self._ground_cb = QCheckBox("Show ground plane (below origin)")
        self._ground_cb.setChecked(False)
        self._ground_cb.setToolTip("Off by default so world axes stay visible")
        self._ground_cb.toggled.connect(self._on_ground_toggled)
        lay.addWidget(self._ground_cb)

        self._reset_cam_btn = QPushButton("Reset camera")
        self._reset_cam_btn.setToolTip("R — restore framing after load")
        self._reset_cam_btn.clicked.connect(self._reset_camera)
        lay.addWidget(self._reset_cam_btn)

        lay.addWidget(self._sun_mode_cb)
        lay.addWidget(self._sun_az_lab)
        lay.addWidget(self._sun_az)
        lay.addWidget(self._sun_el_lab)
        lay.addWidget(self._sun_el)
        lay.addWidget(self._sun_int_lab)
        lay.addWidget(self._sun_int)
        self._array_lights_host = QWidget()
        arr = QVBoxLayout(self._array_lights_host)
        arr.setContentsMargins(0, 8, 0, 0)
        arr.addWidget(QLabel("Array lights (when Sun mode off)"))
        for cb in self._light_checks:
            arr.addWidget(cb)
        lay.addWidget(self._array_lights_host)
        lay.addSpacing(8)
        lay.addWidget(self._emis_lab)
        lay.addWidget(self._emis_slider)
        tip = QLabel("HDRI 2k · sun/moon mesh · MMB pan · R reset")
        _compact_tip(tip)
        tip.setToolTip(
            "Poly Haven 2k HDRIs (CC0, ACES). env=None = clean clear (no fog). "
            "Sun/Moon = real sphere meshes. "
            "Try Kloppenheim / Belfast Sunset / Drakensberg. "
            "MMB = pan · R = reset."
        )
        lay.addWidget(tip)
        self._sync_sun_ui_enabled()
        return w

    def _build_settings(self) -> QWidget:
        w = FrostGlassFrame(radius=14.0)
        w.setObjectName("glassPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(36, 36, 36, 36)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Settings")
        title.setObjectName("brandTitle")
        title.setFont(app_font(22, QFont.Weight.Bold))
        lay.addWidget(title)

        # Theme
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        self._settings_theme = QComboBox()
        self._settings_theme.addItem("Dark", "dark")
        self._settings_theme.addItem("Light", "light")
        self._settings_theme.setCurrentIndex(0 if self._theme_mode == "dark" else 1)
        self._settings_theme.currentIndexChanged.connect(self._on_settings_theme)
        theme_row.addWidget(self._settings_theme, 1)
        lay.addLayout(theme_row)

        self._settings_flip = QCheckBox("Flip texture V")
        self._settings_flip.setChecked(self._flip_texture_v)
        self._settings_flip.setToolTip(
            "Off = Trainz/D3D (V=0 at top). Only turn on if maps still look inverted."
        )
        self._settings_flip.toggled.connect(self._set_flip_texture_v)
        lay.addWidget(self._settings_flip)

        self._settings_axes = QCheckBox("Show world axes")
        self._settings_axes.setChecked(self._show_axes)
        self._settings_axes.toggled.connect(lambda on: self._set_view_flag("_show_axes", on))
        lay.addWidget(self._settings_axes)

        self._settings_grid = QCheckBox("Show grid")
        self._settings_grid.setChecked(self._show_grid)
        self._settings_grid.toggled.connect(lambda on: self._set_view_flag("_show_grid", on))
        lay.addWidget(self._settings_grid)

        self._settings_gizmo = QCheckBox("Show corner XYZ gizmo")
        self._settings_gizmo.setChecked(self._show_corner_gizmo)
        self._settings_gizmo.toggled.connect(
            lambda on: self._set_view_flag("_show_corner_gizmo", on)
        )
        lay.addWidget(self._settings_gizmo)

        self._settings_atts = QCheckBox("Show attachment gizmos")
        self._settings_atts.setChecked(self._show_atts)
        self._settings_atts.toggled.connect(lambda on: self._set_view_flag("_show_atts", on))
        lay.addWidget(self._settings_atts)

        self._settings_fps = QCheckBox("Show frame stats (F3)")
        self._settings_fps.setChecked(self._show_fps)
        self._settings_fps.setToolTip("Toggle the glass frame-stats HUD (F3)")
        self._settings_fps.toggled.connect(lambda on: self._set_view_flag("_show_fps", on))
        lay.addWidget(self._settings_fps)

        tex_row = QHBoxLayout()
        tex_row.addWidget(QLabel("Default texture view"))
        self._settings_tex_mode = QComboBox()
        self._settings_tex_mode.addItem("All materials", "all")
        self._settings_tex_mode.addItem("Selected only", "selected")
        self._settings_tex_mode.setCurrentIndex(0)
        self._settings_tex_mode.currentIndexChanged.connect(self._on_settings_tex_mode)
        tex_row.addWidget(self._settings_tex_mode, 1)
        lay.addLayout(tex_row)

        cache_tip = QLabel(
            "Texture precache: parallel decode + disk RGBA cache "
            "(~/.cache/trainz_studio/tex) · full-res maps (no downsample)."
        )
        cache_tip.setObjectName("mutedTip")
        cache_tip.setWordWrap(True)
        lay.addWidget(cache_tip)
        self._clear_tex_cache_btn = QPushButton("Clear texture precache")
        self._clear_tex_cache_btn.clicked.connect(self._clear_tex_cache)
        lay.addWidget(self._clear_tex_cache_btn)

        lay.addSpacing(16)
        about_logo = QLabel()
        about_logo.setObjectName("sideLogo")
        about_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_logo.setPixmap(_logo_pixmap(160, mode=self._theme_mode))
        self._about_logo = about_logo
        about_plate = QFrame()
        about_plate.setObjectName("logoPlate")
        ap_lay = QVBoxLayout(about_plate)
        ap_lay.setContentsMargins(12, 8, 12, 8)
        ap_lay.addWidget(about_logo)
        lay.addWidget(about_plate)

        about = QLabel("MSTN Mesh Studio\nCopyright MSTN Production")
        about.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about.setObjectName("mutedTip")
        lay.addWidget(about)
        lay.addStretch(1)
        return w

    def _build_welcome(self) -> QWidget:
        w = QFrame()
        w.setObjectName("glassPanel")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(16)
        lay.setContentsMargins(48, 48, 48, 48)

        logo_plate = QFrame()
        logo_plate.setObjectName("logoPlate")
        logo_plate.setFixedWidth(280)
        lp = QVBoxLayout(logo_plate)
        lp.setContentsMargins(12, 8, 12, 8)
        logo = QLabel()
        logo.setObjectName("sideLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(_logo_pixmap(180, mode=self._theme_mode))
        self._welcome_logo = logo
        lp.addWidget(logo)

        brand = QLabel("Mesh Studio")
        brand.setObjectName("welcomeTitle")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFont(app_font(28, QFont.Weight.Bold))

        sub = QLabel(
            "Preview: .trainzmesh / FBX / .im\n"
            "Editor: Attachments · Meshes — Save writes .trainzmesh / .im in Studio\n"
            "Drop one or more meshes here (multi-select). "
            "Texture view filters parts — never paints the whole car."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setObjectName("mutedTip")
        sub.setWordWrap(True)

        open_btn = QPushButton("Open mesh…")
        open_btn.setObjectName("accentBtn")
        open_btn.setMinimumWidth(220)
        open_btn.setMinimumHeight(44)
        open_btn.clicked.connect(self._browse)

        fix_btn = QPushButton("Open bumper.fbx fixture")
        fix_btn.setMinimumWidth(220)
        fix_btn.setMinimumHeight(40)
        fix_btn.clicked.connect(lambda: self.open_path(FIXTURES / "bumper.fbx"))

        home_btn = QPushButton("Home")
        home_btn.setMinimumWidth(220)
        home_btn.setMinimumHeight(36)
        home_btn.clicked.connect(self.go_home)

        tip = QLabel("LMB orbit · MMB pan · wheel dolly · Ctrl+wheel FOV · Ctrl+Shift fine · arrows walk · R reset · multi-drop meshes")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setObjectName("mutedTip")

        copy = QLabel("Copyright MSTN Production")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy.setObjectName("mutedTip")

        lay.addWidget(logo_plate, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(brand)
        lay.addWidget(sub)
        lay.addSpacing(12)
        lay.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(fix_btn, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(home_btn, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(12)
        lay.addWidget(tip)
        lay.addWidget(copy)
        self._welcome_btns = (open_btn, fix_btn, home_btn)
        return w

    def _hub_reveal_host(self) -> QWidget | None:
        """Content host for hub transitions (excludes menu / status)."""
        return getattr(self, "_center_host", None) or self.centralWidget()

    def _grab_hub_snapshot(self) -> QPixmap:
        """Sharp grab of the studio content area for hub page transitions."""
        host = self._hub_reveal_host()
        if host is None or host.width() < 8 or host.height() < 8:
            return QPixmap()
        try:
            return host.grab()
        except Exception:
            return QPixmap()

    def _hub_transition_dir(self, *, leaving_home: bool, dest: str) -> str:
        """Directional wipe — Mesh← Sounds↑ Engine→ Assets↓ TexMesh↘ (reverse home)."""
        if leaving_home:
            return {
                "mesh": HUB_DIR_LEFT,
                "sounds": HUB_DIR_UP,
                "engine": HUB_DIR_RIGHT,
                "assets": HUB_DIR_DOWN,
                "texmesh": HUB_DIR_DOWN,
            }.get(dest, HUB_DIR_LEFT)
        return {
            "mesh": HUB_DIR_RIGHT,
            "sounds": HUB_DIR_DOWN,
            "engine": HUB_DIR_LEFT,
            "assets": HUB_DIR_UP,
            "texmesh": HUB_DIR_UP,
        }.get(dest, HUB_DIR_RIGHT)

    def _play_hub_transition(
        self,
        from_pm: QPixmap,
        *,
        direction: str,
        label: str,
    ) -> None:
        """Reveal next hub page under a sliding snapshot (safe over GL)."""
        if from_pm.isNull():
            return
        ov = getattr(self, "_hub_reveal", None)
        if ov is None:
            return
        # Don't fight the loading glass.
        busy = getattr(self, "_overlay", None)
        if busy is not None and busy.isVisible():
            return
        host = self._hub_reveal_host()
        if host is not None:
            tl = host.mapTo(self, QPoint(0, 0))
            ov.setGeometry(QRect(tl, host.size()))
        from ..util.hw import hub_reveal_ms

        ms = hub_reveal_ms(warm=self.hubs_are_warm())
        if ms <= 0:
            return
        pal = palette(self._theme_mode)
        ov.play(
            from_pm,
            direction=direction,
            label=label,
            accent=QColor(pal.accent),
            ink=QColor(pal.ink),
            dark=self._theme_mode != "light",
            ms=ms,
        )

    def go_home(self) -> None:
        """Return to MSTN Trainz Studio HOME (keep mesh scene in memory)."""
        leaving = self._studio_mode
        snap = (
            self._grab_hub_snapshot()
            if leaving in ("mesh", "sounds", "engine", "assets", "texmesh")
            else QPixmap()
        )
        direction = self._hub_transition_dir(leaving_home=False, dest=leaving)
        self._studio_mode = "home"
        if self._chrome_ready:
            self._set_editor_dock(False, animated=False)
            self._set_settings_overlay(False, animated=False)
        self._hub.setCurrentIndex(HUB_HOME)
        self._stack.setCurrentIndex(STACK_HUB)
        if self.pbr_hud is not None:
            self.pbr_hud.hide()
        self._apply_studio_chrome()
        self._layout_viewer_pane()  # hub must fill pane or HOME cards sit top-left
        self._status.showMessage(
            "MSTN Trainz Studio — Mesh · Sounds · Engine · Assets · Texture / Mesh"
        )
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if not snap.isNull():
            self._play_hub_transition(snap, direction=direction, label="Home")

    def enter_mesh_studio(self) -> None:
        """Return to Mesh mode — restore last GL scene when still in memory."""
        leaving_home = self._studio_mode == "home"
        snap = self._grab_hub_snapshot() if leaving_home else QPixmap()
        self.ensure_studio_chrome()
        self._studio_mode = "mesh"
        # Recover scene from the GL widget if MainWindow ref was emptied.
        if not (self._scene.parts or self._scene.attachments) and self.view is not None:
            vs = getattr(self.view, "_scene", None)
            if vs is not None and (vs.parts or vs.attachments):
                self._scene = vs
        has_mesh = bool(self._scene.parts or self._scene.attachments)
        if has_mesh:
            if self.view is None:
                self._ensure_gl()
            if self.view is not None:
                self.view.set_scene(self._scene)
                self._stack.setCurrentIndex(STACK_GL)
                self._set_page("preview")
            else:
                self._hub.setCurrentIndex(HUB_MESH)
                self._stack.setCurrentIndex(STACK_HUB)
                if self.pbr_hud is not None:
                    self.pbr_hud.hide()
        else:
            self._hub.setCurrentIndex(HUB_MESH)
            self._stack.setCurrentIndex(STACK_HUB)
            if self.pbr_hud is not None:
                self.pbr_hud.hide()
        self._apply_studio_chrome()
        self._status.showMessage(
            "Mesh Studio"
            if not has_mesh
            else f"Mesh Studio — {Path(self._mesh_paths[0]).name if self._mesh_paths else 'scene'}"
        )
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if leaving_home and not snap.isNull():
            self._play_hub_transition(
                snap,
                direction=self._hub_transition_dir(leaving_home=True, dest="mesh"),
                label="Mesh Studio",
            )

    def enter_sounds_studio(self, paths: list[Path] | None = None) -> None:
        leaving_home = self._studio_mode == "home"
        snap = self._grab_hub_snapshot() if leaving_home else QPixmap()
        self._ensure_sounds_host()
        self._studio_mode = "sounds"
        if self._chrome_ready:
            self._set_editor_dock(False, animated=False)
            self._set_settings_overlay(False, animated=False)
        self._hub.setCurrentIndex(HUB_SOUNDS)
        self._stack.setCurrentIndex(STACK_HUB)
        if self.pbr_hud is not None:
            self.pbr_hud.hide()
        self._apply_studio_chrome()
        pending = list(paths or [])
        pending.extend(getattr(self, "_pending_sound_paths", []))
        self._pending_sound_paths = []
        if pending and self._sounds_host is not None:
            self._sounds_host.import_paths(pending)
        self._status.showMessage("Sounds Studio")
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if leaving_home and not snap.isNull():
            self._play_hub_transition(
                snap,
                direction=self._hub_transition_dir(leaving_home=True, dest="sounds"),
                label="Sounds Studio",
            )

    def enter_engine_tuner(self) -> None:
        leaving_home = self._studio_mode == "home"
        snap = self._grab_hub_snapshot() if leaving_home else QPixmap()
        self._ensure_engine_host()
        self._studio_mode = "engine"
        if self._chrome_ready:
            self._set_editor_dock(False, animated=False)
            self._set_settings_overlay(False, animated=False)
        self._hub.setCurrentIndex(HUB_ENGINE)
        self._stack.setCurrentIndex(STACK_HUB)
        if self.pbr_hud is not None:
            self.pbr_hud.hide()
        self._apply_studio_chrome()
        self._status.showMessage("Engine Tuner")
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if leaving_home and not snap.isNull():
            self._play_hub_transition(
                snap,
                direction=self._hub_transition_dir(leaving_home=True, dest="engine"),
                label="Engine Tuner",
            )

    def _on_packages_enginespec_open(self, kuid: str, text: str, label: str) -> None:
        """Packages → Engine Tuner CDP session; Save writes back and returns."""
        self._ensure_assets_host()
        self._ensure_engine_host()
        pkg = self._assets_host.packages_page
        engine = self._engine_host

        def on_save(new_text: str) -> None:
            out = pkg.apply_enginespec_save(kuid, new_text)
            self._pending_enginespec_notice = (
                f"บันทึกและแก้ไขแล้ว — {out.name if out else 'CDP'} · {kuid}"
            )

        def on_done() -> None:
            self.enter_assets_studio()
            self._assets_host.show_packages()
            notice = getattr(self, "_pending_enginespec_notice", None) or (
                f"บันทึกและแก้ไขแล้ว — {kuid}"
            )
            self._pending_enginespec_notice = None
            pkg._msg(notice)
            sb = getattr(self, "_status", None)
            if sb is not None:
                sb.showMessage(notice, 8000)
            QMessageBox.information(self, "Engine Tuner", notice)

        def on_back() -> None:
            self.enter_assets_studio()
            self._assets_host.show_packages()
            sb = getattr(self, "_status", None)
            if sb is not None:
                sb.showMessage("Back to Packages — CDP unchanged", 5000)

        if not engine.open_cdp_session(
            text=text,
            label=label,
            on_save=on_save,
            on_done=on_done,
            on_back=on_back,
        ):
            return
        self.enter_engine_tuner()

    def _on_packages_mesh_open(self, staged_path: str) -> None:
        """Packages CDP mesh → Mesh Studio (mesh-first; textures may still be filling)."""
        path = Path(staged_path)
        if not path.is_file():
            QMessageBox.warning(self, "Mesh Studio", f"Staged mesh missing:\n{path}")
            return
        # defer so Packages button click returns before hub switch / LoadWorker
        QTimer.singleShot(0, lambda p=path: self._open_packages_mesh_deferred(p))

    def _open_packages_mesh_deferred(self, path: Path) -> None:
        if not path.is_file():
            QMessageBox.warning(self, "Mesh Studio", f"Staged mesh missing:\n{path}")
            return
        self.enter_mesh_studio()
        self.open_paths([path], mode="replace")
        sb = getattr(self, "_status", None)
        if sb is not None:
            sb.showMessage(
                f"Opened from CDP — {path.name} (textures may still be staging)", 6000
            )

    def enter_assets_studio(self) -> None:
        leaving_home = self._studio_mode == "home"
        snap = self._grab_hub_snapshot() if leaving_home else QPixmap()
        self._ensure_assets_host()
        self._assets_host.set_suite("assets")
        self._studio_mode = "assets"
        if self._chrome_ready:
            self._set_editor_dock(False, animated=False)
            self._set_settings_overlay(False, animated=False)
        self._hub.setCurrentIndex(HUB_ASSETS)
        self._stack.setCurrentIndex(STACK_HUB)
        if self.pbr_hud is not None:
            self.pbr_hud.hide()
        self._apply_studio_chrome()
        self._status.showMessage("Assets Tools")
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if leaving_home and not snap.isNull():
            self._play_hub_transition(
                snap,
                direction=self._hub_transition_dir(leaving_home=True, dest="assets"),
                label="Assets Tools",
            )

    def enter_texmesh_studio(self) -> None:
        """Texture / Mesh Tools — maps + LM / materials (same host, texmesh suite)."""
        leaving_home = self._studio_mode == "home"
        snap = self._grab_hub_snapshot() if leaving_home else QPixmap()
        self._ensure_assets_host()
        self._assets_host.set_suite("texmesh")
        self._studio_mode = "texmesh"
        if self._chrome_ready:
            self._set_editor_dock(False, animated=False)
            self._set_settings_overlay(False, animated=False)
        self._hub.setCurrentIndex(HUB_ASSETS)
        self._stack.setCurrentIndex(STACK_HUB)
        if self.pbr_hud is not None:
            self.pbr_hud.hide()
        self._apply_studio_chrome()
        self._status.showMessage("Texture / Mesh Tools")
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        if leaving_home and not snap.isNull():
            self._play_hub_transition(
                snap,
                direction=self._hub_transition_dir(leaving_home=True, dest="texmesh"),
                label="Texture / Mesh Tools",
            )

    def _status_from_sounds(self, msg: str) -> None:
        sb = getattr(self, "_status", None)
        if sb is not None:
            sb.showMessage(msg)

    def _on_save_noticed(self, detail: str) -> None:
        """Glass toast when any studio reports a successful save."""
        hub = getattr(self, "_toasts", None)
        if hub is not None:
            hub.save(detail)
            return
        fn = getattr(self, "_show_save_toast", None)
        if fn is not None:
            fn(self, detail)

    def _on_progress_noticed(self, detail: str, pct: int) -> None:
        """Status lines with ``N%`` → sticky progress bubble."""
        hub = getattr(self, "_toasts", None)
        if hub is None:
            return
        # Title = text without the trailing percent token when possible.
        title = detail
        for sep in (" — ", " · ", "… ", "... "):
            if sep in detail:
                title = detail.split(sep, 1)[0].strip() or detail
                break
        hub.progress(title or "Working…", int(pct), detail)

    def _on_progress_cleared(self, detail: str) -> None:
        """Load/bake often end at 99% — plain status must close the sticky toast."""
        hub = getattr(self, "_toasts", None)
        if hub is not None:
            hub.finish(detail)

    def _open_status_log(self) -> None:
        """Footer left chip → frost dialog with recent status lines."""
        sb = getattr(self, "_status", None)
        lines = list(getattr(sb, "history", []) or [])
        fn = getattr(self, "_show_status_log_dialog", None)
        if fn is not None:
            fn(self, lines)

    def _apply_studio_chrome(self) -> None:
        """Hide mesh chrome on HOME / Sounds / Engine / Assets; show on Mesh.

        Chrome layer stays AlwaysStackOnTop — must hide (or mouse-transparent)
        on HOME or it steals clicks from the hub cards.
        """
        mesh = self._studio_mode == "mesh"
        sp = getattr(self, "_side_panel", None)
        if sp is not None and not mesh:
            sp.hide()
        for edge in (
            getattr(self, "_side_edge_btn", None),
            getattr(self, "_editor_edge_btn", None),
        ):
            if edge is not None and not mesh:
                edge.hide()
        nav = getattr(self, "_nav", None)
        if nav is not None:
            nav.setVisible(mesh)
        bar = getattr(self, "_shortcut_bar", None)
        if bar is not None:
            bar.setVisible(mesh)
        if not mesh and self.pbr_hud is not None:
            self.pbr_hud.hide()
        layer = getattr(self, "_chrome_layer", None)
        if layer is not None:
            # AlwaysStackOnTop chrome must not sit over other hubs or cards won't click.
            layer.setVisible(mesh)
            layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not mesh)
            if not mesh:
                layer.clearMask()

    def _wire(self) -> None:
        self._open_btn.clicked.connect(self._browse)
        self._folder_btn.clicked.connect(self._browse_folder_textures)
        self.att_list.currentItemChanged.connect(self._on_att_select)
        self.scene_mesh_list.currentRowChanged.connect(self._on_scene_mesh_row)
        self.scene_mesh_list.itemChanged.connect(self._on_scene_mesh_checks)
        self._mesh_ds_all.toggled.connect(self._on_mesh_ds_all)
        self._mesh_ds_apply.clicked.connect(self._apply_checked_double_sided)
        self._ed_att_list.currentRowChanged.connect(self._on_ed_att_row)
        self.editor.att_apply.connect(self._on_att_apply)
        self.editor.att_add.connect(self._on_att_add)
        self.editor.att_delete.connect(self._on_att_delete)
        self.editor.att_save.connect(self._on_att_save)
        self.editor.att_save_as.connect(self._on_att_save_as)
        self.editor.material_changed.connect(self._on_mesh_material_changed)
        self.editor.attachment_tree_changed.connect(self._on_att_tree_changed)
        self.editor.two_sided_changed.connect(self._on_mesh_two_sided_changed)
        self.editor.attachments_page.attachment_selected.connect(self._on_ed_att_row)
        self.editor.meshes_page.material_selected.connect(self._on_editor_mesh_selected)
        self.editor.editor_mode_changed.connect(self._on_editor_mode_changed)
        self.tex_tree.itemSelectionChanged.connect(self._on_tex_selection_changed)
        self.tex_tree.customContextMenuRequested.connect(self._on_tex_context_menu)
        self.tex_mode_combo.currentIndexChanged.connect(self._on_tex_mode_changed)
        self.anim_list.currentItemChanged.connect(self._on_anim_select)
        self._play_btn.clicked.connect(self._toggle_play)
        self._frame_slider.valueChanged.connect(self._on_frame_scrub)
        self.editor.texture.saved.connect(self._on_editor_saved)
        self.editor.texture.rescan_requested.connect(self._sync_editor_texture_list)
        self.editor.texture.texture_selected.connect(self._on_editor_texture_selected)
        self.editor.texture.material_preview_changed.connect(
            self._on_editor_material_preview
        )
        self.editor.texture.two_sided_changed.connect(self._on_editor_two_sided)

        self._nav.page_changed.connect(self._set_page)
        self._nav.home_btn.clicked.connect(self.go_home)

        for seg in self._pbr_controls:
            seg.mode_changed.connect(self._set_pbr_mode)

        for i, cb in enumerate(self._light_checks):
            cb.toggled.connect(lambda on, idx=i: self._on_light_toggle(idx, on))

        self._sun_mode_cb.toggled.connect(self._on_sun_mode)
        self._sun_az.valueChanged.connect(self._on_sun_params)
        self._sun_el.valueChanged.connect(self._on_sun_params)
        self._sun_int.valueChanged.connect(self._on_sun_params)
        self._emis_slider.valueChanged.connect(self._on_emissive_boost)

        self.lamp_tree.itemSelectionChanged.connect(self._on_lamp_select)
        self.mesh_list.itemSelectionChanged.connect(self._on_mesh_head_select)
        self.mesh_list.currentCellChanged.connect(self._on_mesh_head_select)
        self.mesh_list.itemChanged.connect(self._on_mesh_table_item_changed)
        self._lamp_gizmo_cb.toggled.connect(self._push_lamps_to_view)
        self._face_orient_cb.toggled.connect(self._set_face_orientation)
        self._lamp_enabled.toggled.connect(self._on_lamp_edit)
        self._lamp_bright.valueChanged.connect(self._on_lamp_edit)
        self._lamp_range.valueChanged.connect(self._on_lamp_edit)
        self._lamp_color_btn.clicked.connect(self._pick_lamp_color)
        self._style_lamp_color_btn()
        self._moon_cb.toggled.connect(self._push_lamps_to_view)
        self._moon_int.valueChanged.connect(self._on_moon_int)
        self._lamp_rescan_btn.clicked.connect(self._rescan_lamps)
        self._lamp_add_btn.clicked.connect(self._add_lamp_from_mat)
        self._lamp_remove_btn.clicked.connect(self._remove_selected_lamp)
        self._bake_btn.clicked.connect(self._start_lamp_bake)
        self._bake_bar.cancel_requested.connect(self._cancel_lamp_bake)
        self._mesh_remove_btn.clicked.connect(self._remove_selected_meshes)
        self._mesh_clear_btn.clicked.connect(self._clear_meshes)

    # ── theme / pages / PBR ──────────────────────────────────

    def _toggle_theme(self) -> None:
        # Never put QGraphicsOpacityEffect / window-grab fade on MainWindow —
        # freezes QOpenGLWidget and left half-dark / half-light plates.
        next_mode = "light" if self._theme_mode == "dark" else "dark"
        self._begin_theme_change(next_mode)

    def _begin_theme_change(self, mode: str, *, animated: bool = False) -> None:
        del animated  # ponytail: grab+fade was slow + mixed (GL black holes)
        mode = mode if mode in ("dark", "light") else "dark"
        if mode == self._theme_mode:
            return
        if getattr(self, "_theme_busy", False):
            return
        self._theme_busy = True
        try:
            self._theme_mode = mode
            self._apply_theme_mode()
        finally:
            self._theme_busy = False

    def _refresh_logos(self) -> None:
        mode = self._theme_mode
        if hasattr(self, "_side_logo"):
            self._side_logo.setPixmap(_logo_pixmap(108, mode=mode))
        if hasattr(self, "_welcome_logo"):
            self._welcome_logo.setPixmap(_logo_pixmap(180, mode=mode))
        if hasattr(self, "_home_logo"):
            self._home_logo.setPixmap(_logo_pixmap(180, mode=mode))
        if hasattr(self, "_about_logo"):
            self._about_logo.setPixmap(_logo_pixmap(160, mode=mode))
        if hasattr(self, "_overlay") and hasattr(self._overlay, "logo"):
            self._overlay.logo.setPixmap(_logo_pixmap(140, mode=mode))

    def _retint_frost_panels(self) -> None:
        """Solid theme tint on every frost plate — Engine/Assets drawers included."""
        dark = self._theme_mode != "light"
        for panel in self.findChildren(FrostGlassFrame):
            panel.set_frost(None, dark=dark)

    def _retint_glass_chips(self) -> None:
        dark = self._theme_mode != "light"
        for w in (
            getattr(self, "_nav", None),
            getattr(self, "_bake_bar", None),
            getattr(self, "pbr_hud", None),
            getattr(self, "_title_bar", None),
        ):
            if w is not None:
                set_glass_dark(w, dark)
        bar = getattr(self, "_title_bar", None)
        if bar is not None:
            bar.set_theme(self._theme_mode)
        for seg in getattr(self, "_pbr_controls", []) or []:
            if seg is not None:
                set_glass_dark(seg, dark)
        view = getattr(self, "view", None)
        chip = getattr(view, "fps_chip", None) if view is not None else None
        if chip is not None:
            set_glass_dark(chip, dark)

    def _push_hub_theme_palettes(self) -> None:
        """Cheap palette push — avoids allWidgets polish; fixes sticky hub plates."""
        qp = qpalette_for(self._theme_mode)
        for w in (
            getattr(self, "_stack", None),
            getattr(self, "_hub", None),
            getattr(self, "_assets_host", None),
            getattr(self, "_sounds_host", None),
            getattr(self, "_engine_host", None),
        ):
            if w is not None:
                w.setPalette(qp)

    def _deferred_theme_hosts(self) -> None:
        """Secondary retints after sheet swap — keep Theme click snappy."""
        mode = self._theme_mode
        if hasattr(self, "_sounds_host") and self._sounds_host is not None:
            self._sounds_host.set_theme(mode)
        if getattr(self, "_engine_host", None) is not None:
            self._engine_host.set_theme(mode)
        if getattr(self, "_assets_host", None) is not None:
            self._assets_host.set_theme(mode)
        apply_code_edit_theme(self, mode)

    def _deferred_theme_chrome(self) -> None:
        """Frost plates + HOME wash — after the sheet swap paints."""
        self._retint_frost_panels()
        if hasattr(self, "_home_page"):
            self._home_page.set_theme(self._theme_mode)

    def _deferred_frost_after_theme(self) -> None:
        """Re-grab frost plates after style polish settles — never sync in _apply_theme_mode."""
        view = self.view
        if view is not None and getattr(view, "_cam_busy", False):
            return
        self._refresh_side_frost()
        if getattr(self, "_settings_open", False) and isinstance(
            getattr(self, "_settings_panel", None), FrostGlassFrame
        ):
            self._apply_panel_frost(self._settings_panel, self._center_host.rect())
        if getattr(self, "_editor_dock_open", False) and isinstance(
            getattr(self, "editor", None), FrostGlassFrame
        ):
            self._apply_panel_frost(self.editor, self._editor_dock_rect(open_=True))

    def _apply_theme_mode(self) -> None:
        app = QApplication.instance()
        # drop any leftover opacity effect from older builds
        self.setGraphicsEffect(None)
        # Batch one repaint on the window — QApplication has no setUpdatesEnabled
        # (that AttributeError was swallowed by Qt and left Theme looking dead).
        self.setUpdatesEnabled(False)
        try:
            # Cached QSS/QPalette only — no setFont (second polish) on toggle.
            apply_theme(
                app if app is not None else self,
                self._theme_mode,
                rebind_font=False,
            )
            self._push_hub_theme_palettes()
            p = palette(self._theme_mode)
            self._refresh_logos()  # warm_logo_cache — pixmap swap only
            self._retint_glass_chips()
            if self.view is not None:
                self.view.setStyleSheet("background: transparent; border: none;")
                if not hasattr(self, "_env_combo") or self._env_combo.currentData() in (
                    None,
                    "none",
                ):
                    self.view.set_clear_color(p.gl_clear)
            if hasattr(self, "_settings_theme"):
                idx = 0 if self._theme_mode == "dark" else 1
                self._settings_theme.blockSignals(True)
                self._settings_theme.setCurrentIndex(idx)
                self._settings_theme.blockSignals(False)
            self._status.showMessage(f"Theme: {self._theme_mode}")
            self._sync_theme_menu()
        finally:
            self.setUpdatesEnabled(True)
        if self.view is not None:
            self.view.update()
        # Hosts / frost / HOME / CodeEdit / frost-grab — off the click path.
        QTimer.singleShot(0, self._deferred_theme_chrome)
        QTimer.singleShot(0, self._deferred_theme_hosts)
        QTimer.singleShot(80, self._deferred_frost_after_theme)

    def _on_env_changed(self, _idx: int = 0) -> None:
        key = str(self._env_combo.currentData() or "none")
        if self.view is not None:
            self.view.set_environment(key)
            if key == "none":
                self.view.set_clear_color(palette(self._theme_mode).gl_clear)
            # HDRI peak → snap sun az/el so disc + light match the map
            hint = self.view.consume_hdri_sun_hint()
            if hint is not None:
                az, el = hint
                self._sun_az.blockSignals(True)
                self._sun_el.blockSignals(True)
                self._sun_az.setValue(int(round(az)) % 360)
                import numpy as np

                self._sun_el.setValue(int(round(float(np.clip(el, -10.0, 89.0)))))
                self._sun_az.blockSignals(False)
                self._sun_el.blockSignals(False)
                self._sun_az_lab.setText(f"Azimuth {self._sun_az.value()}°")
                self._sun_el_lab.setText(f"Elevation {self._sun_el.value()}°")
                self._push_lights_to_view()
        label = self._env_combo.currentText()
        self._status.showMessage(f"Environment: {label}")

    def _on_ground_toggled(self, on: bool) -> None:
        if self.view is not None:
            self.view.set_show_ground(on)
        self._status.showMessage("Ground on" if on else "Ground off (axes clear)")

    def _apply_shading(self, mode: str) -> None:
        mode = str(mode or SHADING_RENDERED)
        if mode not in (SHADING_WIRE, SHADING_SOLID, SHADING_MATERIAL, SHADING_RENDERED):
            mode = SHADING_RENDERED
        self._shading_mode = mode
        if self.view is not None:
            self.view.set_shading(mode)
        label = next((n for n, k in SHADING_MODES if k == mode), mode)
        self._status.showMessage(f"Shading: {label}")

    def _apply_att_edit_mode(self, mode: str) -> None:
        mode = str(mode or ATT_EDIT_VIEW)
        if mode not in (ATT_EDIT_VIEW, ATT_EDIT_MOVE):
            mode = ATT_EDIT_VIEW
        self._att_edit_mode = mode
        self._sync_att_viewport_mode()
        self._refresh_shortcut_bar()
        label = next((n for n, k in ATT_EDIT_MODES if k == mode), mode)
        tip = (
            "Move — drag axis / center gizmo on selected a.*"
            if mode == ATT_EDIT_MOVE
            else "View — select a.* only (no drag)"
        )
        self._status.showMessage(f"Edit: {label}  ·  {tip}")

    def _active_tab_pie(self) -> ModePie:
        """Editor → Edit pie; Preview/Settings → Shading pie."""
        if self._in_editor_page():
            return self._edit_pie
        return self._shading_pie

    def _arm_tab_pie(self) -> None:
        pie = self._active_tab_pie()
        # hide the other so only one overlay shows
        other = self._shading_pie if pie is self._edit_pie else self._edit_pie
        other.cancel()
        # Drop sidebar focus so Qt stops treating Tab as focus-next
        fw = QApplication.focusWidget()
        if fw is not None and fw is not pie:
            fw.clearFocus()
        self._tab_pie = pie
        self._tab_pie_armed = True
        self._tab_pie_sticky = False
        self._tab_pie_t0 = time.perf_counter()
        pie.popup_at(QCursor.pos())
        # Above chrome (AlwaysStackOnTop sibling) — chrome.raise_ would bury us otherwise
        pie.raise_()

    def _commit_tab_pie(self, *, force: bool = False) -> None:
        pie = self._tab_pie or self._active_tab_pie()
        # Short tap → keep pie open (sticky) until click / Esc / Tab again
        if (
            not force
            and self._tab_pie_armed
            and not self._tab_pie_sticky
        ):
            if (time.perf_counter() - float(self._tab_pie_t0)) < 0.20:
                self._tab_pie_sticky = True
                pie.raise_()
                return
        self._tab_pie_armed = False
        self._tab_pie_sticky = False
        self._tab_pie = None
        mode = pie.commit()
        if not mode:
            return
        if pie is self._edit_pie:
            self._apply_att_edit_mode(mode)
        else:
            self._apply_shading(mode)

    def _cancel_tab_pie(self) -> None:
        pie = self._tab_pie or self._active_tab_pie()
        self._tab_pie_armed = False
        self._tab_pie_sticky = False
        self._tab_pie = None
        pie.cancel()

    def _refresh_shortcut_bar(self) -> None:
        bar = getattr(self, "_shortcut_bar", None)
        if bar is None:
            return
        if self._in_editor_page():
            mode = getattr(self, "_att_edit_mode", ATT_EDIT_VIEW)
            edit = "Move" if mode == ATT_EDIT_MOVE else "View"
            bar.setText(
                "LMB Orbit   ·   MMB Pan   ·   Wheel Dolly   ·   "
                f"Tab Edit pie ({edit})   ·   Alt+LMB pick a.*   ·   "
                "[ ] Side panels   ·   ← ↑ ↓ → Walk   ·   R Reset"
            )
        else:
            bar.setText(
                "LMB Orbit   ·   MMB Pan L/R · U/D   ·   Wheel Dolly   ·   "
                "Ctrl+Wheel FOV (mm)   ·   Tab Shading pie   ·   "
                "[ ] Side panels   ·   ← ↑ ↓ → Walk   ·   R Reset   ·   F3 Frame stats"
            )

    def _focus_wants_tab(self) -> bool:
        """Only multi-line text keeps Tab — spin/line/combo must not steal the pie."""
        w = QApplication.focusWidget()
        while w is not None:
            if isinstance(w, QPlainTextEdit):
                return True
            w = w.parentWidget()
        return False

    def _tab_opens_pie(self) -> bool:
        """Mesh Preview/Editor/Settings: Tab = pie (Blender), not sidebar focus chain."""
        if getattr(self, "_studio_mode", "mesh") != "mesh":
            return False
        if getattr(self, "_page", "preview") not in ("preview", "meshes", "attachs", "settings"):
            return False
        return not self._focus_wants_tab()

    def _strip_sidebar_tab_focus(self) -> None:
        """Click-focus inputs OK; Tab must not cycle side/editor controls."""
        roots = (
            getattr(self, "_side_panel", None),
            getattr(self, "editor", None),
            getattr(self, "_settings_panel", None),
        )
        for root in roots:
            if root is None:
                continue
            widgets = [root, *root.findChildren(QWidget)]
            for w in widgets:
                pol = w.focusPolicy()
                # StrongFocus / WheelFocus include TabFocus — drop to ClickFocus
                if int(pol) & int(Qt.FocusPolicy.TabFocus):
                    if int(pol) & int(Qt.FocusPolicy.ClickFocus):
                        w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                    else:
                        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if (
            key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and not event.isAutoRepeat()
            and self._tab_opens_pie()
            and not self._tab_pie_armed
        ):
            self._arm_tab_pie()
            event.accept()
            return
        # [ ] — collapse / expand left / right frost panels
        # F3 — frame stats (QAction shortcut alone is flaky with hidden menuBar)
        if not self._focus_wants_tab() and not event.isAutoRepeat():
            if key == Qt.Key.Key_BracketLeft:
                self._toggle_side_panel()
                event.accept()
                return
            if key == Qt.Key.Key_BracketRight:
                self._toggle_editor_panel()
                event.accept()
                return
            if key == Qt.Key.Key_F3:
                self._set_view_flag("_show_fps", not self._show_fps)
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and self._tab_pie_armed
        ):
            self._commit_tab_pie()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _on_settings_theme(self, _idx: int = 0) -> None:
        mode = str(self._settings_theme.currentData() or "dark")
        if getattr(self, "_theme_busy", False):
            idx = 0 if self._theme_mode == "dark" else 1
            self._settings_theme.blockSignals(True)
            self._settings_theme.setCurrentIndex(idx)
            self._settings_theme.blockSignals(False)
            return
        self._begin_theme_change(mode)

    def _on_settings_tex_mode(self, _idx: int = 0) -> None:
        mode = str(self._settings_tex_mode.currentData() or "all")
        self.tex_mode_combo.blockSignals(True)
        self.tex_mode_combo.setCurrentIndex(0 if mode == "all" else 1)
        self.tex_mode_combo.blockSignals(False)
        self._tex_mode = mode
        self._apply_tex_filter()

    def _set_flip_texture_v(self, on: bool) -> None:
        on = bool(on)
        self._flip_texture_v = on
        if hasattr(self, "_settings_flip"):
            self._settings_flip.blockSignals(True)
            self._settings_flip.setChecked(on)
            self._settings_flip.blockSignals(False)
        act = self._view_acts.get("flip_v")
        if act is not None:
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)
        if self.view is not None:
            self.view.set_flip_texture_v(on)
        self._status.showMessage(f"Flip texture V: {'on' if on else 'off'}")

    def _clear_tex_cache(self) -> None:
        from ..io.texcache import cache_root, clear_cache

        n = clear_cache()
        self._status.showMessage(f"Cleared {n} precache file(s) · {cache_root()}")

    def _reset_camera(self) -> None:
        if self.view is not None:
            self.view.reset_camera()
            self._status.showMessage("Camera reset")

    def _set_face_orientation(self, on: bool) -> None:
        """Scene-tab / View menu — blue front / red back (Blender Face Orientation)."""
        on = bool(on)
        self._face_orient = on
        cb = getattr(self, "_face_orient_cb", None)
        if cb is not None:
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
        act = self._view_acts.get("face_orient")
        if act is not None:
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)
        if self.view is not None:
            self.view.set_face_orientation(on)
        self._status.showMessage(
            "Face Orientation on — blue front · red back"
            if on
            else "Face Orientation off"
        )

    def _set_view_flag(self, attr: str, on: bool) -> None:
        on = bool(on)
        setattr(self, attr, on)
        act = self._view_acts.get(attr)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)
        # sync settings checkboxes
        mapping = {
            "_show_axes": "_settings_axes",
            "_show_grid": "_settings_grid",
            "_show_corner_gizmo": "_settings_gizmo",
            "_show_atts": "_settings_atts",
            "_show_fps": "_settings_fps",
        }
        cb_name = mapping.get(attr)
        if cb_name and hasattr(self, cb_name):
            cb = getattr(self, cb_name)
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
        if self.view is not None:
            if attr == "_show_fps":
                self.view.set_show_fps(on)
                self._place_fps_hud()
            else:
                setattr(self.view, attr, on)
                self.view.update()

    def _set_pbr_mode(self, mode: int) -> None:
        self._debug_mode = int(mode)
        for seg in self._pbr_controls:
            seg.blockSignals(True)
            seg.set_mode(mode)
            seg.blockSignals(False)
        for m, act in getattr(self, "_dbg_actions", {}).items():
            act.blockSignals(True)
            act.setChecked(m == mode)
            act.blockSignals(False)
        if self.view is not None:
            self.view.set_debug_mode(mode)
        label = next((n for n, m in PBR_MODES if m == mode), str(mode))
        self._status.showMessage(f"PBR mode: {label}")

    def _in_editor_page(self) -> bool:
        return getattr(self, "_page", "") in ("meshes", "attachs")

    def _canonical_page(self, which: str) -> str:
        """Map legacy ``editor`` onto the tab already showing, else last mode."""
        if which in ("attachments", "attachs"):
            return "attachs"
        if which == "editor":
            ed = getattr(self, "editor", None)
            if ed is not None and ed.current_mode() == "meshes":
                return "meshes"
            if ed is not None and ed.current_mode() == "attachments":
                return "attachs"
            mode = getattr(self, "_editor_mode", "meshes")
            return mode if mode in ("meshes", "attachs") else "meshes"
        if which in ("preview", "meshes", "attachs", "settings"):
            return which
        return "preview"

    def _set_nav_checked(self, which: str) -> None:
        # sync pill only — do not animate button widths (that caused double-click lag)
        self._nav.set_page(which, animate=True, emit=False)

    def _set_page(self, which: str) -> None:
        if self._studio_mode != "mesh":
            self._studio_mode = "mesh"
            self._apply_studio_chrome()
        instant = bool(getattr(self._nav, "_drag", False))
        which = self._canonical_page(which)
        self._page = which

        if which in ("meshes", "attachs"):
            self._editor_mode = which
            self._set_nav_checked(which)
            self._set_settings_overlay(False, animated=not instant)
            # Keep GL full-size; Editor overlays the right (crop, no resize).
            if self.view is not None and (self._scene.parts or self._scene.attachments):
                self._stack.setCurrentIndex(STACK_GL)
                self.pbr_hud.show()
                self._reposition_pbr_hud()
            elif self._scene.attachments:
                self._stack.setCurrentIndex(STACK_GL)
                self.pbr_hud.hide()
            else:
                self._hub.setCurrentIndex(HUB_MESH)
                self._stack.setCurrentIndex(STACK_HUB)
                self.pbr_hud.hide()
            if which == "meshes":
                self.editor.show_meshes_tab()
            else:
                self.editor.show_attachments_tab()
            self._set_editor_dock(True, animated=not instant)
            self._set_scene_att_ui_for_editor(True)
            # Lists are preloaded on mesh load — only rebuild if missing/stale
            self._refresh_editor_dock(force=False)
            self._sync_att_viewport_mode()
            self._refresh_shortcut_bar()
            label = "Meshes Editor" if which == "meshes" else "Attachs Editor"
            self._status.showMessage(f"{label} — pick on the left · edit on the right · Save")
            QTimer.singleShot(0, self._reposition_viewer_chrome)
            return
        if which == "settings":
            self._set_nav_checked("settings")
            # Instant dock shut — slide-out left Editor covering Preview on slow PCs.
            self._set_editor_dock(False, animated=False)
            self._set_scene_att_ui_for_editor(False)
            self._sync_att_viewport_mode()
            self._refresh_shortcut_bar()
            # Keep GL under Settings overlay — stack swap was the stutter.
            if self.view is not None and (self._scene.parts or self._scene.attachments):
                self._stack.setCurrentIndex(STACK_GL)
            else:
                self._hub.setCurrentIndex(HUB_MESH)
                self._stack.setCurrentIndex(STACK_HUB)
            self.pbr_hud.hide()
            self._set_settings_overlay(True, animated=not instant)
            QTimer.singleShot(0, self._reposition_viewer_chrome)
            return
        # preview — viewer only (no a.* drag); dock shut instant so GL reads full-bleed
        self._set_nav_checked("preview")
        self._set_settings_overlay(False, animated=not instant)
        self._set_editor_dock(False, animated=False)
        self._set_scene_att_ui_for_editor(False)
        self._sync_att_viewport_mode()
        self._refresh_shortcut_bar()
        if self.view is not None and (self._scene.parts or self._scene.attachments):
            self._stack.setCurrentIndex(STACK_GL)
            self.pbr_hud.show()
            self._reposition_pbr_hud()
        else:
            self._hub.setCurrentIndex(HUB_MESH)
            self._stack.setCurrentIndex(STACK_HUB)
            self.pbr_hud.hide()
        QTimer.singleShot(0, self._reposition_viewer_chrome)

    def _side_panel_rect(self, *, open_: bool | None = None) -> QRect:
        """Left frost sidebar over full-bleed viewport (or parked off-left)."""
        host = self._center_host
        m = SIDE_PANEL_MARGIN
        # Cap harder on narrow / high-DPI laptops — //3 + 500px dock ate the strip.
        w = min(SIDE_PANEL_W, max(260, host.width() // 4))
        h = max(1, host.height() - 2 * m)
        is_open = self._side_open if open_ is None else bool(open_)
        if is_open:
            return QRect(m, m, w, h)
        return QRect(-w - 8, m, w, h)

    def _layout_side_panel(self) -> None:
        side = getattr(self, "_side_panel", None)
        if side is None:
            return
        # HOME / Sounds: never show mesh sidebar (layout used to force it visible).
        if getattr(self, "_studio_mode", "home") != "mesh":
            side.hide()
            self._layout_panel_edge_btns()
            return
        open_ = getattr(self, "_side_open", True)
        side.setGeometry(self._side_panel_rect(open_=open_))
        side.setVisible(open_)
        if open_:
            side.raise_()
        self._layout_panel_edge_btns()
        # keep editor/settings/chrome above when open
        if getattr(self, "_editor_dock_open", False) and self.editor.isVisible():
            self.editor.raise_()
        if getattr(self, "_settings_open", False):
            panel = getattr(self, "_settings_panel", None)
            if panel is not None and panel.isVisible():
                panel.raise_()
        layer = getattr(self, "_chrome_layer", None)
        if layer is not None and layer.isVisible():
            layer.raise_()
        for b in (
            getattr(self, "_side_edge_btn", None),
            getattr(self, "_editor_edge_btn", None),
        ):
            if b is not None and b.isVisible():
                b.raise_()

    def _layout_panel_edge_btns(self) -> None:
        """‹ › tabs so left / right panels collapse independently."""
        host = self._center_host
        if host is None:
            return
        left = getattr(self, "_side_edge_btn", None)
        right = getattr(self, "_editor_edge_btn", None)
        if getattr(self, "_studio_mode", "home") != "mesh":
            if left is not None:
                left.hide()
            if right is not None:
                right.hide()
            return
        mid_y = max(8, (host.height() - 56) // 2)
        settings_on = getattr(self, "_settings_open", False)

        if left is not None:
            if settings_on:
                left.hide()
            else:
                left.setText("‹" if self._side_open else "›")
                if self._side_open:
                    g = self._side_panel.geometry()
                    left.move(g.right() - PANEL_EDGE_W // 2, mid_y)
                else:
                    left.move(SIDE_PANEL_MARGIN, mid_y)
                left.show()
                left.raise_()

        if right is not None:
            if settings_on:
                right.hide()
            else:
                ed_open = getattr(self, "_editor_dock_open", False)
                right.setText("›" if ed_open else "‹")
                if ed_open and self.editor.isVisible():
                    g = self.editor.geometry()
                    right.move(g.left() - PANEL_EDGE_W // 2, mid_y)
                else:
                    right.move(host.width() - SIDE_PANEL_MARGIN - PANEL_EDGE_W, mid_y)
                right.show()
                right.raise_()

    def _toggle_side_panel(self) -> None:
        self._set_side_panel(not getattr(self, "_side_open", True), animated=True)

    def _toggle_editor_panel(self) -> None:
        open_ = not getattr(self, "_editor_dock_open", False)
        if open_ and not self._in_editor_page():
            # expanding right panel enters the last editor (Meshes by default)
            self._set_page(getattr(self, "_editor_mode", "meshes"))
            return
        self._set_editor_dock(open_, animated=True)
        if not open_:
            self._set_scene_att_ui_for_editor(False)
            self._sync_att_viewport_mode()
        else:
            self._set_scene_att_ui_for_editor(True)
            self._refresh_editor_dock()
            self._sync_att_viewport_mode()
        self._layout_panel_edge_btns()
        QTimer.singleShot(0, self._reposition_viewer_chrome)

    def _set_side_panel(self, open_: bool, *, animated: bool) -> None:
        open_ = bool(open_)
        if open_ == getattr(self, "_side_open", True):
            self._layout_side_panel()
            return
        from ..util.hw import prefer_instant_panels

        if animated and prefer_instant_panels():
            animated = False
        self._side_open = open_
        side = self._side_panel
        target = self._side_panel_rect(open_=open_)

        def _done() -> None:
            side.setGeometry(target)
            side.setVisible(open_)
            if open_:
                self._refresh_side_frost()
            self._layout_panel_edge_btns()
            self._reposition_viewer_chrome()

        if open_:
            self._apply_panel_frost(side, self._side_panel_rect(open_=True))
            start = self._side_panel_rect(open_=False)
            side.setGeometry(start)
            side.show()
            side.raise_()
            if animated:
                animate_geometry(
                    side,
                    target,
                    EDITOR_DOCK_MS,
                    on_tick=self._layout_panel_edge_btns,
                    on_done=_done,
                )
            else:
                _done()
            return
        if animated and side.isVisible():
            animate_geometry(
                side,
                target,
                EDITOR_DOCK_MS,
                on_tick=self._layout_panel_edge_btns,
                on_done=_done,
            )
        else:
            side.setGeometry(target)
            _done()

    def _refresh_side_frost(self) -> None:
        side = getattr(self, "_side_panel", None)
        if not isinstance(side, FrostGlassFrame):
            return
        if not getattr(self, "_side_open", True):
            return
        self._apply_panel_frost(side, self._side_panel_rect(open_=True))

    def _editor_dock_rect(self, *, open_: bool) -> QRect:
        """Editor geometry over the right (floating margins — matches left sidebar)."""
        host = self._center_host
        m = SIDE_PANEL_MARGIN
        side_w = 0
        if getattr(self, "_side_open", True):
            sp = getattr(self, "_side_panel", None)
            if sp is not None and sp.isVisible():
                side_w = sp.geometry().right() + m
        # Keep ≥40% clear viewport so Preview never looks "pushed" on 1366×768.
        clear_min = max(280, int(host.width() * 0.40))
        w = min(EDITOR_DOCK_W, max(260, host.width() - side_w - clear_min - m))
        h = max(1, host.height() - 2 * m)
        if open_:
            return QRect(host.width() - w - m, m, w, h)
        return QRect(host.width() + 8, m, w, h)

    def _frost_pixmap_for_host_rect(self, host_rect: QRect) -> QPixmap | None:
        """Grab GL under a center_host rect → cheap frost plate."""
        view = self.view
        if view is None or host_rect.width() < 8 or host_rect.height() < 8:
            return None
        try:
            fb = view.grabFramebuffer()
        except Exception:
            return None
        if fb.isNull():
            return None
        dpr = float(view.devicePixelRatio())
        tl = view.mapFrom(self._center_host, host_rect.topLeft())
        br = view.mapFrom(self._center_host, host_rect.bottomRight())
        x0 = int(max(0, min(tl.x(), br.x())) * dpr)
        y0 = int(max(0, min(tl.y(), br.y())) * dpr)
        x1 = int(min(view.width(), max(tl.x(), br.x()) + 1) * dpr)
        y1 = int(min(view.height(), max(tl.y(), br.y()) + 1) * dpr)
        # framebuffer may be device pixels matching widget*dpr
        if fb.width() != int(view.width() * dpr) or fb.height() != int(view.height() * dpr):
            # scale map into actual FBO size
            sx = fb.width() / max(1.0, float(view.width()))
            sy = fb.height() / max(1.0, float(view.height()))
            x0 = int(max(0, min(tl.x(), br.x())) * sx)
            y0 = int(max(0, min(tl.y(), br.y())) * sy)
            x1 = int(min(view.width(), max(tl.x(), br.x()) + 1) * sx)
            y1 = int(min(view.height(), max(tl.y(), br.y()) + 1) * sy)
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        if x0 >= fb.width() or y0 >= fb.height():
            return None
        w = min(w, fb.width() - x0)
        h = min(h, fb.height() - y0)
        crop = fb.copy(x0, y0, w, h)
        pm = make_frost_pixmap(crop)
        return pm if not pm.isNull() else None

    def _apply_panel_frost(self, panel: FrostGlassFrame, host_rect: QRect) -> None:
        """Frost plate from last GL frame — never force a paint + processEvents (that janks orbit)."""
        dark = self._theme_mode != "light"
        view = self.view
        # Skip GL readback while orbiting — keep previous plate (or solid tint).
        if view is not None and getattr(view, "_cam_busy", False):
            return
        pm = self._frost_pixmap_for_host_rect(host_rect)
        if pm is None:
            return  # keep existing frost; don't thrash to empty
        panel.set_frost(pm, dark=dark)

    def _set_settings_overlay(self, open_: bool, *, animated: bool) -> None:
        """Cover center with Settings — GL stays underneath (no stack tear-down)."""
        panel = getattr(self, "_settings_panel", None)
        if panel is None:
            return
        if open_ == getattr(self, "_settings_open", False):
            if open_:
                panel.setGeometry(self._center_host.rect())
                panel.show()
                panel.raise_()
                self._chrome_layer.raise_()
            return
        self._settings_open = open_
        if open_:
            geo = self._center_host.rect()
            if isinstance(panel, FrostGlassFrame):
                self._apply_panel_frost(panel, geo)
            panel.setGeometry(geo)
            panel.show()
            panel.raise_()
            self._chrome_layer.raise_()
            if animated:
                fade_overlay(panel, True, 160)
            return
        if animated and panel.isVisible():
            fade_overlay(panel, False, 140)
        else:
            panel.hide()

    def _set_editor_dock(self, open_: bool, *, animated: bool) -> None:
        """Slide Editor over the viewport — crop feel, GL widget never resizes."""
        if open_ == getattr(self, "_editor_dock_open", False):
            if open_:
                self.editor.setGeometry(self._editor_dock_rect(open_=True))
                self.editor.raise_()
                self._chrome_layer.raise_()
            elif self.editor is not None and self.editor.isVisible():
                # Mid-slide leftover (anim interrupted) — snap shut.
                self.editor.hide()
            return
        from ..util.hw import prefer_instant_panels

        if animated and prefer_instant_panels():
            animated = False
        self._editor_dock_open = open_
        ed = self.editor
        target = self._editor_dock_rect(open_=open_)

        def _chrome() -> None:
            self._reposition_viewer_chrome()

        if open_:
            # Snapshot frost before the dock covers the strip
            self._apply_panel_frost(ed, target)
            # start off-screen right, slide in — viewer underneath keeps its size
            start = self._editor_dock_rect(open_=False)
            ed.setFixedWidth(target.width())
            ed.setGeometry(start)
            ed.show()
            ed.raise_()
            self._chrome_layer.raise_()

            def _opened() -> None:
                ed.setGeometry(target)
                ed.raise_()
                self._chrome_layer.raise_()
                _chrome()

            if animated:
                animate_geometry(
                    ed, target, EDITOR_DOCK_MS, on_tick=_chrome, on_done=_opened
                )
            else:
                _opened()
            return

        def _closed() -> None:
            ed.hide()
            _chrome()

        if animated and ed.isVisible():
            animate_geometry(
                ed, target, EDITOR_DOCK_MS, on_tick=_chrome, on_done=_closed
            )
        else:
            ed.setGeometry(target)
            _closed()

    def _layout_viewer_pane(self) -> None:
        """Fill stack under floating chrome (no QLayout — it would restack over nav)."""
        pane = getattr(self, "_viewer_pane", None)
        stack = getattr(self, "_stack", None)
        if pane is None or stack is None:
            return
        stack.setGeometry(pane.rect())
        stack.lower()

    def _update_chrome_mask(self) -> None:
        """Only nav/HUD/shortcut hit-test — rest of layer lets orbit/pan reach GL."""
        layer = getattr(self, "_chrome_layer", None)
        if layer is None:
            return
        if not layer.isVisible():
            layer.clearMask()
            return
        region = QRegion()
        for w in (
            self._nav,
            self._bake_bar,
            self.pbr_hud,
            self._shortcut_bar,
        ):
            if w is not None and w.isVisible():
                region = region.united(QRegion(w.geometry()))
        # Empty mask on a raised AlwaysStackOnTop layer blocks HOME clicks on some Qt builds.
        if region.isEmpty():
            layer.clearMask()
            layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            layer.setMask(region)

    def _reposition_viewer_chrome(self) -> None:
        """Float top/bottom bars over the clear viewport strip (between frost panels)."""
        stack = getattr(self, "_stack", None)
        if stack is not None and stack.graphicsEffect() is not None:
            stack.setGraphicsEffect(None)
        # Always size hub/GL stack — HOME centering needs this before chrome exists.
        self._layout_viewer_pane()
        if not getattr(self, "_chrome_ready", False):
            return
        self._layout_side_panel()

        layer = getattr(self, "_chrome_layer", None)
        host = getattr(self, "_center_host", None)
        if layer is not None and host is not None:
            left = 0
            sp = getattr(self, "_side_panel", None)
            if (
                sp is not None
                and getattr(self, "_side_open", True)
                and sp.isVisible()
                and not getattr(self, "_settings_open", False)
            ):
                left = max(0, sp.geometry().right() + 4)
            dock_w = 0
            if self.editor.isVisible() and getattr(self, "_editor_dock_open", False):
                dock_w = max(0, host.width() - self.editor.geometry().x())
            layer.setGeometry(
                left, 0, max(1, host.width() - dock_w - left), host.height()
            )
            layer.show()
            if self.editor.isVisible():
                self.editor.raise_()
            if getattr(self, "_settings_open", False):
                panel = getattr(self, "_settings_panel", None)
                if panel is not None:
                    panel.raise_()
            layer.raise_()
            self._layout_panel_edge_btns()

        if hasattr(self, "_apply_studio_chrome"):
            self._apply_studio_chrome()
        if self._bake_busy:
            self._nav.hide()
            self._shortcut_bar.hide()
            self._bake_bar.reposition()
        else:
            self._bake_bar.hide()
            if self._studio_mode == "mesh":
                self._nav.reposition()
                # shortcut strip just above bottom nav
                bar = self._shortcut_bar
                bar.adjustSize()
                bw = (
                    min(layer.width() - 16, max(bar.sizeHint().width(), 200))
                    if layer
                    else 200
                )
                bar.setFixedWidth(max(120, bw))
                bx = max(0, ((layer.width() if layer else 0) - bar.width()) // 2)
                by = max(
                    4,
                    (layer.height() if layer else 0)
                    - self._nav.height()
                    - bar.height()
                    - 28,
                )
                bar.move(bx, by)
                bar.show()
                bar.raise_()
            else:
                self._shortcut_bar.hide()
                self._nav.hide()
        if self.pbr_hud.isVisible():
            self._reposition_pbr_hud()
        if self._nav.isVisible():
            self._nav._stack_pill()
        if self.pbr_hud.isVisible():
            self.pbr_hud._sync_pill(animate=False)
        self._update_chrome_mask()
        self._place_fps_hud()
        ed = getattr(self, "editor", None)
        if ed is not None and ed.isVisible():
            ed.raise_()
        self._layout_panel_edge_btns()
        if layer is not None:
            layer.raise_()
        if getattr(self, "_settings_open", False):
            panel = getattr(self, "_settings_panel", None)
            if panel is not None:
                panel.raise_()
        # Tab pie must stay above chrome/GL while armed
        if getattr(self, "_tab_pie_armed", False):
            pie = getattr(self, "_tab_pie", None) or (
                self._active_tab_pie() if hasattr(self, "_active_tab_pie") else None
            )
            if pie is not None and pie.isVisible():
                pie.setGeometry(
                    (getattr(self, "_center_host", None) or self).rect()
                )
                pie.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt API
        et = event.type()
        # Frameless edge resize — grab presses in the outer grip band.
        if (
            self.isActiveWindow()
            and not self.isMaximized()
            and et == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            local = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = edge_at(local, self.size(), EDGE_GRIP)
            if edges:
                bar = getattr(self, "_title_bar", None)
                # Title bar owns drag/move inside its capsule.
                if bar is None or not bar.geometry().contains(local):
                    wh = self.windowHandle()
                    if wh is not None:
                        wh.startSystemResize(edges)
                        return True
        # Steal Tab before Qt focus-chain / shortcuts (spinboxes were eating Tab)
        if self.isActiveWindow() and et == QEvent.Type.ShortcutOverride:
            key = event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and self._tab_opens_pie():
                event.accept()
                return True
            if key == Qt.Key.Key_Escape and self._tab_pie_armed:
                event.accept()
                return True
            # Own F3 so hidden-menuBar QAction + our KeyPress don't double-toggle.
            if key == Qt.Key.Key_F3 and not self._focus_wants_tab():
                event.accept()
                return True
        if self.isActiveWindow() and et in (
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
        ):
            key = event.key()
            if key == Qt.Key.Key_Escape and self._tab_pie_armed:
                self._cancel_tab_pie()
                return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and self._tab_opens_pie():
                if et == QEvent.Type.KeyPress and not event.isAutoRepeat() and not self._tab_pie_armed:
                    self._arm_tab_pie()
                    return True
                if et == QEvent.Type.KeyRelease and self._tab_pie_armed:
                    self._commit_tab_pie()
                    return True
            if (
                et == QEvent.Type.KeyPress
                and not event.isAutoRepeat()
                and not self._focus_wants_tab()
            ):
                if key == Qt.Key.Key_BracketLeft:
                    self._toggle_side_panel()
                    return True
                if key == Qt.Key.Key_BracketRight:
                    self._toggle_editor_panel()
                    return True
                if key == Qt.Key.Key_F3:
                    self._set_view_flag("_show_fps", not self._show_fps)
                    return True
        watch = (
            getattr(self, "_viewer_pane", None),
            getattr(self, "_center_host", None),
        )
        if obj in watch and obj is not None and et == QEvent.Type.Resize:
            self._layout_side_panel()
            self._reposition_viewer_chrome()
            if getattr(self, "_editor_dock_open", False) and self.editor.isVisible():
                self.editor.setGeometry(self._editor_dock_rect(open_=True))
            if getattr(self, "_settings_open", False):
                panel = getattr(self, "_settings_panel", None)
                if panel is not None:
                    panel.setGeometry(self._center_host.rect())
                    panel.raise_()
                    self._chrome_layer.raise_()
            # debounce frost re-grab while dragging the window
            if not hasattr(self, "_frost_resize_timer"):
                self._frost_resize_timer = QTimer(self)
                self._frost_resize_timer.setSingleShot(True)
                self._frost_resize_timer.timeout.connect(self._refresh_side_frost)
            self._frost_resize_timer.start(120)
        return super().eventFilter(obj, event)

    def _set_scene_att_ui_for_editor(self, in_editor: bool) -> None:
        """Keep Scene list visible; in Editor it links to the right dock."""
        block = getattr(self, "_scene_att_block", None)
        note = getattr(self, "_scene_editor_note", None)
        if block is not None:
            block.setVisible(True)
        if note is not None:
            note.hide()
        self.att_list.setEnabled(True)
        self.scene_mesh_list.setEnabled(True)
        if in_editor:
            self._on_editor_mode_changed(self.editor.current_mode())
        else:
            self._set_scene_list_mode("atts")
        self._sync_side_scroll_body()

    def _on_editor_mode_changed(self, mode: str) -> None:
        self._editor_mode = "meshes" if mode == "meshes" else "attachs"
        if not self._in_editor_page():
            return
        self._set_scene_list_mode("meshes" if mode == "meshes" else "atts")

    def _set_scene_list_mode(self, mode: str) -> None:
        """Show attachment or material names in left Scene tab."""
        self._scene_list_mode = mode if mode in ("atts", "meshes") else "atts"
        show_meshes = self._scene_list_mode == "meshes"
        self.att_list.setVisible(not show_meshes)
        self.scene_mesh_list.setVisible(show_meshes)
        bar = getattr(self, "_mesh_ds_bar", None)
        if bar is not None:
            bar.setVisible(show_meshes)
        title = getattr(self, "_scene_list_title", None)
        if title is not None:
            if show_meshes:
                title.setText("Meshes")
                title.setToolTip(
                    "Tick meshes, then Apply Double Sided. Click a name to edit on the right."
                )
            else:
                title.setText("Attachments (a.*)")
                title.setToolTip("Select an attachment — edit on the right Editor.")
        tip = getattr(self, "_scene_cap_tip", None)
        if tip is not None and self._in_editor_page():
            tip.setText(
                "Meshes → edit on right"
                if show_meshes
                else "a.* → edit on right · Alt+LMB pick in 3D"
            )
        self._sync_side_scroll_body()

    def _scene_mesh_checked_names(self) -> list[str]:
        names: list[str] = []
        lst = getattr(self, "scene_mesh_list", None)
        if lst is None:
            return names
        for i in range(lst.count()):
            item = lst.item(i)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            text = item.text().strip()
            if text:
                names.append(text)
        return names

    def _refresh_mesh_ds_count(self) -> None:
        btn = getattr(self, "_mesh_ds_apply", None)
        all_box = getattr(self, "_mesh_ds_all", None)
        if btn is None:
            return
        n = len(self._scene_mesh_checked_names())
        total = self.scene_mesh_list.count()
        btn.setText(f"Apply Double Sided ({n})")
        btn.setEnabled(n > 0)
        if all_box is not None:
            all_box.blockSignals(True)
            all_box.setChecked(total > 0 and n == total)
            all_box.blockSignals(False)

    def _on_scene_mesh_checks(self, _item: QListWidgetItem) -> None:
        self._refresh_mesh_ds_count()

    def _on_mesh_ds_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        lst = self.scene_mesh_list
        lst.blockSignals(True)
        for i in range(lst.count()):
            item = lst.item(i)
            if item is not None:
                item.setCheckState(state)
        lst.blockSignals(False)
        self._refresh_mesh_ds_count()

    def _apply_checked_double_sided(self) -> None:
        names = self._scene_mesh_checked_names()
        if not names:
            return
        page = getattr(self.editor, "meshes_page", None)
        if page is not None:
            page.note_two_sided(names, True)
        n = 0
        if self.view is not None:
            n = self.view.set_two_sided_for_materials(names, True)
            view = self.view
            QTimer.singleShot(0, view.update)
        else:
            from ..render.view3d import _two_sided_name_hit

            for part in self._scene.parts:
                if any(_two_sided_name_hit(part.name or "", raw) for raw in names):
                    part.two_sided = True
                    n += 1
        self._queue_two_sided(names, True)
        self._status.showMessage(
            f"Double Sided on · {n or len(names)} part(s) in preview — Save to keep"
        )

    def _refill_scene_mesh_list(self) -> None:
        names = self.editor.meshes_page.material_names()
        if not names:
            names = [p.name for p in self._scene.parts if p.name]
        checked = set(self._scene_mesh_checked_names())
        keep = self.scene_mesh_list.currentRow()
        self._suppress_mesh_hl += 1
        self.scene_mesh_list.blockSignals(True)
        try:
            self.scene_mesh_list.clear()
            for name in names:
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if name in checked
                    else Qt.CheckState.Unchecked
                )
                self.scene_mesh_list.addItem(item)
        finally:
            self.scene_mesh_list.blockSignals(False)
        try:
            if names:
                row = keep if 0 <= keep < len(names) else 0
                self.scene_mesh_list.setCurrentRow(row)
        finally:
            self._suppress_mesh_hl -= 1
        self._refresh_mesh_ds_count()
        _refit_side_table(self.scene_mesh_list)

    def _on_scene_mesh_row(self, row: int) -> None:
        if self._in_editor_page():
            if self.editor.current_mode() != "meshes":
                self.editor.show_meshes_tab()
            self.editor.meshes_page.select_row(row)
        if row < 0:
            self._set_mesh_hl("part", set(), frame=False)
            self._status.showMessage("")
            return
        name = self._mesh_part_name_at(row)
        self._set_mesh_hl("part", {name} if name else set(), frame=True)
        if self._mesh_hl_blocked():
            self._status.showMessage(name)

    def _on_editor_mesh_selected(self, row: int) -> None:
        if self.scene_mesh_list.currentRow() != row:
            self.scene_mesh_list.blockSignals(True)
            self.scene_mesh_list.setCurrentRow(row)
            self.scene_mesh_list.blockSignals(False)

    def _sync_scene_mesh_list_labels(self, index: int, fields: dict) -> None:
        name = fields.get("name")
        if not name:
            return
        item = self.scene_mesh_list.item(index)
        if item is not None:
            item.setText(name)

    def _editor_cache_key(self) -> str:
        path = self._mesh_path
        n_att = len(self._scene.attachments)
        n_parts = len(self._scene.parts)
        src = str(path.resolve()) if path is not None else self._scene.source
        return f"{src}|{self._scene.kind}|{n_att}|{n_parts}"

    def _refresh_editor_dock(self, *, force: bool = True) -> None:
        """Sync Editor dock. ``force=False`` skips list rebuild when already populated."""
        self._refill_att_list(self._scene)
        key = self._editor_cache_key()
        if force or key != self._editor_populated_key:
            # never reload buffer while dirty — would wipe unsaved edits
            if self._tzmf_bytes is None or (force and not self._tzmf_dirty):
                self._load_tzmf_buffer()
            self._populate_meshes_page()
            self._populate_attachments_page()
            self._refill_scene_mesh_list()
            self._editor_populated_key = key
        self._update_editor_writability()
        self._sync_editor_texture_list()
        self._strip_sidebar_tab_focus()

    def _update_editor_writability(self) -> None:
        im_ok = self._im_doc is not None and self._scene.kind == "im"
        tz_ok = self._tzmf_bytes is not None and self._scene.kind == "trainzmesh"
        self.editor.set_im_writable(im_ok)
        if tz_ok:
            self.editor.set_trainzmesh_writable(True)
        if im_ok:
            self.editor.att_tip.setText(
                ".im ATCH — LMB drag in 3D · Shift=fine · Apply / Save"
            )
        elif tz_ok:
            self.editor.att_tip.setText(
                ".trainzmesh — pick a.* / mesh · Z-up Location · Save in Studio"
            )
        elif len(self._mesh_paths) > 1 or self._scene.kind == "multi":
            self.editor.att_tip.setText("Multi-mesh — Save needs a single .im / .trainzmesh")
        else:
            self.editor.att_tip.setText("Pick an item · Save when writable")

    def _load_tzmf_buffer(self) -> None:
        """Load .trainzmesh bytes for in-session edit (None if not applicable)."""
        self._tzmf_bytes = None
        self._tzmf_dirty = False
        self._tzmf_mats_cache = []
        path = self._mesh_path
        if (
            path is not None
            and self._scene.kind == "trainzmesh"
            and path.suffix.lower() == ".trainzmesh"
            and len(self._mesh_paths) <= 1
        ):
            raw = getattr(self._scene, "source_bytes", None)
            if raw is None and path.is_file():
                try:
                    raw = path.read_bytes()
                except OSError:
                    return
            if raw is None:
                return
            self._tzmf_bytes = bytearray(raw)
            # Drop shared ref — Editor mutates its own bytearray copy.
            self._scene.source_bytes = None
            from ..io.tzmf_edit import parse_materials

            self._tzmf_mats_cache = parse_materials(self._tzmf_bytes)

    def _capture_snapshot(self, label: str) -> EditSnapshot:
        atts: list[tuple[str, tuple[float, float, float], tuple[float, ...]]] = []
        for a in self._scene.attachments:
            atts.append((a.name, tuple(a.pos), tuple(a.orient)))  # type: ignore[arg-type]
        parts: list[tuple[str, str, str, str, str, tuple[float, float, float]]] = []
        for p in self._scene.parts:
            c = p.color if p.color is not None else (1.0, 1.0, 1.0)
            parts.append(
                (
                    p.name or "",
                    p.material_type or "",
                    p.albedo_ref or "",
                    p.normal_ref or "",
                    p.parameter_ref or "",
                    (float(c[0]), float(c[1]), float(c[2])),
                )
            )
        return EditSnapshot(
            label=label,
            tzmf_z=EditSnapshot.pack_tzmf(self._tzmf_bytes),
            tzmf_dirty=bool(self._tzmf_dirty),
            atts=atts,
            parts=parts,
        )

    def _push_history(self, label: str, *, coalesce: bool = False) -> None:
        if self._tzmf_bytes is None and not self._scene.attachments:
            return
        self._history.push(self._capture_snapshot(label), coalesce=coalesce)
        self._refresh_history_actions()

    def _refresh_history_actions(self) -> None:
        if self._undo_act is not None:
            ok = self._history.can_undo()
            self._undo_act.setEnabled(ok)
            lab = self._history.undo_label()
            self._undo_act.setText(f"Undo {lab}" if ok and lab else "Undo")
        if self._redo_act is not None:
            ok = self._history.can_redo()
            self._redo_act.setEnabled(ok)
            lab = self._history.redo_label()
            self._redo_act.setText(f"Redo {lab}" if ok and lab else "Redo")

    def _restore_snapshot(self, snap: EditSnapshot) -> None:
        from ..io.scene import Attachment as SceneAtt

        if snap.tzmf_z is not None:
            self._tzmf_bytes = snap.unpack_tzmf()
            self._tzmf_dirty = snap.tzmf_dirty
            if self._tzmf_bytes is not None:
                from ..io.tzmf_edit import parse_materials

                self._tzmf_mats_cache = parse_materials(self._tzmf_bytes)
        else:
            self._tzmf_dirty = snap.tzmf_dirty

        restored: list = []
        for name, pos, orient in snap.atts:
            restored.append(SceneAtt(name=name, pos=pos, orient=orient))  # type: ignore[arg-type]
        self._scene.attachments = restored
        if self._im_doc is not None and self._scene.kind == "im":
            for i, a in enumerate(restored):
                if i < len(self._im_doc.atts):
                    try:
                        self._im_doc.update_one(
                            i, name=a.name, pos=a.pos, orient=a.orient
                        )
                    except Exception:
                        pass

        folder = Path(self._mesh_path).parent if self._mesh_path else Path()
        try:
            from ..lib.trainzmesh_viewer.textures import resolve_texture_path
        except ImportError:
            resolve_texture_path = None  # type: ignore[assignment]
        for i, fields in enumerate(snap.parts):
            if i >= len(self._scene.parts):
                break
            part = self._scene.parts[i]
            name, mtype, alb, nrm, prm, color = fields
            part.name = name
            part.material_type = mtype
            part.albedo_ref = alb
            part.normal_ref = nrm
            part.parameter_ref = prm
            part.color = color
            if resolve_texture_path is not None:
                if alb:
                    part.albedo_path = resolve_texture_path(str(folder), alb)
                if nrm:
                    part.normal_path = resolve_texture_path(str(folder), nrm)
                if prm:
                    part.parameter_path = resolve_texture_path(str(folder), prm)

        self._refill_att_list(self._scene)
        self._editor_populated_key = ""
        self._refresh_editor_dock(force=True)
        if self.view is not None:
            self.view.set_scene(self._scene)
        if snap.tzmf_dirty:
            self._mark_edited()
        else:
            self._tzmf_dirty = False
            self._autosave_pending = False
        self._refresh_history_actions()

    def _undo_edit(self) -> None:
        if not self._history.can_undo():
            return
        current = self._capture_snapshot(self._history.undo_label() or "edit")
        snap = self._history.undo(current)
        if snap is None:
            return
        self._restore_snapshot(snap)
        self._status.showMessage(f"Undo · {snap.label}")

    def _redo_edit(self) -> None:
        if not self._history.can_redo():
            return
        current = self._capture_snapshot(self._history.redo_label() or "edit")
        snap = self._history.redo(current)
        if snap is None:
            return
        self._restore_snapshot(snap)
        self._status.showMessage(f"Redo · {snap.label}")

    def _collect_project_state(self) -> ProjectState:
        page = getattr(self, "_page", "editor") or "editor"
        tab = "attachments"
        try:
            tab = self.editor.current_mode()
        except Exception:
            pass
        return ProjectState(
            mesh_paths=[str(p) for p in self._mesh_paths],
            studio_page=page,
            editor_tab=tab,
            sel_att=self.att_list.currentRow() if hasattr(self, "att_list") else -1,
            sel_mesh=(
                self.scene_mesh_list.currentRow()
                if hasattr(self, "scene_mesh_list")
                else -1
            ),
            theme=self._theme_mode,
            tzmf_dirty=bool(self._tzmf_dirty),
            buffer=bytes(self._tzmf_bytes) if self._tzmf_bytes is not None else None,
            project_path=str(self._project_path) if self._project_path else None,
        )

    def _mark_edited(self) -> None:
        """Flag dirty + schedule the next 1‑minute autosave (no spam writes)."""
        self._tzmf_dirty = True
        self._autosave_pending = True

    def _autosave_tick(self) -> None:
        """1‑minute timer: write only if something changed since last autosave."""
        if not self._autosave_pending:
            return
        if self._tzmf_bytes is None and not self._mesh_paths:
            self._autosave_pending = False
            return
        try:
            state = self._collect_project_state()
            write_crash_backup(state)
            if self._project_path is not None:
                save_project(self._project_path, state)
                self._status.showMessage(
                    f"Autosaved · {self._project_path.name}", 2500
                )
            else:
                self._status.showMessage("Autosaved recovery checkpoint", 2500)
        except OSError:
            return
        self._autosave_pending = False

    def _save_project_as(self) -> None:
        start = str(self._project_path or self._mesh_path or Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            start,
            "MSTN Trainz Studio Project (*.mtzs)",
        )
        if not path:
            return
        out = save_project(Path(path), self._collect_project_state())
        self._project_path = out
        self._autosave_pending = False
        self._status.showMessage(f"Project saved · {out.name}")
        self.setWindowTitle(f"MSTN Trainz Studio — {out.stem}")

    def _save_project(self) -> None:
        if self._project_path is None:
            self._save_project_as()
            return
        save_project(self._project_path, self._collect_project_state())
        self._autosave_pending = False
        self._status.showMessage(f"Project saved · {self._project_path.name}")

    def _open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(self._project_path or Path.home()),
            "MSTN Trainz Studio Project (*.mtzs)",
        )
        if not path:
            return
        self._open_project(Path(path))

    def _open_project(self, path: Path) -> None:
        try:
            state = load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "Open Project", str(e))
            return
        self._project_path = path
        self._apply_project_state(state)

    def _apply_project_state(self, state: ProjectState) -> None:
        paths = [Path(p) for p in state.mesh_paths if p]
        existing = [p for p in paths if p.is_file()]
        if not existing:
            QMessageBox.warning(
                self,
                "Open Project",
                "No mesh files from this project are still on disk.",
            )
            return
        self._pending_project = state
        self._history.clear()
        self._refresh_history_actions()
        if state.theme in ("dark", "light") and state.theme != self._theme_mode:
            self._theme_mode = state.theme
            self._apply_theme_mode()
        self.open_paths(existing, mode="replace")

    def _finish_pending_project(self) -> None:
        state = self._pending_project
        self._pending_project = None
        if state is None:
            return
        if state.buffer is not None and self._tzmf_bytes is not None:
            self._tzmf_bytes = bytearray(state.buffer)
            if state.tzmf_dirty:
                self._mark_edited()
            else:
                self._tzmf_dirty = False
                self._autosave_pending = False
            from ..io.tzmf_edit import parse_attachment_records, parse_materials
            from ..io.scene import Attachment as SceneAtt

            self._tzmf_mats_cache = parse_materials(self._tzmf_bytes)
            recs = parse_attachment_records(self._tzmf_bytes)
            from ..io.tzmf_edit import zup_quat_to_orient

            self._scene.attachments = [
                SceneAtt(
                    name=r.name,
                    pos=r.pos_zup,
                    orient=zup_quat_to_orient(*r.quat_zup),
                )
                for r in recs
            ]
            # refresh part preview colors/refs from materials
            folder = Path(self._mesh_path).parent if self._mesh_path else Path()
            try:
                from ..lib.trainzmesh_viewer.textures import resolve_texture_path
            except ImportError:
                resolve_texture_path = None  # type: ignore[assignment]
            from ..io.tzmf_edit import materials_by_tail

            mats_at = materials_by_tail(self._tzmf_mats_cache)
            for part in self._scene.parts:
                mat = mats_at.get(int(getattr(part, "chunk_tail", -1)))
                if mat is None:
                    continue
                part.name = mat.name
                part.material_type = mat.type_name
                part.color = (mat.color[0], mat.color[1], mat.color[2])
                tex = {t.key: t.value for t in mat.textures}
                if resolve_texture_path is not None:
                    if "txAlbedo" in tex:
                        part.albedo_ref = tex["txAlbedo"]
                        part.albedo_path = resolve_texture_path(
                            str(folder), tex["txAlbedo"]
                        )
                    if "txNormal" in tex:
                        part.normal_ref = tex["txNormal"]
                        part.normal_path = resolve_texture_path(
                            str(folder), tex["txNormal"]
                        )
                    if "txParameters" in tex:
                        part.parameter_ref = tex["txParameters"]
                        part.parameter_path = resolve_texture_path(
                            str(folder), tex["txParameters"]
                        )
            self._refill_att_list(self._scene)
            self._editor_populated_key = ""
            self._refresh_editor_dock(force=True)
            if self.view is not None:
                self.view.set_scene(self._scene)

        if state.editor_tab == "meshes":
            self.editor.show_meshes_tab()
        else:
            self.editor.show_attachments_tab()
        if state.sel_att >= 0:
            self.att_list.setCurrentRow(state.sel_att)
        if state.sel_mesh >= 0 and hasattr(self, "scene_mesh_list"):
            self.scene_mesh_list.setCurrentRow(state.sel_mesh)
        if state.studio_page and state.studio_page != "home":
            try:
                self._set_page(state.studio_page)
            except Exception:
                pass
        self._status.showMessage(
            f"Project restored · {Path(state.project_path or '').name or 'session'}"
        )

    def _offer_crash_restore(self) -> None:
        if not has_crash_recovery():
            return
        state = load_crash_backup()
        if state is None or not state.mesh_paths:
            clear_crash_backup()
            return
        names = ", ".join(Path(p).name for p in state.mesh_paths[:3])
        ans = QMessageBox.question(
            self,
            "Recover unsaved work?",
            f"Found a self-backup from a previous session:\n{names}\n\n"
            "Restore unsaved edits?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            clear_crash_backup()
            return
        self._apply_project_state(state)

    def _populate_meshes_page(self) -> None:
        page = self.editor.meshes_page
        sc = self._scene
        mins, maxs = (None, None)
        b = sc.bounds()
        if b is not None:
            mins, maxs = b
        bbox = "—"
        if mins is not None and maxs is not None:
            bbox = (
                f"x1:{mins[0]:.6f}  y1:{mins[1]:.6f}  z1:{mins[2]:.6f}\n"
                f"x2:{maxs[0]:.6f}  y2:{maxs[1]:.6f}  z2:{maxs[2]:.6f}"
            )
        page.set_info(version=2, tris=sc.face_count, bbox=bbox, flags=0)
        mats = self._tzmf_mats_cache
        two = {p.name: bool(p.two_sided) for p in sc.parts if p.name}
        if mats:
            page.set_materials(mats, two_sided=two)
        else:
            page.clear()

    def _populate_attachments_page(self) -> None:
        from ..io.tzmf_edit import AttRecord, parse_attachment_records, _mat3_to_quat
        import numpy as np

        page = self.editor.attachments_page
        # Right-hand fields follow the scene list. A tzMF byte scan can hit a
        # stray ``a.`` inside geometry; that must not fill Name when the list is empty.
        scene_names = {a.name for a in self._scene.attachments if a.name}
        if not scene_names:
            page.clear()
            return
        if self._tzmf_bytes is not None:
            recs = [
                r
                for r in parse_attachment_records(self._tzmf_bytes)
                if r.name in scene_names
            ]
            if recs:
                page.set_attachments(recs)
                return
        # Scene is already Trainz Z-up
        recs: list[AttRecord] = []
        for a in self._scene.attachments:
            m = np.asarray(a.orient, dtype=np.float64).reshape(3, 3)
            recs.append(
                AttRecord(
                    name=a.name,
                    name_off=-1,
                    floats_off=-1,
                    pos_zup=tuple(float(v) for v in a.pos),  # type: ignore[arg-type]
                    quat_zup=_mat3_to_quat(m),
                )
            )
        page.set_attachments(recs)

    def _on_mesh_material_changed(self, index: int, fields: dict) -> None:
        if self._tzmf_bytes is None:
            self._status.showMessage("Material edit needs a single .trainzmesh")
            return
        from ..io.tzmf_edit import apply_material_edits, parse_materials

        try:
            from ..lib.trainzmesh_viewer.textures import resolve_texture_path
        except ImportError:
            resolve_texture_path = None  # type: ignore[assignment]

        mats = parse_materials(self._tzmf_bytes)
        if index < 0 or index >= len(mats):
            return
        mat = mats[index]
        self._push_history(f"Material {fields.get('name') or index}", coalesce=True)
        try:
            self._tzmf_bytes = apply_material_edits(
                self._tzmf_bytes,
                mat,
                type_name=fields.get("type_name"),
                name=fields.get("name"),
                color=fields.get("color"),
                emissive=fields.get("emissive"),
                specular=fields.get("specular"),
                spec_power=fields.get("spec_power"),
                textures=fields.get("textures"),
            )
        except Exception as e:
            QMessageBox.warning(self, "Material edit", str(e))
            return
        self._mark_edited()
        # live preview: update matching MeshPart refs
        if index < len(self._scene.parts):
            part = self._scene.parts[index]
            part.name = fields.get("name") or part.name
            part.material_type = fields.get("type_name") or part.material_type
            tex = fields.get("textures") or {}
            folder = Path(self._mesh_path).parent if self._mesh_path else Path()
            if resolve_texture_path is not None:
                if "txAlbedo" in tex:
                    part.albedo_ref = tex["txAlbedo"]
                    part.albedo_path = resolve_texture_path(str(folder), tex["txAlbedo"])
                if "txNormal" in tex:
                    part.normal_ref = tex["txNormal"]
                    part.normal_path = resolve_texture_path(str(folder), tex["txNormal"])
                if "txParameters" in tex:
                    part.parameter_ref = tex["txParameters"]
                    part.parameter_path = resolve_texture_path(
                        str(folder), tex["txParameters"]
                    )
            if fields.get("color"):
                c = fields["color"]
                part.color = (float(c[0]), float(c[1]), float(c[2]))
        # debounce GL rebuild — typing must not freeze the dock
        self._mat_preview_timer.start()
        self._sync_scene_mesh_list_labels(index, fields)
        self._status.showMessage(
            f"Material «{fields.get('name', '?')}» edited · Save to write .trainzmesh"
        )

    def _flush_mat_preview(self) -> None:
        if self.view is not None:
            self.view.set_scene(self._scene)

    def _on_mesh_two_sided_changed(self, _index: int, on: bool, material: str) -> None:
        # _index is the material-list row, not the geometry chunk — match by name.
        name = (material or "").strip()
        n = 0
        if self.view is not None and name:
            # Live cull in the current preview. Camera and buffers stay put.
            n = self.view.set_two_sided_for_material(name, on)
            view = self.view
            QTimer.singleShot(0, view.update)
        elif name:
            for part in self._scene.parts:
                if (part.name or "").strip().lower() == name.lower():
                    part.two_sided = on
                    n += 1
        if name:
            self._queue_two_sided([name], on)
        flag = "on" if on else "off"
        if n:
            self._status.showMessage(
                f"Double Sided {flag} · {name} · {n} part(s) in preview — Save to keep"
            )
        else:
            self._status.showMessage(
                f"Double Sided {flag} · {name or 'mesh'} · no geometry in preview"
            )

    def _queue_two_sided(self, names: list[str], on: bool) -> None:
        """Remember flags for the next Editor Save. Does not touch the mesh file."""
        pending = getattr(self, "_two_sided_pending", None)
        if pending is None:
            pending = {}
            self._two_sided_pending = pending
        for name in names:
            key = (name or "").strip()
            if key:
                pending[key] = bool(on)

    def _flush_two_sided_meta(self, mesh_path: Path | None = None) -> None:
        """Write queued Double Sided flags beside the mesh. No-op until Save."""
        pending = getattr(self, "_two_sided_pending", None) or {}
        path = self._mesh_path if mesh_path is None else mesh_path
        if not pending or path is None:
            return
        from ..io.mesh_meta import mesh_meta_path, write_two_sided_map

        try:
            write_two_sided_map(mesh_meta_path(path), dict(pending))
        except OSError:
            return
        pending.clear()

    def _on_att_tree_changed(self, index: int, fields: dict) -> None:
        from ..io.scene import Attachment as SceneAtt
        from ..io.tzmf_edit import (
            parse_attachment_records,
            set_attachment_yup,
            zup_quat_to_orient,
        )

        pos_z = tuple(float(v) for v in fields["pos_zup"])
        quat_z = tuple(float(v) for v in fields["quat_zup"])
        orient = zup_quat_to_orient(*quat_z)
        name = fields.get("name") or f"a.{index}"
        self._push_history(f"Attachment {name}", coalesce=True)
        if 0 <= index < len(self._scene.attachments):
            self._scene.attachments[index] = SceneAtt(
                name=name, pos=pos_z, orient=orient  # type: ignore[arg-type]
            )
        if self._tzmf_bytes is not None:
            recs = parse_attachment_records(self._tzmf_bytes)
            if 0 <= index < len(recs):
                rec = recs[index]
                try:
                    if name != rec.name and rec.name_off >= 0:
                        from ..io.tzmf_edit import rename_attachment

                        self._tzmf_bytes = rename_attachment(
                            self._tzmf_bytes, rec, name
                        )
                        recs = parse_attachment_records(self._tzmf_bytes)
                        rec = recs[index]
                    set_attachment_yup(
                        self._tzmf_bytes,
                        rec,
                        pos_zup=pos_z,  # type: ignore[arg-type]
                        quat_yup=quat_z,  # file / MeshEditor Z-up quat
                    )
                    self._mark_edited()
                except Exception as e:
                    QMessageBox.warning(self, "Attachment edit", str(e))
                    return
        if self._im_doc is not None and self._scene.kind == "im":
            try:
                self._im_doc.update_one(index, name=name, pos=pos_z, orient=orient)
            except Exception:
                pass
        if self.view is not None:
            self.view._scene.attachments = self._scene.attachments
            self.view.update()
        # hidden spinboxes track Trainz Z-up (same as viewport)
        self._att_x.blockSignals(True)
        self._att_y.blockSignals(True)
        self._att_z.blockSignals(True)
        self._att_name.blockSignals(True)
        self._att_x.setValue(pos_z[0])
        self._att_y.setValue(pos_z[1])
        self._att_z.setValue(pos_z[2])
        self._att_name.setText(name)
        self._att_x.blockSignals(False)
        self._att_y.blockSignals(False)
        self._att_z.blockSignals(False)
        self._att_name.blockSignals(False)
        # sync left Scene attachment label
        item = self.att_list.item(index)
        if item is not None:
            item.setText(name)
            item.setData(Qt.ItemDataRole.UserRole, self._scene.attachments[index])
        self._status.showMessage(f"{name}  Z-up {pos_z} · quat {quat_z}")

    def _sync_editor_texture_list(self, *, select: Path | None = None) -> None:
        """Fill Editor → Texture browser from mesh folders + scene map refs."""
        paths: list[Path] = []
        if self._scene.parts or self._mesh_paths:
            entries = self._collect_tex_entries(self._scene, self._mesh_folder_map())
            for e in entries:
                if e.path is not None and e.path.is_file():
                    if e.path.name.lower().endswith(".texture.txt"):
                        paths.append(e.path)
            for folder in self._mesh_folder_map().values():
                try:
                    for p in folder.glob("*.texture.txt"):
                        if p.is_file():
                            paths.append(p)
                except OSError:
                    pass
        prefer = select or self._selected_texture_txt() or self.editor.texture.path
        self.editor.texture.set_files(paths, select=prefer)

    def _place_fps_hud(self) -> None:
        """Pin the F3 chip to the top-right of the clear viewport.

        The GL widget stays full-bleed under the Editor dock, so a chip glued
        to the widget's right edge sits under the sidebar. Track the dock's
        left edge and slide the chip with it.
        """
        view = getattr(self, "view", None)
        host = getattr(self, "_center_host", None)
        if view is None or host is None or not hasattr(view, "fps_chip"):
            return
        chip = view.fps_chip
        mesh = getattr(self, "_studio_mode", "") == "mesh"
        want = bool(
            getattr(view, "_show_fps", False)
            and mesh
            and view.isVisible()
            and not getattr(self, "_settings_open", False)
        )
        view._fps_suppressed = not want
        if chip.parentWidget() is not host:
            chip.setParent(host)
        # Off the GL widget, this flag keeps the chip above the native viewport.
        chip.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        if not want:
            chip.hide()
            return
        dock_left = None
        ed = getattr(self, "editor", None)
        if ed is not None and ed.isVisible():
            dock_left = int(ed.geometry().x())
        left_min = 12
        sp = getattr(self, "_side_panel", None)
        if (
            sp is not None
            and getattr(self, "_side_open", True)
            and sp.isVisible()
        ):
            left_min = max(left_min, int(sp.geometry().right()) + 8)
        view.set_fps_place(host.width(), dock_left, left_min)
        if chip.hud_text():
            chip.show()
            view.apply_fps_place()
        # Chip is AlwaysStackOnTop (so the GL hwnd cannot cover it). Keep chrome above it.
        layer = getattr(self, "_chrome_layer", None)
        if layer is not None and layer.isVisible():
            layer.raise_()
        if getattr(self, "_settings_open", False):
            panel = getattr(self, "_settings_panel", None)
            if panel is not None and panel.isVisible():
                panel.raise_()

    def _reposition_pbr_hud(self) -> None:
        host = self.pbr_hud.parentWidget() or self._viewer_pane
        self.pbr_hud.adjustSize()
        w = max(self.pbr_hud.sizeHint().width(), 320)
        self.pbr_hud.setFixedWidth(w)
        x = (host.width() - w) // 2
        # Chrome layer already starts under TITLE_CONTENT_INSET — only a small gap.
        y = 4
        self.pbr_hud.move(max(8, x), y)
        self.pbr_hud.show()
        self.pbr_hud.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_viewer_pane()
        self._reposition_viewer_chrome()
        self._reposition_title_bar()
        if hasattr(self, "_overlay") and self._overlay.isVisible():
            self._overlay.setGeometry(self.rect())
            self._overlay.raise_()
            bar = getattr(self, "_title_bar", None)
            if bar is not None:
                bar.raise_()
        reveal = getattr(self, "_hub_reveal", None)
        if reveal is not None and reveal.isVisible():
            host = self._hub_reveal_host()
            if host is not None:
                tl = host.mapTo(self, QPoint(0, 0))
                reveal.setGeometry(QRect(tl, host.size()))
            reveal.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._layout_viewer_pane()
        QTimer.singleShot(0, self._reposition_viewer_chrome)
        QTimer.singleShot(0, self._reposition_title_bar)

    # ── overlay / busy / GL ──────────────────────────────────

    def _capture_overlay_frost(self) -> QPixmap:
        """Blur central UI (overlay is a MainWindow child — not in this grab)."""
        host = self.centralWidget()
        if host is None or host.width() < 8 or host.height() < 8:
            return QPixmap()
        try:
            raw = host.grab().toImage()
        except Exception:
            return QPixmap()
        return make_frost_pixmap(raw)

    def _show_overlay(
        self,
        stage: str,
        *,
        brand: str | None = None,
        pct: int = 0,
        instant: bool = False,
        frost: bool = True,
    ) -> None:
        if brand is not None:
            self._overlay.set_brand(brand)
        self._overlay.set_stage(stage, pct)
        self._overlay.setGeometry(self.rect())
        if frost:
            self._overlay.set_frost(self._capture_overlay_frost())
        # Drop leftover opacity effect so next show isn't stuck at 0.
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        eff = self._overlay.graphicsEffect()
        if isinstance(eff, QGraphicsOpacityEffect):
            self._overlay.setGraphicsEffect(None)
        self._overlay.show()
        self._overlay.raise_()
        if instant:
            self._overlay.update()
        else:
            fade_overlay(self._overlay, True, 120)
        QApplication.processEvents()

    def _hide_overlay(self) -> None:
        from ..util.hw import prefer_light_boot_frost

        # Low-end: snap off — fade + frost composite felt sticky after warm.
        if prefer_light_boot_frost():
            self._overlay.hide()
            self._overlay.set_frost(None)
        else:
            fade_overlay(self._overlay, False, 100)
        # Safety: LoadWorker used to top out at 99% — never leave toast stuck.
        hub = getattr(self, "_toasts", None)
        if hub is not None:
            hub.finish()

    def _on_load_progress(self, stage: str, pct: int) -> None:
        self._overlay.set_brand("Mesh Studio")
        self._overlay.set_stage(stage, pct)
        # % in the status line → StudioStatusBar.progress_noticed → toast bubble
        self._status.showMessage(f"{stage}  {max(0, min(100, int(pct)))}%")
        QApplication.processEvents()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if not getattr(self, "_chrome_ready", False):
            return
        self._open_btn.setEnabled(not busy)
        self._folder_btn.setEnabled(not busy)
        for b in getattr(self, "_welcome_btns", ()):
            b.setEnabled(not busy)
        self.menuBar().setEnabled(not busy)

    def _ensure_gl(self) -> bool:
        if self.view is not None:
            return True
        self._overlay.set_stage("Creating 3D view…", 96)
        QApplication.processEvents()
        try:
            from ..render.view3d import MeshView

            self.view = MeshView()
            self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.view.set_clear_color(palette(self._theme_mode).gl_clear)
            self.view.set_debug_mode(self._debug_mode)
            self.view.set_flip_texture_v(self._flip_texture_v)
            self.view.set_face_orientation(self._face_orient)
            self.view._show_axes = self._show_axes
            self.view._show_grid = self._show_grid
            self.view._show_atts = self._show_atts
            self.view._show_corner_gizmo = self._show_corner_gizmo
            self.view.set_show_fps(self._show_fps)
            self.view._fps_host_hook = self._place_fps_hud
            set_glass_dark(self.view.fps_chip, self._theme_mode != "light")
            self.view.attachment_moved.connect(self._on_att_viewport_moved)
            self.view.attachment_drag_started.connect(self._on_att_viewport_drag_started)
            self.view.attachment_drag_finished.connect(self._on_att_viewport_drag_finished)
            self.view.attachment_picked.connect(self._on_att_viewport_picked)
            while self._gl_layout.count():
                item = self._gl_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            self._gl_layout.addWidget(self.view)
            self._push_lights_to_view()
            self._push_lamps_to_view()
            QTimer.singleShot(0, self._reposition_viewer_chrome)
            QTimer.singleShot(120, self._refresh_side_frost)
            return True
        except Exception as e:
            QMessageBox.warning(self, "OpenGL", f"3D view unavailable:\n{e}")
            self._status.showMessage("OpenGL failed")
            return False

    def _on_light_toggle(self, index: int, on: bool) -> None:
        if self.view is not None:
            self.view.set_light_enabled(index, on)
        cb = self._light_checks[index]
        pulse_checkbox(cb)

    def _sync_sun_ui_enabled(self) -> None:
        sun = self._sun_mode_cb.isChecked()
        for w in (
            self._sun_az,
            self._sun_el,
            self._sun_int,
            self._sun_az_lab,
            self._sun_el_lab,
            self._sun_int_lab,
        ):
            w.setEnabled(sun)
        if hasattr(self, "_array_lights_host"):
            self._array_lights_host.setEnabled(not sun)

    def _push_lights_to_view(self) -> None:
        if self.view is None:
            return
        self.view.set_sun(
            self._sun_mode_cb.isChecked(),
            float(self._sun_az.value()),
            float(self._sun_el.value()),
            self._sun_int.value() / 100.0,
        )
        self.view.set_emissive_scale(self._emis_slider.value() / 100.0)
        for i, cb in enumerate(self._light_checks):
            self.view.set_light_enabled(i, cb.isChecked())

    def _on_sun_mode(self, on: bool) -> None:
        self._sun_mode = bool(on)
        self._sync_sun_ui_enabled()
        self._push_lights_to_view()
        self._push_lamps_to_view()
        if on:
            self._status.showMessage("Sun mode on")
        else:
            self._status.showMessage("Sun off — moonlight + cabin lamps")

    def _on_sun_params(self, _v: int = 0) -> None:
        self._sun_az_lab.setText(f"Azimuth {self._sun_az.value()}°")
        self._sun_el_lab.setText(f"Elevation {self._sun_el.value()}°")
        self._sun_int_lab.setText(f"Intensity {self._sun_int.value() / 100.0:.2f}")
        self._push_lights_to_view()

    def _on_emissive_boost(self, v: int) -> None:
        f = v / 100.0
        self._emissive_boost = f
        self._emis_lab.setText(f"Emissive boost {f:.2f} (preview only)")
        if self.view is not None:
            self.view.set_emissive_scale(f)

    # ── lamps (onetex surface glow) ─────────────────────────

    def _selected_lamps(self) -> list[Lamp]:
        keys = set()
        for it in self.lamp_tree.selectedItems():
            uid = str(it.data(0, Qt.ItemDataRole.UserRole) or "")
            if uid:
                keys.add(uid)
        return [L for L in self._lamps if lamp_uid(L.mesh_key, L.part_id) in keys]

    def _selected_lamp(self) -> Lamp | None:
        sel = self._selected_lamps()
        return sel[0] if sel else None

    def _refill_lamp_list(self, select_stem: str | None = None) -> None:
        prev = {
            str(it.data(0, Qt.ItemDataRole.UserRole) or "")
            for it in self.lamp_tree.selectedItems()
        }
        prev.discard("")
        if select_stem:
            for L in self._lamps:
                if L.stem == select_stem:
                    prev.add(lamp_uid(L.mesh_key, L.part_id))
        self._lamp_block = True
        self.lamp_tree.clear()
        for L in self._lamps:
            mark = "●" if L.enabled else "○"
            name = L.label or L.part_id or L.stem
            # strip mesh suffix from label if shown in col 1
            short = name.split(" @ ")[0] if " @ " in name else name
            item = QTreeWidgetItem([f"{mark}  {short}", L.mesh_key or "—", L.stem])
            item.setData(0, Qt.ItemDataRole.UserRole, lamp_uid(L.mesh_key, L.part_id))
            item.setData(0, ROLE_MESH_KEY, L.mesh_key)
            item.setToolTip(0, f"{L.label}\npos {tuple(round(x, 3) for x in L.pos)}")
            self.lamp_tree.addTopLevelItem(item)
        self._lamp_block = False
        if prev:
            self._lamp_block = True
            for i in range(self.lamp_tree.topLevelItemCount()):
                it = self.lamp_tree.topLevelItem(i)
                if it and str(it.data(0, Qt.ItemDataRole.UserRole) or "") in prev:
                    it.setSelected(True)
            self._lamp_block = False
        elif self._lamps and not self.lamp_tree.selectedItems():
            first = self.lamp_tree.topLevelItem(0)
            if first is not None:
                first.setSelected(True)
        _refit_side_table(self.lamp_tree)
        self._load_lamp_editor()
        self._push_lamps_to_view()

    def _style_lamp_color_btn(self) -> None:
        c = self._lamp_color
        self._lamp_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: rgb({c.red()},{c.green()},{c.blue()}); "
            f"color: {'#111' if c.lightness() > 140 else '#eee'}; "
            f"font-weight: 600; border: 1px solid rgba(0,0,0,0.35); "
            f"border-radius: 4px; padding: 4px 10px; }}"
        )
        self._lamp_color_btn.setText(
            f"Color  #{c.red():02X}{c.green():02X}{c.blue():02X}"
        )

    def _pick_lamp_color(self) -> None:
        sel = self._selected_lamps()
        if not sel:
            return
        start = self._lamp_color
        col = QColorDialog.getColor(start, self, "Lamp color")
        if not col.isValid():
            return
        self._lamp_color = col
        self._style_lamp_color_btn()
        rgb = (col.redF(), col.greenF(), col.blueF())
        for L in sel:
            L.color = rgb
        self._push_lamps_to_view()
        self._status.showMessage(
            f"Lamp color #{col.red():02X}{col.green():02X}{col.blue():02X}"
            + (f"  ({len(sel)} selected)" if len(sel) > 1 else "")
        )

    def _load_lamp_editor(self) -> None:
        sel = self._selected_lamps()
        self._lamp_block = True
        try:
            en = bool(sel)
            self._lamp_enabled.setEnabled(en)
            self._lamp_bright.setEnabled(en)
            self._lamp_range.setEnabled(en)
            self._lamp_color_btn.setEnabled(en)
            self._lamp_remove_btn.setEnabled(en)
            if not sel:
                return
            L = sel[0]
            self._lamp_enabled.setChecked(all(x.enabled for x in sel))
            self._lamp_bright.setValue(int(round(L.brightness * 100)))
            self._lamp_range.setValue(int(round(L.range_m * 100)))
            r, g, b = L.color
            self._lamp_color = QColor(
                int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
            )
            self._style_lamp_color_btn()
            if len(sel) > 1:
                self._lamp_bright_lab.setText(
                    f"Brightness {L.brightness:.2f}  ({len(sel)} selected)"
                )
                self._lamp_range_lab.setText(
                    f"Cast range {L.range_m:.1f} m  ({len(sel)} selected)"
                )
            else:
                self._lamp_bright_lab.setText(f"Brightness {L.brightness:.2f}")
                self._lamp_range_lab.setText(f"Cast range {L.range_m:.1f} m")
        finally:
            self._lamp_block = False

    def _on_lamp_select(self, *_args) -> None:
        if self._lamp_block:
            return
        self._load_lamp_editor()

    def _on_lamp_edit(self, *_args) -> None:
        if self._lamp_block:
            return
        sel = self._selected_lamps()
        if not sel:
            return
        on = self._lamp_enabled.isChecked()
        bright = self._lamp_bright.value() / 100.0
        range_m = self._lamp_range.value() / 100.0
        for L in sel:
            L.enabled = on
            L.brightness = bright
            L.range_m = range_m
        suffix = f"  ({len(sel)} selected)" if len(sel) > 1 else ""
        self._lamp_bright_lab.setText(f"Brightness {bright:.2f}{suffix}")
        self._lamp_range_lab.setText(f"Cast range {range_m:.1f} m{suffix}")
        stems = {lamp_uid(L.mesh_key, L.part_id) for L in sel}
        self._lamp_block = True
        for i in range(self.lamp_tree.topLevelItemCount()):
            it = self.lamp_tree.topLevelItem(i)
            if it is None:
                continue
            uid = str(it.data(0, Qt.ItemDataRole.UserRole) or "")
            for L in self._lamps:
                if lamp_uid(L.mesh_key, L.part_id) == uid:
                    mark = "●" if L.enabled else "○"
                    short = (L.label or L.part_id).split(" @ ")[0]
                    it.setText(0, f"{mark}  {short}")
                    break
            if uid in stems:
                it.setSelected(True)
        self._lamp_block = False
        self._push_lamps_to_view()

    def _on_moon_int(self, v: int) -> None:
        self._moon_int_lab.setText(f"Moon {v / 100.0:.2f}")
        self._push_lamps_to_view()

    def _push_lamps_to_view(self) -> None:
        if self.view is None:
            return
        moon = self._moon_cb.isChecked() and not self._sun_mode_cb.isChecked()
        self.view.set_moon(moon, self._moon_int.value() / 100.0)
        self.view.set_lamps(self._lamps)
        self.view.set_show_lamp_gizmos(self._lamp_gizmo_cb.isChecked())

    def _rescan_lamps(self) -> None:
        found = discover_lamps(self._scene)
        self._lamps = merge_lamps(self._lamps, found)
        self._refill_lamp_list()
        self._status.showMessage(f"Glow maps: {len(self._lamps)}")

    def _add_lamp_from_mat(self) -> None:
        stems = self._selected_stems()
        mesh_keys = self._selected_mesh_keys()
        if not stems:
            QMessageBox.information(self, "Lamps", "Select a material family in Mat first.")
            return
        if len(self._mesh_paths) > 1 and not mesh_keys:
            QMessageBox.information(
                self,
                "Lamps",
                "Multiple meshes loaded — select materials under a specific mesh in Mat.",
            )
            return
        existing = {lamp_uid(L.mesh_key, L.part_id) for L in self._lamps}
        added = 0
        last_stem = ""
        mks = mesh_keys or {""}
        for mk in mks:
            for stem in stems:
                for L in lamps_from_stem(stem, self._scene, mesh_key=mk):
                    uid = lamp_uid(L.mesh_key, L.part_id)
                    if uid in existing:
                        continue
                    if len(self._lamps) >= MAX_LAMPS:
                        break
                    self._lamps.append(L)
                    existing.add(uid)
                    added += 1
                    last_stem = stem
        if added == 0:
            self._refill_lamp_list(select_stem=next(iter(stems)))
            self._status.showMessage(f"Already listed: {', '.join(sorted(stems)[:3])}")
            return
        self._refill_lamp_list(select_stem=last_stem or next(iter(stems)))
        self._status.showMessage(f"Added {added} bulb cast point(s)")

    def _bake_out_dir(self) -> Path | None:
        if self._mesh_path is not None:
            return self._mesh_path.parent / "baked_lamps"
        if self._mesh_paths:
            return self._mesh_paths[0].parent / "baked_lamps"
        return None

    def _probe_cuda_bake(self) -> None:
        """Deferred CuPy probe — keeps cold start off the CUDA search path."""
        from ..lamps.bake import cuda_available

        ok = bool(cuda_available())
        self._bake_cuda_cb.setChecked(ok)
        self._bake_cuda_cb.setEnabled(ok)
        self._bake_cuda_cb.setToolTip(
            "Path-trace direct lighting on GPU when CuPy/CUDA is available"
            if ok
            else "CuPy/CUDA not available — CPU bake only"
        )

    def _start_lamp_bake(self) -> None:
        if self._bake_busy or self._busy:
            return
        if not self._scene.parts:
            QMessageBox.information(self, "Bake", "Open a mesh first.")
            return
        enabled = [L for L in self._lamps if L.enabled and L.brightness > 1e-4]
        if not enabled:
            QMessageBox.information(
                self, "Bake", "No enabled lamps. Rescan / enable bulbs first."
            )
            return
        out_dir = self._bake_out_dir()
        if out_dir is None:
            QMessageBox.information(self, "Bake", "No mesh folder to write baked_lamps/.")
            return
        from ..lamps.bake import BakeSettings, cuda_available

        q = str(self._bake_quality.currentData() or "high")
        settings = BakeSettings.from_quality(
            q, prefer_cuda=bool(self._bake_cuda_cb.isChecked())
        )
        backend = "CUDA" if settings.prefer_cuda and cuda_available() else "CPU"
        # shallow copy lamps / scene refs — worker must not mutate UI list mid-edit
        lamps = list(self._lamps)
        self._bake_busy = True
        self._bake_btn.setEnabled(False)
        self._nav.hide()
        self._bake_bar.set_progress(f"Starting ({backend})…", 0, 0.0)
        self._bake_bar.show()
        self._bake_bar.reposition()
        self._bake_worker = BakeWorker(self._scene, lamps, out_dir, settings, self)
        self._bake_worker.progress.connect(self._on_bake_progress)
        self._bake_worker.finished_ok.connect(self._on_bake_finished)
        self._bake_worker.failed.connect(self._on_bake_failed)
        self._bake_worker.start()
        self._status.showMessage(f"Baking lamps → {out_dir} ({backend})")

    def _cancel_lamp_bake(self) -> None:
        if self._bake_worker is not None:
            self._bake_worker.cancel()
            self._bake_bar.set_progress("Cancelling…", self._bake_bar.bar.value(), 0.0)

    def _on_bake_progress(self, stage: str, pct: int, eta: float) -> None:
        self._bake_bar.set_progress(stage, pct, eta)
        # Same % → toast path as mesh load (bar stays the detailed bake UI).
        self._status.showMessage(f"{stage}  {max(0, min(100, int(pct)))}%")
        self._bake_bar.reposition()

    def _on_bake_finished(self, result: object) -> None:
        from ..lamps.bake import BakeResult

        self._bake_busy = False
        self._bake_btn.setEnabled(True)
        self._bake_bar.hide()
        self._nav.show()
        self._nav.reposition()
        self._bake_worker = None
        if not isinstance(result, BakeResult):
            return
        warns = [i.message for i in result.issues if i.level == "warn"]
        errs = [i.message for i in result.issues if i.level == "error"]
        infos = [i.message for i in result.issues if i.level == "info"]
        if result.cancelled:
            QMessageBox.information(self, "Bake", "Bake cancelled.")
            self._status.showMessage("Bake cancelled")
            return
        if errs and not result.written:
            QMessageBox.warning(self, "Bake failed", "\n".join(errs[:8]))
            self._status.showMessage("Bake failed")
            return
        msg = (
            f"Backend: {result.backend}\n"
            f"Time: {result.seconds:.1f}s\n"
            f"Wrote {len(result.written)} file(s) →\n{result.out_dir}\n"
        )
        if infos:
            msg += "\n" + "\n".join(infos[:6])
        if warns:
            msg += "\n\nWarnings:\n" + "\n".join(warns[:8])
        if errs:
            msg += "\n\nErrors:\n" + "\n".join(errs[:4])
        QMessageBox.information(self, "Bake complete", msg)
        self._status.showMessage(
            f"Bake OK · {result.backend} · {result.seconds:.1f}s → {result.out_dir}"
        )

    def _on_bake_failed(self, err: str) -> None:
        self._bake_busy = False
        self._bake_btn.setEnabled(True)
        self._bake_bar.hide()
        self._nav.show()
        self._nav.reposition()
        self._bake_worker = None
        QMessageBox.critical(self, "Bake error", err)
        self._status.showMessage("Bake error")

    def _remove_selected_lamp(self) -> None:
        sel = self._selected_lamps()
        if not sel:
            return
        drop = {lamp_uid(L.mesh_key, L.part_id) for L in sel}
        self._lamps = [L for L in self._lamps if lamp_uid(L.mesh_key, L.part_id) not in drop]
        self._refill_lamp_list()
        self._status.showMessage(f"Removed {len(drop)} bulb(s)")

    # ── menu ─────────────────────────────────────────────────

    def _build_menu(self) -> None:
        open_act = QAction("Open…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._browse)

        add_act = QAction("Add mesh to preview…", self)
        add_act.setShortcut("Ctrl+Shift+O")
        add_act.triggered.connect(self._browse_add_mesh)

        clear_meshes_act = QAction("Clear meshes", self)
        clear_meshes_act.setShortcut("Ctrl+Shift+Backspace")
        clear_meshes_act.triggered.connect(self._clear_meshes)

        fixture_act = QAction("Open bumper.fbx fixture", self)
        fixture_act.triggered.connect(lambda: self.open_path(FIXTURES / "bumper.fbx"))

        tm_act = QAction("Open body.trainzmesh fixture", self)
        tm_act.triggered.connect(lambda: self.open_path(FIXTURES / "body.trainzmesh"))

        tex_act = QAction("Open sample_albedo.texture.txt fixture", self)
        tex_act.triggered.connect(lambda: self.open_path(FIXTURES / "sample_albedo.texture.txt"))

        folder_act = QAction("Check textures in folder…", self)
        folder_act.triggered.connect(self._browse_folder_textures)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        open_proj = QAction("Open Project…", self)
        open_proj.setShortcut("Ctrl+Shift+P")
        open_proj.triggered.connect(self._open_project_dialog)
        save_proj = QAction("Save Project", self)
        save_proj.setShortcut("Ctrl+Shift+S")
        save_proj.triggered.connect(self._save_project)
        save_proj_as = QAction("Save Project As…", self)
        save_proj_as.triggered.connect(self._save_project_as)

        undo_act = QAction("Undo", self)
        undo_act.setShortcut("Ctrl+Z")
        undo_act.setEnabled(False)
        undo_act.triggered.connect(self._undo_edit)
        redo_act = QAction("Redo", self)
        redo_act.setShortcuts(["Ctrl+Y", "Ctrl+Shift+Z"])
        redo_act.setEnabled(False)
        redo_act.triggered.connect(self._redo_edit)
        self._undo_act = undo_act
        self._redo_act = redo_act

        mb = self.menuBar()
        mb.setNativeMenuBar(False)
        mb.hide()
        mb.setFixedHeight(0)

        m = mb.addMenu("File")
        m.addAction(open_act)
        m.addAction(add_act)
        m.addAction(clear_meshes_act)
        m.addAction(fixture_act)
        m.addAction(tm_act)
        m.addAction(tex_act)
        m.addAction(folder_act)
        m.addSeparator()
        m.addAction(open_proj)
        m.addAction(save_proj)
        m.addAction(save_proj_as)
        m.addSeparator()
        m.addAction(quit_act)
        self._file_menu = m

        ed = mb.addMenu("Edit")
        ed.addAction(undo_act)
        ed.addAction(redo_act)
        self._edit_menu = ed

        v = mb.addMenu("View")
        for label, attr, shortcut in (
            ("World axes", "_show_axes", ""),
            ("Corner XYZ gizmo", "_show_corner_gizmo", ""),
            ("Grid", "_show_grid", ""),
            ("Attachment gizmos", "_show_atts", ""),
            ("Frame stats (FPS)", "_show_fps", "F3"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(getattr(self, attr))
            if shortcut:
                act.setShortcut(shortcut)
                act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.toggled.connect(lambda checked, a=attr: self._set_view_flag(a, checked))
            self._view_acts[attr] = act
            v.addAction(act)

        flip_act = QAction("Flip texture V", self)
        flip_act.setCheckable(True)
        flip_act.setChecked(self._flip_texture_v)
        flip_act.setToolTip("Off = Trainz/D3D (V=0 at top). Turn on only if maps look inverted.")
        flip_act.toggled.connect(self._set_flip_texture_v)
        self._view_acts["flip_v"] = flip_act
        v.addAction(flip_act)

        face_act = QAction("Face Orientation", self)
        face_act.setCheckable(True)
        face_act.setChecked(self._face_orient)
        face_act.setToolTip("Blue = front · red = back (Blender). Also on Scene tab.")
        face_act.toggled.connect(self._set_face_orientation)
        self._view_acts["face_orient"] = face_act
        v.addAction(face_act)

        reset_cam = QAction("Reset camera", self)
        reset_cam.setShortcut("R")
        reset_cam.triggered.connect(self._reset_camera)
        v.addAction(reset_cam)

        settings_act = QAction("Settings…", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.triggered.connect(lambda: self._set_page("settings"))
        v.addAction(settings_act)

        v.addSeparator()
        dbg_group = QActionGroup(self)
        dbg_group.setExclusive(True)
        self._dbg_actions: dict[int, QAction] = {}
        for label, mode in PBR_MODES:
            act = QAction(f"PBR {label}", self)
            act.setCheckable(True)
            if mode == 0:
                act.setChecked(True)
            dbg_group.addAction(act)
            v.addAction(act)
            self._dbg_actions[mode] = act

            def _set_dbg(_checked: bool = False, m=mode) -> None:
                self._set_pbr_mode(m)

            act.triggered.connect(_set_dbg)

        show_home = QAction("Home", self)
        show_home.triggered.connect(self.go_home)
        v.addSeparator()
        v.addAction(show_home)
        engine_act = QAction("Engine Tuner", self)
        engine_act.triggered.connect(self.enter_engine_tuner)
        v.addAction(engine_act)
        assets_act = QAction("Assets Tools", self)
        assets_act.triggered.connect(self.enter_assets_studio)
        v.addAction(assets_act)
        texmesh_act = QAction("Texture / Mesh Tools", self)
        texmesh_act.triggered.connect(self.enter_texmesh_studio)
        v.addAction(texmesh_act)
        self._view_menu = v

        tools = mb.addMenu("Tools")
        ve_cur = QAction("VE Rules scan current", self)
        ve_cur.setShortcut("Ctrl+Shift+V")
        ve_cur.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        ve_cur.setToolTip(
            "Scan the open mesh / textures / config / sounds / asset folder "
            "(works in every studio, not only Assets Tools)."
        )
        ve_cur.triggered.connect(self._ve_scan_current)
        tools.addAction(ve_cur)
        ve_folder = QAction("VE Rules scan folder…", self)
        ve_folder.setShortcut("Ctrl+Shift+R")
        ve_folder.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        ve_folder.triggered.connect(self._ve_scan_folder_dialog)
        tools.addAction(ve_folder)
        ve_fix = QAction("VE Rules fix current…", self)
        ve_fix.triggered.connect(self._ve_fix_current)
        tools.addAction(ve_fix)
        tools.addSeparator()
        ve_last = QAction("Show last VE report", self)
        ve_last.triggered.connect(self._ve_show_last)
        tools.addAction(ve_last)
        self._tools_menu = tools

        self._build_theme_menu()
        self._build_lang_menu()

    def _build_theme_menu(self) -> None:
        """Top-bar Theme menu — reliable (bottom-bar icon was click-through)."""
        theme_menu = self.menuBar().addMenu("Theme")
        theme_menu.setToolTip("Light / dark appearance")
        group = QActionGroup(self)
        group.setExclusive(True)

        dark_act = QAction("Dark", self)
        dark_act.setCheckable(True)
        dark_act.setChecked(self._theme_mode == "dark")
        dark_act.triggered.connect(lambda: self._begin_theme_change("dark"))
        group.addAction(dark_act)
        theme_menu.addAction(dark_act)

        light_act = QAction("Light", self)
        light_act.setCheckable(True)
        light_act.setChecked(self._theme_mode == "light")
        light_act.triggered.connect(lambda: self._begin_theme_change("light"))
        group.addAction(light_act)
        theme_menu.addAction(light_act)

        theme_menu.addSeparator()
        toggle_act = QAction("Toggle light / dark", self)
        toggle_act.setShortcut("Ctrl+T")
        toggle_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        toggle_act.triggered.connect(self._toggle_theme)
        theme_menu.addAction(toggle_act)

        self._theme_menu = theme_menu
        self._theme_dark_act = dark_act
        self._theme_light_act = light_act

    def _sync_theme_menu(self) -> None:
        dark = getattr(self, "_theme_dark_act", None)
        light = getattr(self, "_theme_light_act", None)
        if dark is None or light is None:
            return
        dark.blockSignals(True)
        light.blockSignals(True)
        dark.setChecked(self._theme_mode == "dark")
        light.setChecked(self._theme_mode == "light")
        dark.blockSignals(False)
        light.blockSignals(False)

    def _build_lang_menu(self) -> None:
        from .i18n import LANG_NATIVE, LANG_ORDER, current_language, i18n, mark_skip

        # English literals here — snapshot_and_apply translates after build.
        lang_menu = self.menuBar().addMenu("Lang")
        lang_menu.setToolTip(
            "Switch UI language — menus, buttons, tooltips, and status codes."
        )
        group = QActionGroup(self)
        group.setExclusive(True)
        self._lang_acts: dict[str, QAction] = {}
        self._lang_tip_keys: dict[str, str] = {
            "en": "English — default UI language",
            "th": "Thai — Noto Sans Thai Looped",
            "ja": "Japanese — Noto Sans CJK JP",
            "id": "Indonesian — Noto Sans",
        }
        cur = current_language()
        for code in LANG_ORDER:
            # Native name stays in that language — never auto-translate the label.
            act = QAction(LANG_NATIVE[code], self)
            act.setCheckable(True)
            act.setChecked(code == cur)
            act.setData(code)
            act.setToolTip(self._lang_tip_keys[code])
            mark_skip(act)
            act.triggered.connect(lambda _=False, c=code: self._set_ui_language(c))
            group.addAction(act)
            lang_menu.addAction(act)
            self._lang_acts[code] = act
        self._lang_menu = lang_menu
        i18n().language_changed.connect(self._on_language_changed)
        bar = getattr(self, "_title_bar", None)
        if bar is not None:
            bar.bind_menus(
                {
                    "File": self._file_menu,
                    "Edit": self._edit_menu,
                    "View": self._view_menu,
                    "Tools": getattr(self, "_tools_menu", None),
                    "Theme": self._theme_menu,
                    "Lang": self._lang_menu,
                }
            )

    def _install_title_bar(self) -> None:
        """Floating glass menu bar + macOS traffic lights (frameless chrome)."""
        bar = FloatTitleBar(self, mode=self._theme_mode)
        bar.close_clicked.connect(self.close)
        bar.minimize_clicked.connect(self.showMinimized)
        bar.zoom_clicked.connect(self._toggle_max_restore)
        bar.bind_menus(
            {
                "File": getattr(self, "_file_menu", None),
                "Edit": getattr(self, "_edit_menu", None),
                "View": getattr(self, "_view_menu", None),
                "Tools": getattr(self, "_tools_menu", None),
                "Theme": getattr(self, "_theme_menu", None),
                "Lang": getattr(self, "_lang_menu", None),
            }
        )
        bar.set_window_title_text(self.windowTitle())
        self._title_bar = bar
        QTimer.singleShot(0, self._reposition_title_bar)

    def _reposition_title_bar(self) -> None:
        bar = getattr(self, "_title_bar", None)
        if bar is None:
            return
        bar.reposition(self)
        bar.raise_()

    def _toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def setWindowTitle(self, title: str) -> None:  # noqa: N802
        super().setWindowTitle(title)
        bar = getattr(self, "_title_bar", None)
        if bar is not None:
            bar.set_window_title_text(title)

    def _set_ui_language(self, code: str) -> None:
        from .i18n import current_language, set_language

        if code == current_language():
            return
        set_language(code)

    def _on_language_changed(self, lang: str) -> None:
        from .i18n import apply_language_font, snapshot_and_apply
        from .motion import animate_language_swap

        for code, act in getattr(self, "_lang_acts", {}).items():
            act.blockSignals(True)
            act.setChecked(code == lang)
            act.blockSignals(False)

        def _apply() -> None:
            from .i18n import t

            apply_language_font(lang, root=self)
            snapshot_and_apply(self)
            home = getattr(self, "_home_page", None)
            if home is not None and hasattr(home, "retranslate"):
                home.retranslate()
            for host in (
                getattr(self, "_sounds_host", None),
                getattr(self, "_engine_host", None),
                getattr(self, "_assets_host", None),
            ):
                if host is not None:
                    snapshot_and_apply(host)
            for code, act in getattr(self, "_lang_acts", {}).items():
                tip_key = getattr(self, "_lang_tip_keys", {}).get(code)
                if tip_key:
                    act.setToolTip(t(tip_key))
            bar = getattr(self, "_title_bar", None)
            if bar is not None:
                bar.sync_titles()
            if self._status is not None:
                self._status.showMessage(self.windowTitle())

        animate_language_swap(self, _apply)

    # ── file open ────────────────────────────────────────────

    def _browse(self) -> None:
        self.ensure_studio_chrome()
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open mesh(es), texture, or .kin — multi-select for combined preview",
            str(FIXTURES if FIXTURES.is_dir() else Path.home()),
            "Trainz (*.fbx *.im *.trainzmesh *.texture.txt *.texture *.kin);;All (*.*)",
        )
        if not paths:
            return
        self.open_paths([Path(p) for p in paths], mode="replace")

    def _browse_add_mesh(self) -> None:
        self.ensure_studio_chrome()
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add mesh(es) to preview",
            str(self._mesh_folder or (FIXTURES if FIXTURES.is_dir() else Path.home())),
            "Meshes (*.fbx *.im *.trainzmesh);;All (*.*)",
        )
        if not paths:
            return
        mode = "append" if self._scene.parts else "replace"
        self.open_paths([Path(p) for p in paths], mode=mode)

    def _browse_folder_textures(self) -> None:
        if self._busy:
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            "Folder with .texture.txt",
            str(FIXTURES if FIXTURES.is_dir() else Path.home()),
        )
        if folder:
            self._mesh_folder = Path(folder)
            self._rebuild_tex_list()
            self._status.showMessage(f"Scanned textures in {folder}")

    def _is_texture_path(self, path: Path) -> bool:
        name = path.name.lower()
        return name.endswith(".texture.txt") or path.suffix.lower() == ".texture"

    # ── VE Rules hub (app-wide — every studio) ───────────────

    def ve_context_paths(self) -> list[Path]:
        """Paths relevant to the current studio for a shared VE scan."""
        mode = getattr(self, "_studio_mode", "home")
        out: list[Path] = []
        seen: set[str] = set()

        def _add(p: Path | None) -> None:
            if p is None:
                return
            try:
                key = str(p.resolve()) if p.exists() else str(p)
            except OSError:
                key = str(p)
            if key in seen:
                return
            seen.add(key)
            out.append(p)

        if mode == "mesh":
            for p in getattr(self, "_mesh_paths", []) or []:
                _add(Path(p))
            folder = getattr(self, "_mesh_folder", None)
            if folder is not None and Path(folder).is_dir():
                _add(Path(folder))
            elif out:
                _add(out[0].parent)
        elif mode in ("assets", "texmesh"):
            host = getattr(self, "_assets_host", None)
            if host is not None and hasattr(host, "ve_context_paths"):
                for p in host.ve_context_paths():
                    _add(Path(p))
        elif mode == "engine":
            host = getattr(self, "_engine_host", None)
            cfg = getattr(getattr(host, "cfg", None), "source_path", None) if host else None
            if cfg:
                p = Path(cfg)
                _add(p)
                if p.is_file():
                    _add(p.parent)
        elif mode == "sounds":
            host = getattr(self, "_sounds_host", None)
            clips = getattr(host, "_clips", None) if host else None
            if clips:
                for clip in clips:
                    src = getattr(clip, "source", None)
                    if src:
                        _add(Path(src))
        elif mode == "home":
            pass
        return out

    def _ve_busy(self) -> bool:
        w = getattr(self, "_ve_worker", None)
        return w is not None and w.isRunning()

    def ve_scan(
        self,
        paths: list[Path] | None = None,
        *,
        show_dialog: bool = True,
        announce: bool = True,
    ) -> None:
        """Central VE Rules entry — Mesh / Sounds / Engine / Assets / folder drop."""
        targets = [Path(p) for p in (paths or self.ve_context_paths())]
        if not targets:
            if announce:
                QMessageBox.information(
                    self,
                    "VE Rules",
                    "Nothing to scan in this studio yet.\n"
                    "Open a mesh, config, sounds, or Assets folder — "
                    "or use Tools → VE Rules scan folder…",
                )
            return
        if self._ve_busy():
            if announce:
                self._status.showMessage("VE Rules — still scanning…", 3000)
            return
        if announce:
            self._status.showMessage(f"VE Rules — scanning {len(targets)} path(s)…")
        worker = VeScanWorker(targets, self)
        self._ve_worker = worker

        def _done(reports: object, summary: object) -> None:
            from .ve_dialog import show_ve_reports

            reps = list(reports) if isinstance(reports, list) else []
            summ = summary if isinstance(summary, dict) else {}
            self._ve_last_reports = reps
            line = str(summ.get("line") or "VE done")
            has_hit = bool(summ.get("errors") or summ.get("warns"))
            self._ve_btn.setText("VE!" if has_hit else "VE OK")
            self._ve_btn.setToolTip(line)
            self._status.showMessage(f"VE Rules — {line}", 8000)
            if show_dialog and (announce or has_hit):
                show_ve_reports(self, reps, title="VE Rules")

        def _err(msg: str) -> None:
            self._status.showMessage(f"VE Rules error — {msg}", 8000)
            if announce:
                QMessageBox.warning(self, "VE Rules", msg)

        worker.done.connect(_done)
        worker.err.connect(_err)
        worker.start()

    def _ve_scan_current(self) -> None:
        self.ve_scan(None, show_dialog=True, announce=True)

    def _ve_scan_folder_dialog(self) -> None:
        start = self._mesh_folder or Path.home()
        path = QFileDialog.getExistingDirectory(
            self, "VE Rules — scan asset folder", str(start)
        )
        if not path:
            return
        self.ve_scan([Path(path)], show_dialog=True, announce=True)

    def _ve_fix_current(self) -> None:
        from ..io.ve_rules import fix_reports, scan_paths
        from .i18n import g

        paths = self.ve_context_paths()
        if not paths:
            QMessageBox.information(
                self, "VE Rules", "Open content in a studio first."
            )
            return
        reply = QMessageBox.question(
            self,
            g("rules.ui.fix_title"),
            g("rules.fix.confirm", n=len(paths)),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        results = fix_reports(scan_paths(paths), bak=True)
        ok_n = sum(1 for _, ok, _ in results if ok)
        self._status.showMessage(
            f"VE Rules fix — {ok_n} applied, {len(results) - ok_n} failed", 6000
        )
        self.ve_scan(paths, show_dialog=True, announce=True)

    def _ve_show_last(self) -> None:
        from .ve_dialog import show_ve_reports

        reps = getattr(self, "_ve_last_reports", None) or []
        if not reps:
            self._ve_scan_current()
            return
        show_ve_reports(self, reps, title="VE Rules — last scan")

    def _ve_scan_auto(self, paths: list[Path]) -> None:
        """Background scan after open — status bar only; dialog if errors."""
        if not paths:
            return
        # Expand mesh parents so textures/config are included
        expanded: list[Path] = []
        seen: set[str] = set()
        for p in paths:
            p = Path(p)
            key = str(p)
            if key not in seen:
                seen.add(key)
                expanded.append(p)
            parent = p.parent if p.is_file() else p
            pk = str(parent)
            if parent.is_dir() and pk not in seen:
                seen.add(pk)
                expanded.append(parent)

        def _done(reports: object, summary: object) -> None:
            from .ve_dialog import show_ve_reports

            reps = list(reports) if isinstance(reports, list) else []
            summ = summary if isinstance(summary, dict) else {}
            self._ve_last_reports = reps
            line = str(summ.get("line") or "VE done")
            has_err = bool(summ.get("errors"))
            self._ve_btn.setText("VE!" if has_err or summ.get("warns") else "VE OK")
            self._ve_btn.setToolTip(line)
            self._status.showMessage(f"VE Rules — {line}", 6000)
            if has_err:
                show_ve_reports(self, reps, title="VE Rules — issues found")

        if self._ve_busy():
            return
        worker = VeScanWorker(expanded, self)
        self._ve_worker = worker
        worker.done.connect(_done)
        worker.err.connect(lambda m: self._status.showMessage(f"VE Rules — {m}", 5000))
        worker.start()

    def open_path(self, path: Path | None) -> None:
        if path is None:
            return
        self.open_paths([Path(path)], mode="replace")

    def open_paths(self, paths: list[Path], *, mode: str = "replace") -> None:
        """Load one or more meshes. mode=replace clears preview; append keeps existing."""
        self.ensure_studio_chrome()
        if self._busy:
            return
        resolved: list[Path] = []
        for path in paths:
            path = Path(path).expanduser()
            if not path.is_file():
                alt = Path.cwd() / path
                if alt.is_file():
                    path = alt
                else:
                    QMessageBox.warning(self, "Not found", f"File not found:\n{path}")
                    continue
            resolved.append(path)
        if not resolved:
            return

        # .kin / texture handled one-by-one (not merged geometry)
        if len(resolved) == 1:
            path = resolved[0]
            if path.suffix.lower() == KIN_EXT:
                self._add_kin(path)
                return
            if self._is_texture_path(path):
                self._mesh_folder = path.parent
                self._rebuild_tex_list(extra_reports=[check_texture_txt(path)])
                self.setWindowTitle(f"MSTN Mesh Studio — {path.name}")
                self._status.showMessage(f"Checked {path}")
                self._select_stem(texture_stem(path.name))
                QTimer.singleShot(100, lambda p=path: self._ve_scan_auto([p]))
                return

        mesh_paths = [
            p
            for p in resolved
            if p.suffix.lower() in MESH_EXTS and not self._is_texture_path(p)
        ]
        if not mesh_paths:
            return
        if self._worker is not None and self._worker.isRunning():
            return

        if mode == "append" and not self._scene.parts:
            mode = "replace"

        self._set_busy(True)
        names = ", ".join(p.name for p in mesh_paths[:3])
        if len(mesh_paths) > 3:
            names += f" +{len(mesh_paths) - 3}"
        verb = "Adding" if mode == "append" else "Opening"
        self._show_overlay(
            f"{verb} {names}…", brand="Mesh Studio", pct=2, instant=True, frost=True
        )
        self._status.showMessage(f"{verb} {len(mesh_paths)} mesh(es)…")
        base = self._scene if mode == "append" else None
        self._worker = LoadWorker(mesh_paths, self, base_scene=base)
        self._worker.progress.connect(self._on_load_progress)
        self._worker.ok.connect(
            lambda sc, dec, mp=list(mesh_paths), m=mode: self._on_loaded(mp, sc, dec, mode=m)
        )
        self._worker.err.connect(self._on_load_err)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    # ── textures (grouped + per-part filter) ─────────────────

    def _collect_tex_entries(
        self,
        scene: Scene,
        folders: dict[str, Path] | Path | None,
        extra: list[TextureReport] | None = None,
    ) -> list[TexEntry]:
        by: dict[tuple[str, str], TexEntry] = {}

        for part in scene.parts:
            mk = part.mesh_key or ""
            for ref, tag in (
                (part.albedo_ref, "albedo"),
                (part.normal_ref, "normal"),
                (part.parameter_ref, "parameter"),
            ):
                if not ref:
                    continue
                stem = texture_stem(ref)
                if not stem:
                    continue
                key = (mk, stem)
                if key in by:
                    continue
                fam, role = material_family(stem)
                by[key] = TexEntry(
                    stem=stem,
                    label=f"[scene] {stem}  ({tag})",
                    kind="scene",
                    map_role=role or tag,
                    family=fam,
                    mesh_key=mk,
                )

        folder_map: dict[str, Path] = {}
        if isinstance(folders, dict):
            folder_map = {k: v for k, v in folders.items() if v is not None and v.is_dir()}
        elif folders is not None and Path(folders).is_dir():
            # legacy single folder — apply to all mesh keys present (or "")
            keys = {p.mesh_key or "" for p in scene.parts} or {""}
            for mk in keys:
                folder_map[mk] = Path(folders)

        for mk, folder in folder_map.items():
            for r in scan_folder(folder):
                stem = texture_stem(r.path.name)
                if not stem:
                    continue
                fam, role = material_family(stem)
                label = f"{r.summary}  {r.path.name}"
                key = (mk, stem)
                if key in by:
                    e = by[key]
                    e.report = r
                    e.path = r.path
                    e.label = label
                    e.kind = "folder"
                    e.map_role = role or e.map_role
                    e.family = fam or e.family
                else:
                    by[key] = TexEntry(
                        stem=stem,
                        label=label,
                        kind="folder",
                        report=r,
                        path=r.path,
                        map_role=role,
                        family=fam,
                        mesh_key=mk,
                    )
        if extra:
            # attach extras to primary / empty mesh key
            primary = self._mesh_paths[0].name if self._mesh_paths else ""
            for r in extra:
                stem = texture_stem(r.path.name)
                if not stem:
                    continue
                fam, role = material_family(stem)
                key = (primary, stem)
                by[key] = TexEntry(
                    stem=stem,
                    label=f"{r.summary}  {r.path.name}",
                    kind="folder",
                    report=r,
                    path=r.path,
                    map_role=role,
                    family=fam,
                    mesh_key=primary,
                )
        return sorted(
            by.values(),
            key=lambda e: (e.mesh_key, e.family or e.stem, e.map_role or "", e.stem),
        )

    def _mesh_folder_map(self) -> dict[str, Path]:
        return {p.name: p.parent for p in self._mesh_paths if p.parent.is_dir()}

    def _group_entries(self, entries: list[TexEntry]) -> list[MatGroup]:
        groups: dict[str, MatGroup] = {}
        order: list[str] = []
        for e in entries:
            key = e.family or e.stem
            if key not in groups:
                groups[key] = MatGroup(key=key)
                order.append(key)
            groups[key].entries.append(e)
        return [groups[k] for k in order]

    def _add_mat_groups(
        self,
        parent: QTreeWidgetItem | QTreeWidget,
        groups: list[MatGroup],
        *,
        mesh_key: str,
    ) -> None:
        role_order = {"albedo": 0, "normal": 1, "parameter": 2}
        role_tag = {"albedo": "A", "normal": "N", "parameter": "P"}
        for g in groups:
            stems = [e.stem for e in g.entries]
            roles = sorted(
                {e.map_role for e in g.entries if e.map_role},
                key=lambda r: role_order.get(r or "", 9),
            )
            tags = " ".join(role_tag.get(r, r[:1].upper()) for r in roles) or "—"
            bad = any(e.report is not None and not e.report.ok for e in g.entries)
            status = "!" if bad else "ok"
            item = QTreeWidgetItem([g.key, tags, status])
            item.setData(0, ROLE_KIND, "group")
            item.setData(0, ROLE_GROUP_STEMS, stems)
            item.setData(0, ROLE_STEM, "")
            item.setData(0, ROLE_MESH_KEY, mesh_key)
            item.setToolTip(0, f"{g.key}\n{mesh_key or 'mesh'}\n{', '.join(roles) if roles else 'maps'}")
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            if bad:
                item.setForeground(2, QColor("#ff6b6b"))
            for e in sorted(g.entries, key=lambda x: role_order.get(x.map_role or "", 9)):
                role = e.map_role or "map"
                st = "!" if (e.report is not None and not e.report.ok) else "ok"
                child = QTreeWidgetItem([role, role_tag.get(role, "·"), st])
                child.setData(0, ROLE_STEM, e.stem)
                child.setData(0, ROLE_REPORT, e.report)
                child.setData(0, ROLE_KIND, "map")
                child.setData(0, ROLE_PATH, str(e.path) if e.path else "")
                child.setData(0, ROLE_MAP_ROLE, role)
                child.setData(0, ROLE_MESH_KEY, e.mesh_key or mesh_key)
                child.setToolTip(0, f"{e.stem}\n{e.mesh_key or mesh_key}")
                if e.report is not None and not e.report.ok:
                    child.setForeground(0, QColor("#ff6b6b"))
                    child.setForeground(2, QColor("#ff6b6b"))
                item.addChild(child)
            if isinstance(parent, QTreeWidget):
                parent.addTopLevelItem(item)
            else:
                parent.addChild(item)
            item.setExpanded(False)

    def _rebuild_tex_list(self, extra_reports: list[TextureReport] | None = None) -> None:
        entries = self._collect_tex_entries(self._scene, self._mesh_folder_map(), extra_reports)
        self.tex_tree.blockSignals(True)
        try:
            self.tex_tree.clear()
            self.tex_detail.setText("")
            mesh_keys = sorted({e.mesh_key for e in entries if e.mesh_key})
            # also include meshes that have geometry but no tex refs yet
            for p in self._mesh_paths:
                if p.name not in mesh_keys:
                    mesh_keys.append(p.name)
            multi = len(mesh_keys) > 1
            if not multi:
                mk = mesh_keys[0] if mesh_keys else ""
                groups = self._group_entries(entries)
                self._add_mat_groups(self.tex_tree, groups, mesh_key=mk)
            else:
                for mk in mesh_keys:
                    mesh_item = QTreeWidgetItem([mk, "mesh", "ok"])
                    mesh_item.setData(0, ROLE_KIND, "mesh")
                    mesh_item.setData(0, ROLE_MESH_KEY, mk)
                    mesh_item.setData(0, ROLE_STEM, "")
                    mesh_item.setData(
                        0,
                        ROLE_GROUP_STEMS,
                        [e.stem for e in entries if e.mesh_key == mk],
                    )
                    font = mesh_item.font(0)
                    font.setBold(True)
                    mesh_item.setFont(0, font)
                    mesh_item.setToolTip(0, f"Materials for {mk}")
                    sub = [e for e in entries if e.mesh_key == mk]
                    self._add_mat_groups(mesh_item, self._group_entries(sub), mesh_key=mk)
                    self.tex_tree.addTopLevelItem(mesh_item)
                    mesh_item.setExpanded(True)

            if not entries:
                self.tex_detail.setText("(no materials or .texture.txt)")
            # All materials default: nothing selected in the mat list
            self.tex_tree.clearSelection()
            self.tex_tree.setCurrentItem(None)
        finally:
            self.tex_tree.blockSignals(False)
        _refit_side_table(self.tex_tree)
        self._clear_mat_highlight()
        self._apply_tex_filter()
        self._sync_editor_texture_list()

    def _iter_selected_items(self) -> list[QTreeWidgetItem]:
        return list(self.tex_tree.selectedItems())

    def _selected_stems(self) -> set[str]:
        stems: set[str] = set()
        for item in self._iter_selected_items():
            kind = item.data(0, ROLE_KIND)
            if kind in ("group", "mesh"):
                for st in item.data(0, ROLE_GROUP_STEMS) or []:
                    if st:
                        stems.add(str(st))
            else:
                st = item.data(0, ROLE_STEM)
                if st:
                    stems.add(str(st))
        return stems

    def _selected_mesh_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self._iter_selected_items():
            mk = item.data(0, ROLE_MESH_KEY)
            if mk:
                keys.add(str(mk))
            if item.data(0, ROLE_KIND) == "mesh":
                keys.add(str(item.text(0)))
        return keys

    def _selected_texture_txt(self) -> Path | None:
        for item in self._iter_selected_items():
            raw = item.data(0, ROLE_PATH)
            if raw:
                p = Path(str(raw))
                if p.is_file() and p.name.lower().endswith(".texture.txt"):
                    return p
            r = item.data(0, ROLE_REPORT)
            if isinstance(r, TextureReport) and r.path.is_file():
                if r.path.name.lower().endswith(".texture.txt"):
                    return r.path
            # group: dig into children
            if item.data(0, ROLE_KIND) == "group":
                for i in range(item.childCount()):
                    ch = item.child(i)
                    raw = ch.data(0, ROLE_PATH)
                    if raw:
                        p = Path(str(raw))
                        if p.is_file() and p.name.lower().endswith(".texture.txt"):
                            return p
        return None

    def _select_stem(self, stem: str) -> None:
        stem = texture_stem(stem)
        for i in range(self.tex_tree.topLevelItemCount()):
            parent = self.tex_tree.topLevelItem(i)
            if parent is None:
                continue
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child and child.data(0, ROLE_STEM) == stem:
                    parent.setExpanded(True)
                    self.tex_tree.setCurrentItem(child)
                    return
            # lone / group match
            g_stems = parent.data(0, ROLE_GROUP_STEMS) or []
            if stem in g_stems and parent.childCount() == 0:
                self.tex_tree.setCurrentItem(parent)
                return

    def _on_tex_mode_changed(self, _idx: int = 0) -> None:
        self._tex_mode = str(self.tex_mode_combo.currentData() or "all")
        if hasattr(self, "_settings_tex_mode"):
            self._settings_tex_mode.blockSignals(True)
            self._settings_tex_mode.setCurrentIndex(0 if self._tex_mode == "all" else 1)
            self._settings_tex_mode.blockSignals(False)
        if self._tex_mode == "all":
            # All materials: start with empty mat-list selection (no highlight)
            self.tex_tree.blockSignals(True)
            self.tex_tree.clearSelection()
            self.tex_tree.setCurrentItem(None)
            self.tex_tree.blockSignals(False)
            self.tex_detail.setText("")
            self._clear_mat_highlight()
        self._apply_tex_filter()

    def _clear_mat_highlight(self) -> None:
        if self.view is None:
            return
        if self._mesh_hl:
            self._apply_mesh_hl(frame=False, quiet=True)
            return
        self.view.set_mat_highlight(None)

    def _sync_mat_highlight(self) -> None:
        """Click a mat → orange AABB + fly-to matching geometry (All materials too)."""
        if self.view is None:
            return
        stems = self._selected_stems()
        mesh_keys = self._selected_mesh_keys()
        if not stems and not mesh_keys:
            self._clear_mat_highlight()
            return
        n = self.view.set_mat_highlight(stems, mesh_keys, frame=True)
        if not stems and not mesh_keys:
            pass
        elif n <= 0:
            self._status.showMessage(
                "Mat highlight: no geometry uses this map "
                "(folder-only / unused texture?)"
            )
        else:
            self._status.showMessage(
                f"Mat highlight: {n} part(s) · glowing outline"
            )

    def _on_tex_selection_changed(self) -> None:
        items = self._iter_selected_items()
        if items:
            item = items[0]
            if item.data(0, ROLE_KIND) == "group":
                stems = item.data(0, ROLE_GROUP_STEMS) or []
                self.tex_detail.setText(
                    f"Material family · {len(stems)} map(s)\n" + " · ".join(stems)
                )
            elif item.data(0, ROLE_KIND) == "mesh":
                self.tex_detail.setText(f"Mesh · {item.text(0)}")
            else:
                r = item.data(0, ROLE_REPORT)
                if isinstance(r, TextureReport):
                    self.tex_detail.setText(format_report(r))
                else:
                    stem = item.data(0, ROLE_STEM)
                    role = item.data(0, ROLE_MAP_ROLE) or ""
                    self.tex_detail.setText(f"Scene map · {role}\n{stem}")
        else:
            self.tex_detail.setText("")
        self._apply_tex_filter()
        self._sync_mat_highlight()  # after filter so status isn't overwritten

    def _apply_tex_filter(self) -> None:
        if self._applying_filter:
            return
        mode = self._tex_mode
        stems = self._selected_stems() if mode == "selected" else set()
        mesh_keys = self._selected_mesh_keys() if mode == "selected" else set()
        if self.view is not None:
            self.view.set_texture_filter(mode, stems, mesh_keys=mesh_keys)
        if mode == "all":
            self._status.showMessage("Texture view: All materials (per-part maps)")
        elif not stems and not mesh_keys:
            self._status.showMessage("Texture view: Selected only — pick a mesh / family / map")
        else:
            mesh_bit = f" · {len(mesh_keys)} mesh" if mesh_keys else ""
            self._status.showMessage(
                f"Texture view: Selected only — {len(stems)} stem(s){mesh_bit}"
            )

    def _on_tex_context_menu(self, pos: QPoint) -> None:
        item = self.tex_tree.itemAt(pos)
        if item is None:
            return
        if item not in self.tex_tree.selectedItems():
            self.tex_tree.setCurrentItem(item)
        stems = self._selected_stems()
        menu = QMenu(self)
        act_match = menu.addAction("Preview matching parts only")
        act_illum = menu.addAction("Preview as Self-Illum (onetex)")
        act_pbr = menu.addAction("Preview as PBR (clear self-illum override)")
        menu.addSeparator()
        act_edit = menu.addAction("Open in Editor")
        act_force = menu.addAction("Force as albedo on selection")
        act_reveal = menu.addAction("Reveal file")
        chosen = menu.exec(self.tex_tree.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_match:
            self.tex_mode_combo.setCurrentIndex(1)
            self._tex_mode = "selected"
            if self.view is not None:
                self.view.set_self_illum_stems(None)
            self._apply_tex_filter()
            self._set_page("preview")
        elif chosen is act_illum:
            self.tex_mode_combo.setCurrentIndex(1)
            self._tex_mode = "selected"
            if self.view is not None:
                self.view.set_texture_filter(
                    "selected", stems, mesh_keys=self._selected_mesh_keys()
                )
                self.view.set_self_illum_stems(stems, boost=0.65)
            self._status.showMessage(f"Self-Illum preview: {', '.join(sorted(stems))}")
            self._set_page("preview")
        elif chosen is act_pbr:
            if self.view is not None:
                self.view.set_self_illum_stems(None)
            self._status.showMessage("Self-Illum override cleared (PBR)")
        elif chosen is act_edit:
            self._set_page("meshes")
        elif chosen is act_force:
            self._force_albedo_on_selection(stems)
        elif chosen is act_reveal:
            path = self._selected_texture_txt()
            if path is None:
                raw = item.data(0, ROLE_PATH)
                path = Path(str(raw)) if raw else None
            if path and path.exists():
                self._reveal_path(path)
            else:
                self._status.showMessage("No file path to reveal")

    def _force_albedo_on_selection(self, stems: set[str]) -> None:
        if self.view is None or not stems:
            return
        img: Path | None = None
        for item in self._iter_selected_items():
            targets = [item]
            if item.data(0, ROLE_KIND) == "group":
                targets = [item.child(i) for i in range(item.childCount())]
            for t in targets:
                r = t.data(0, ROLE_REPORT)
                if isinstance(r, TextureReport):
                    img = resolve_primary_image(r)
                    if img is not None:
                        break
            if img is not None:
                break
        if img is None:
            self._status.showMessage("No Primary image for Force as albedo")
            return
        self.view.set_albedo_force_on_stems(img, stems)
        self.view.set_texture_filter("selected", stems, mesh_keys=self._selected_mesh_keys())
        self.tex_mode_combo.setCurrentIndex(1)
        self._tex_mode = "selected"
        self._status.showMessage(f"Forced albedo on selection: {img.name}")
        self._set_page("preview")

    def _reveal_path(self, path: Path) -> None:
        import subprocess

        path = path.resolve()
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except OSError as e:
            self._status.showMessage(f"Reveal failed: {e}")

    def _on_editor_saved(self, path: Path) -> None:
        self._status.showMessage(f"Saved {path.name}")
        self._rebuild_tex_list()

    def _family_stems_for_texture(self, path: Path | None) -> set[str]:
        """Stems in the open scene that share the material family of this .texture.txt."""
        if path is None:
            return set()
        stem = texture_stem(path.name)
        fam, _role = material_family(stem)
        stems: set[str] = {stem} if stem else set()
        if not fam:
            return stems
        for part in self._scene.parts:
            for ref in (part.albedo_ref, part.normal_ref, part.parameter_ref):
                if not ref:
                    continue
                s = texture_stem(ref)
                if not s:
                    continue
                f2, _ = material_family(s)
                if f2 == fam:
                    stems.add(s)
        return stems

    def _on_editor_texture_selected(self, path: object) -> None:
        p = Path(path) if path else None
        self._editor_tex_stems = self._family_stems_for_texture(p)
        # re-apply current material preview against new stems
        en, e, r, m, s = self.editor.texture.material_preview_state()
        self._on_editor_material_preview(en, e, r, m, s)
        self._sync_editor_two_sided(p)

    def _parts_for_texture_family(self, path: Path | None) -> list:
        stems = self._family_stems_for_texture(path)
        if not stems:
            return []
        out = []
        for part in self._scene.parts:
            refs = {
                texture_stem(r)
                for r in (
                    part.albedo_ref,
                    part.normal_ref,
                    part.parameter_ref,
                    part.albedo_path or "",
                    part.name,
                )
                if r
            }
            if stems_match(refs, stems):
                out.append(part)
        return out

    def _sync_editor_two_sided(self, path: Path | None) -> None:
        parts = self._parts_for_texture_family(path)
        mat_name = ""
        checked = False
        if parts:
            # prefer first named part; majority vote for two_sided
            names = [p.name for p in parts if p.name]
            mat_name = names[0] if names else ""
            flags = [bool(p.two_sided) for p in parts]
            checked = sum(1 for f in flags if f) >= max(1, (len(flags) + 1) // 2)

        mesh_path = self._mesh_path
        if parts and getattr(parts[0], "mesh_key", ""):
            key = parts[0].mesh_key
            mesh_path = next((p for p in self._mesh_paths if p.name == key), mesh_path)

        meta = find_mesh_meta(mesh_path) if mesh_path else None
        meta_target = mesh_meta_path(mesh_path) if mesh_path else None
        if mat_name and meta is not None:
            from_meta = read_two_sided(meta, mat_name)
            if from_meta is not None:
                checked = from_meta
        tip = ""
        if meta_target is not None:
            state = "exists" if meta_target.is_file() else "will create on Save"
            tip = (
                f"Mesh meta ({state}): {meta_target.name} · "
                f"materials {{ {mat_name or '…'} {{ two-sided }} }}"
            )
            if mesh_path is not None and mesh_path.suffix.lower() == ".trainzmesh":
                tip += " · also toggles viewport cull; Save mesh.txt for Trainz"
        self.editor.texture.set_two_sided_context(
            meta_target, mat_name, checked, tip=tip
        )

    def _on_editor_two_sided(self, on: bool, material: str) -> None:
        stems = getattr(self, "_editor_tex_stems", set()) or set()
        if self.view is not None and stems:
            self.view.set_two_sided_for_stems(stems, on)
        flag = "on" if on else "off"
        mat = material or "(family)"
        self._status.showMessage(
            f"Two-sided {flag} · {mat} · preview updated — "
            "Save two-sided → mesh.txt to persist for Trainz/FBX"
        )

    def _on_editor_material_preview(
        self,
        enabled: bool,
        emissive: float,
        roughness: float,
        metal: float,
        specular: float,
    ) -> None:
        if self.view is None:
            return
        stems = getattr(self, "_editor_tex_stems", set()) or set()
        if enabled and stems:
            self.view.set_material_preview(
                stems,
                enabled=True,
                emissive=emissive,
                roughness=roughness,
                metal=metal,
                specular=specular,
            )
            self._status.showMessage(
                f"Material preview · {len(stems)} stem(s) · "
                f"E{emissive:.2f} R{roughness:.2f} M{metal:.2f} S{specular:.2f} "
                "(preview only — Save writes .texture.txt text, not parameter RGB)"
            )
        else:
            self.view.clear_material_preview()

    # ── animations ───────────────────────────────────────────

    def _fill_anims(self, scene: Scene) -> None:
        self._stop_anim()
        self.anim_list.blockSignals(True)
        self.anim_list.clear()
        self._anim_clip = None
        for clip in scene.anims:
            label = clip.name or clip.path.name
            if clip.frame_count:
                label = f"{label}  ({clip.frame_count}f)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, clip)
            self.anim_list.addItem(item)
        self.anim_list.blockSignals(False)
        _refit_side_table(self.anim_list)
        empty = len(scene.anims) == 0
        self._anim_empty.setVisible(empty)
        self._frame_slider.blockSignals(True)
        self._frame_slider.setValue(0)
        self._frame_slider.setMaximum(DUMMY_FRAMES)
        self._frame_slider.blockSignals(False)

    def _add_kin(self, path: Path) -> None:
        clip = peek_kin(path)
        for existing in self._scene.anims:
            if existing.path.resolve() == path.resolve():
                self._status.showMessage(f"Already listed: {path.name}")
                self._fill_anims(self._scene)
                return
        self._scene.anims.append(clip)
        self._fill_anims(self._scene)
        self._status.showMessage(f"Added .kin: {path.name} — {clip.note}")

    def _on_anim_select(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            return
        clip = cur.data(Qt.ItemDataRole.UserRole)
        if not isinstance(clip, AnimClip):
            return
        self._anim_clip = clip
        max_f = clip.frame_count if clip.frame_count > 0 else DUMMY_FRAMES
        self._frame_slider.blockSignals(True)
        self._frame_slider.setMaximum(max(max_f, 1))
        self._frame_slider.setValue(0)
        self._frame_slider.blockSignals(False)
        note = clip.note or "(no note)"
        self._status.showMessage(
            f"{clip.name}: frames={clip.frame_count}  bones={len(clip.bone_names)}  {note}"
        )
        if self.view is not None:
            self.view.set_anim_time(0.0)

    def _toggle_play(self) -> None:
        if self._anim_playing:
            self._stop_anim()
            return
        self._anim_playing = True
        self._play_btn.setText("Pause")
        if self._anim_clip is None or self._anim_clip.frame_count <= 0:
            self._status.showMessage(
                "Playback scrub only — .kin bone decode not wired; use skinned mesh + decoder"
            )
        self._anim_timer.start()

    def _stop_anim(self) -> None:
        self._anim_playing = False
        btn = getattr(self, "_play_btn", None)
        if btn is not None:
            btn.setText("Play")
        self._anim_timer.stop()

    def _tick_anim(self) -> None:
        mx = self._frame_slider.maximum()
        nxt = self._frame_slider.value() + 1
        if nxt > mx:
            nxt = 0
        self._frame_slider.setValue(nxt)

    def _on_frame_scrub(self, value: int) -> None:
        mx = max(self._frame_slider.maximum(), 1)
        t = value / float(mx)
        if self.view is not None:
            self.view.set_anim_time(t)

    # ── load callbacks ───────────────────────────────────────

    def _on_load_err(self, msg: str) -> None:
        self._hide_overlay()
        QMessageBox.critical(self, "Load failed", msg)
        self._status.showMessage("Load failed")

    def _on_loaded(
        self,
        paths: Path | list[Path],
        scene: Scene,
        decoded: dict | None = None,
        *,
        mode: str = "replace",
    ) -> None:
        # Mesh → viewport first; side UI / lamps after so open feels instant.
        self._overlay.set_stage("Uploading mesh…", 96)
        self._studio_mode = "mesh"

        path_list = [paths] if isinstance(paths, Path) else list(paths)
        if mode == "replace":
            self._mesh_paths = list(path_list)
            self._lamps = []
            self._hidden_mesh_keys.clear()
            self._two_sided_pending = {}
        else:
            for p in path_list:
                if all(x.resolve() != p.resolve() for x in self._mesh_paths):
                    self._mesh_paths.append(p)
                # freshly added mesh starts visible
                self._hidden_mesh_keys.discard(p.name)

        self._scene = scene
        self._mesh_path = self._mesh_paths[-1] if self._mesh_paths else None
        self._mesh_folder = self._mesh_path.parent if self._mesh_path else None
        # Apply Trainz mesh-meta two-sided before GL batches rebuild
        for mp in self._mesh_paths:
            meta = find_mesh_meta(mp)
            if meta is None:
                continue
            parts = [p for p in scene.parts if (p.mesh_key or mp.name) == mp.name]
            apply_meta_two_sided_to_parts(parts or scene.parts, meta)

        if len(self._mesh_paths) > 1:
            title = f"{len(self._mesh_paths)} meshes"
            self.setWindowTitle(f"MSTN Trainz Studio — {title}")
        else:
            self.setWindowTitle(f"MSTN Trainz Studio — {path_list[0].name}")

        self._editor_populated_key = ""
        self._tzmf_dirty = False
        self._autosave_pending = False
        self._history.clear()
        self._refresh_history_actions()

        need_gl = bool(scene.parts) or bool(scene.attachments)
        if need_gl:
            if not self._ensure_gl():
                self.editor.hide()
                self._studio_mode = "mesh"
                self._hub.setCurrentIndex(HUB_MESH)
                fade_stack_to(self._stack, STACK_HUB)
                self.pbr_hud.hide()
                self._apply_studio_chrome()
            else:
                assert self.view is not None
                # Seed BEFORE set_scene; purge keeps decoded cache now.
                if decoded:
                    self.view.seed_decoded_textures(decoded)
                self.view.set_scene(scene)
                if hasattr(self, "_env_combo"):
                    self.view.set_environment(str(self._env_combo.currentData() or "none"))
                self.view.set_shading(self._shading_mode)
                if hasattr(self, "_ground_cb"):
                    self.view.set_show_ground(self._ground_cb.isChecked())
                self._push_lights_to_view()
                self._tex_mode = "all"
                self.tex_mode_combo.setCurrentIndex(0)
                self.view.set_texture_filter("all", set())
                self._set_page("preview")
        else:
            self.editor.hide()
            self._studio_mode = "mesh"
            self._hub.setCurrentIndex(HUB_MESH)
            fade_stack_to(self._stack, STACK_HUB)
            self.pbr_hud.hide()
            self._apply_studio_chrome()

        self._hide_overlay()
        n_tex = len(decoded) if decoded else 0
        label = ", ".join(p.name for p in path_list[:3])
        if len(path_list) > 3:
            label += f" +{len(path_list) - 3}"
        self._status.showMessage(
            f"Loaded {label} — {scene.vertex_count:,} verts · {n_tex} textures precached"
        )
        # Side lists / Editor / lamps after first paint (island scan can be heavy).
        QTimer.singleShot(
            0,
            lambda sc=scene, pl=path_list: self._finish_mesh_open_ui(sc, pl),
        )
        if scene.kind == "trainzmesh" and not scene.parts:
            QMessageBox.information(
                self,
                "trainzmesh",
                "Could not decode geometry from this .trainzmesh.\n"
                "Open a sibling .fbx if available, or check the file.\n\n"
                "If a sibling .fbx exists, open that for preview.",
            )
        self._finish_pending_project()

    def _finish_mesh_open_ui(self, scene: Scene, path_list: list[Path]) -> None:
        """Deferred UI after viewport has geometry — keeps open feeling snappy."""
        if self._scene is not scene:
            return
        if len(self._mesh_paths) == 1 and scene.kind == "im":
            self._bind_im_document(self._mesh_paths[0], scene)
        else:
            self._im_doc = None
        self._refill_mesh_list()
        self._refill_att_list(scene)
        self._update_scene_cap_tip()
        self._refresh_editor_dock(force=True)
        self._update_stats(self._mesh_path, scene)
        self._rebuild_tex_list()
        self._fill_anims(scene)
        if self.view is not None and (scene.parts or scene.attachments):
            self._rescan_lamps()
        QTimer.singleShot(60, self._refresh_side_frost)
        # App-wide VE Rules — mesh folder + files (status bar; dialog on errors)
        QTimer.singleShot(200, lambda pl=list(path_list): self._ve_scan_auto(pl))

    def _refill_mesh_list(self) -> None:
        self._suppress_mesh_hl += 1
        try:
            self._refill_mesh_list_body()
        finally:
            self._suppress_mesh_hl -= 1

    def _refill_mesh_list_body(self) -> None:
        self.mesh_list.blockSignals(True)
        self.mesh_list.setRowCount(0)
        for p in self._mesh_paths:
            parts = [x for x in self._scene.parts if (x.mesh_key or "") == p.name]
            verts = int(sum(x.vertices.shape[0] for x in parts)) if parts else 0
            faces = int(sum(x.indices.shape[0] // 3 for x in parts)) if parts else 0
            r = self.mesh_list.rowCount()
            self.mesh_list.insertRow(r)
            show_it = QTableWidgetItem("")
            show_it.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            show_it.setCheckState(
                Qt.CheckState.Unchecked
                if p.name in self._hidden_mesh_keys
                else Qt.CheckState.Checked
            )
            show_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            show_it.setToolTip("Draw this mesh in the viewport")
            faces_it = QTableWidgetItem(f"{faces:,}")
            faces_it.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            faces_it.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            name_it = QTableWidgetItem(p.name)
            name_it.setData(Qt.ItemDataRole.UserRole, p.name)
            name_it.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            name_it.setToolTip(
                f"{p}\n{verts:,} verts · {faces:,} faces · {len(parts)} parts"
            )
            self.mesh_list.setItem(r, _MESH_COL_SHOW, show_it)
            self.mesh_list.setItem(r, _MESH_COL_FACES, faces_it)
            self.mesh_list.setItem(r, _MESH_COL_NAME, name_it)
        self.mesh_list.blockSignals(False)
        n = self.mesh_list.rowCount()
        block = getattr(self, "_mesh_list_block", None)
        if block is not None:
            block.setVisible(n > 0)
        if n > 0:
            _refit_side_table(self.mesh_list, rows=min(n, SIDE_TABLE_ROWS))
            self.mesh_list.selectRow(0)
            self._on_mesh_head_select()
        else:
            self._fill_mesh_detail(None)
        self._push_mesh_visibility()

    def _remove_selected_meshes(self) -> None:
        keys: set[str] = set()
        for idx in self.mesh_list.selectionModel().selectedRows(_MESH_COL_NAME):
            it = self.mesh_list.item(idx.row(), _MESH_COL_NAME)
            if it is None:
                continue
            key = str(it.data(Qt.ItemDataRole.UserRole) or it.text() or "")
            if key:
                keys.add(key)
        if not keys:
            return
        self._mesh_paths = [p for p in self._mesh_paths if p.name not in keys]
        self._scene.parts = [p for p in self._scene.parts if (p.mesh_key or "") not in keys]
        # drop attachments prefixed with removed mesh stems
        stems = {Path(k).stem for k in keys}
        self._scene.attachments = [
            a
            for a in self._scene.attachments
            if not any(a.name.startswith(f"{s}/") for s in stems)
        ]
        self._lamps = [L for L in self._lamps if L.mesh_key not in keys]
        self._hidden_mesh_keys -= keys
        self._mesh_path = self._mesh_paths[-1] if self._mesh_paths else None
        self._mesh_folder = self._mesh_path.parent if self._mesh_path else None
        if len(self._mesh_paths) <= 1 and self._scene.parts:
            # collapse kind if single remaining
            remaining = {p.mesh_key for p in self._scene.parts if p.mesh_key}
            if len(remaining) <= 1:
                self._scene.kind = self._mesh_paths[0].suffix.lstrip(".") if self._mesh_paths else self._scene.kind
        self._refill_mesh_list()
        self._refill_att_list(self._scene)
        self._rebuild_tex_list()
        self._refill_lamp_list()
        self._update_stats(self._mesh_path, self._scene)
        if self.view is not None:
            self.view.set_scene(self._scene)
            self._push_mesh_visibility()
            self._push_lamps_to_view()
        if not self._mesh_paths:
            self.setWindowTitle("MSTN Mesh Studio")
            self._status.showMessage("All meshes removed")
        else:
            self._status.showMessage(f"Removed {', '.join(sorted(keys))}")

    def _clear_meshes(self) -> None:
        """Unload every mesh — empty preview ready for a new Open / drop."""
        if not self._mesh_paths and not self._scene.parts:
            self._status.showMessage("No meshes to clear")
            return
        self._mesh_paths = []
        self._mesh_path = None
        self._mesh_folder = None
        self._hidden_mesh_keys.clear()
        self._scene = Scene()
        self._lamps = []
        self._tzmf_bytes = None
        self._tzmf_dirty = False
        self._two_sided_pending = {}
        self._autosave_pending = False
        self._im_doc = None
        self._editor_populated_key = ""
        self._history.clear()
        self._refresh_history_actions()
        self._refill_mesh_list()
        self._refill_att_list(self._scene)
        self._rebuild_tex_list()
        self._fill_anims(self._scene)
        self._refill_lamp_list()
        self._update_stats(None, self._scene)
        self._update_scene_cap_tip()
        if hasattr(self, "editor") and self.editor is not None:
            self._refresh_editor_dock(force=True)
        if self.view is not None:
            self.view.set_scene(self._scene)
            self._push_mesh_visibility()
            self._push_lamps_to_view()
        self.setWindowTitle("MSTN Mesh Studio")
        self._status.showMessage("Meshes cleared — Open or drop a new mesh")

    def _bind_im_document(self, path: Path, scene: Scene) -> None:
        self._im_doc = None
        if scene.kind != "im":
            return
        from ..lib.im_editor.core import ImDocument

        doc = ImDocument()
        doc.open(path)
        self._im_doc = doc

    def _refill_att_list(self, scene: Scene) -> None:
        self.att_list.blockSignals(True)
        self.att_list.clear()
        self._ed_att_list.blockSignals(True)
        self._ed_att_list.clear()
        for i, a in enumerate(scene.attachments):
            item = QListWidgetItem(a.name)
            item.setData(Qt.ItemDataRole.UserRole, a)
            item.setData(Qt.ItemDataRole.UserRole + 1, i)
            self.att_list.addItem(item)
            ed_item = QListWidgetItem(a.name)
            ed_item.setData(Qt.ItemDataRole.UserRole, a)
            ed_item.setData(Qt.ItemDataRole.UserRole + 1, i)
            self._ed_att_list.addItem(ed_item)
        self.att_list.blockSignals(False)
        self._ed_att_list.blockSignals(False)
        _refit_side_table(self.att_list)
        _refit_side_table(self._ed_att_list)

    def _update_scene_cap_tip(self) -> None:
        kind = self._scene.kind
        if len(self._mesh_paths) > 1 or kind == "multi":
            self._scene_cap_tip.setText("Multi-mesh · edit .im on Editor (single only)")
            self._scene_cap_tip.setToolTip(
                f"{len(self._mesh_paths)} meshes: "
                + ", ".join(x.name for x in self._mesh_paths[:6])
            )
            return
        if kind == "trainzmesh":
            self._scene_cap_tip.setText("Editor: Meshes + a.* · Save writes binary")
            self._scene_cap_tip.setToolTip(
                "Editor dock edits materials / attachments; Save writes .trainzmesh (+ .bak)."
            )
        elif kind == "im":
            self._scene_cap_tip.setText("Click to fly · Edit on Editor page")
            self._scene_cap_tip.setToolTip(
                ".im ATCH: Add / move / Save on Editor (.im.bak once)."
            )
        elif kind == "fbx":
            self._scene_cap_tip.setText("FBX preview-only (no attach write)")
            self._scene_cap_tip.setToolTip(
                "Attachments from FBX are preview-only. Open .trainzmesh / .im to Save."
            )
        else:
            self._scene_cap_tip.setText("Click to fly · Edit on Editor page")
            self._scene_cap_tip.setToolTip(
                "Editor Save writes .im / .trainzmesh in Studio (no external app)."
            )

    def _sync_scene_atts_from_im(self) -> None:
        if self._im_doc is None:
            return
        from ..io.scene import Attachment as SceneAtt

        sel = self.att_list.currentRow()
        ed_sel = self._ed_att_list.currentRow()
        keep = ed_sel if ed_sel >= 0 else sel
        self._scene.attachments = [
            SceneAtt(name=a.name, pos=tuple(a.pos), orient=tuple(a.orient))  # type: ignore[arg-type]
            for a in self._im_doc.atts
        ]
        self._refill_att_list(self._scene)
        if 0 <= keep < self.att_list.count():
            self.att_list.setCurrentRow(keep)
            self._ed_att_list.setCurrentRow(keep)
        if self.view is not None:
            # in-place — avoid set_scene camera/filter reset
            self.view._scene.attachments = self._scene.attachments
            self.view.update()
        self._update_stats(self._mesh_path, self._scene)

    def _fill_att_spinboxes(self, a) -> None:
        self._att_x.blockSignals(True)
        self._att_y.blockSignals(True)
        self._att_z.blockSignals(True)
        self._att_name.blockSignals(True)
        self._att_x.setValue(float(a.pos[0]))
        self._att_y.setValue(float(a.pos[1]))
        self._att_z.setValue(float(a.pos[2]))
        self._att_name.setText(str(a.name))
        self._att_x.blockSignals(False)
        self._att_y.blockSignals(False)
        self._att_z.blockSignals(False)
        self._att_name.blockSignals(False)

    def _frame_attachment(self, a) -> None:
        if self.view is not None:
            self.view.fly_to(a.pos, duration_s=0.55, approach=True)
        pos = f"pos=({a.pos[0]:.4f}, {a.pos[1]:.4f}, {a.pos[2]:.4f})"
        if self._in_editor_page():
            if getattr(self, "_att_edit_mode", ATT_EDIT_VIEW) == ATT_EDIT_MOVE:
                self._status.showMessage(
                    f"{a.name}  {pos}  · Move: drag axis/center · Shift=fine · Alt+LMB pick"
                )
            else:
                self._status.showMessage(
                    f"{a.name}  {pos}  · View only · Tab→Move to drag · Alt+LMB pick"
                )
        else:
            self._status.showMessage(
                f"{a.name}  {pos}  · Alt+LMB pick a.* · Preview (no drag)"
            )

    def _on_att_viewport_picked(self, index: int) -> None:
        """Alt+LMB on a.* gizmo in the viewport → select left list + Editor detail."""
        if index < 0 or index >= len(self._scene.attachments):
            return
        a = self._scene.attachments[index]
        # sync Scene list without triggering a fly-to (already looking at it)
        if self.att_list.currentRow() != index:
            self.att_list.blockSignals(True)
            self.att_list.setCurrentRow(index)
            self.att_list.blockSignals(False)
        if self._ed_att_list.currentRow() != index:
            self._ed_att_list.blockSignals(True)
            self._ed_att_list.setCurrentRow(index)
            self._ed_att_list.blockSignals(False)
        self._fill_att_spinboxes(a)
        self._set_view_edit_attachment(index)
        if self._in_editor_page():
            if self.editor.current_mode() != "attachments":
                self.editor.show_attachments_tab()
            self.editor.attachments_page.select_row(index)
            self._set_scene_list_mode("atts")
        pos = f"({a.pos[0]:.4f}, {a.pos[1]:.4f}, {a.pos[2]:.4f})"
        self._status.showMessage(f"Picked {a.name}  {pos}  · Alt+LMB")

    def _att_viewport_editable(self) -> bool:
        """LMB translate only on Editor + Move mode (Tab pie)."""
        return (
            self._in_editor_page()
            and getattr(self, "_att_edit_mode", ATT_EDIT_VIEW) == ATT_EDIT_MOVE
        )

    def _set_view_edit_attachment(self, row: int) -> None:
        if self.view is None:
            return
        editable = self._att_viewport_editable()
        if 0 <= row < len(self._scene.attachments):
            self.view.set_selected_attachment(row, editable=editable)
        else:
            self.view.set_selected_attachment(None)

    def _sync_att_viewport_mode(self) -> None:
        """Re-apply selection after Preview↔Editor so drag only arms on Editor."""
        if self.view is None:
            return
        row = -1
        if self._in_editor_page():
            row = self._ed_att_list.currentRow()
        else:
            row = self.att_list.currentRow()
        self._set_view_edit_attachment(row)

    def _on_att_select(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            if self.view is not None:
                self.view.set_selected_attachment(None)
            return
        a = cur.data(Qt.ItemDataRole.UserRole)
        if a is None:
            return
        row = self.att_list.currentRow()
        if self._ed_att_list.currentRow() != row:
            self._ed_att_list.blockSignals(True)
            self._ed_att_list.setCurrentRow(row)
            self._ed_att_list.blockSignals(False)
        self._fill_att_spinboxes(a)
        self._set_view_edit_attachment(row)
        self._frame_attachment(a)
        # left → right Editor detail
        if self._in_editor_page():
            if self.editor.current_mode() != "attachments":
                self.editor.show_attachments_tab()
            self.editor.attachments_page.select_row(row)

    def _on_ed_att_row(self, row: int) -> None:
        if row < 0 or row >= len(self._scene.attachments):
            if self.view is not None:
                self.view.set_selected_attachment(None)
            return
        a = self._scene.attachments[row]
        if self.att_list.currentRow() != row:
            self.att_list.blockSignals(True)
            self.att_list.setCurrentRow(row)
            self.att_list.blockSignals(False)
        if self._ed_att_list.currentRow() != row:
            self._ed_att_list.blockSignals(True)
            self._ed_att_list.setCurrentRow(row)
            self._ed_att_list.blockSignals(False)
        self._fill_att_spinboxes(a)
        self._set_view_edit_attachment(row)
        self._frame_attachment(a)

    def _on_att_viewport_moved(self, index: int, x: float, y: float, z: float) -> None:
        """Live spinbox sync while dragging a.* in the 3D view."""
        if 0 <= index < len(self._scene.attachments):
            self._scene.attachments[index].pos = (x, y, z)
            # keep list UserRole in sync
            for lst in (self.att_list, self._ed_att_list):
                item = lst.item(index)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, self._scene.attachments[index])
        self._att_x.blockSignals(True)
        self._att_y.blockSignals(True)
        self._att_z.blockSignals(True)
        self._att_x.setValue(x)
        self._att_y.setValue(y)
        self._att_z.setValue(z)
        self._att_x.blockSignals(False)
        self._att_y.blockSignals(False)
        self._att_z.blockSignals(False)
        # Detail panel Location = Z-up (viewport is Z-up too)
        ed = self.editor.attachments_page.editor_at(index)
        if ed is not None:
            ed.set_pos_zup((x, y, z))
        name = (
            self._scene.attachments[index].name
            if 0 <= index < len(self._scene.attachments)
            else "?"
        )
        self._status.showMessage(f"{name}  Z-up ({x:.4f}, {y:.4f}, {z:.4f})")

    def _on_att_viewport_drag_started(self, index: int) -> None:
        name = (
            self._scene.attachments[index].name
            if 0 <= index < len(self._scene.attachments)
            else f"a.{index}"
        )
        self._push_history(f"Move {name}", coalesce=False)

    def _on_att_viewport_drag_finished(
        self, index: int, x: float, y: float, z: float
    ) -> None:
        """Commit ImDocument / tzMF buffer update when mouse is released."""
        self._on_att_viewport_moved(index, x, y, z)
        if self._tzmf_bytes is not None and self._scene.kind == "trainzmesh":
            from ..io.tzmf_edit import parse_attachment_records, set_attachment_yup

            recs = parse_attachment_records(self._tzmf_bytes)
            if 0 <= index < len(recs):
                set_attachment_yup(self._tzmf_bytes, recs[index], pos_zup=(x, y, z))
                self._mark_edited()
                self._status.showMessage(
                    f"Moved → Z-up ({x:.4f}, {y:.4f}, {z:.4f}) · Save to write .trainzmesh"
                )
            return
        if self._im_doc is None or self._scene.kind != "im":
            self._status.showMessage(
                f"Preview moved → ({x:.4f}, {y:.4f}, {z:.4f}) · Save when writable"
            )
            return
        if index < 0 or index >= len(self._im_doc.atts):
            return
        try:
            self._im_doc.update_one(index, pos=(x, y, z))
        except Exception as e:
            QMessageBox.warning(self, "Attach move", str(e))
            return
        from ..io.scene import Attachment as SceneAtt

        a = self._im_doc.atts[index]
        self._scene.attachments[index] = SceneAtt(
            name=a.name, pos=tuple(a.pos), orient=tuple(a.orient)  # type: ignore[arg-type]
        )
        if self.view is not None:
            self.view._scene.attachments = self._scene.attachments
        self._status.showMessage(
            f"Applied {a.name} → ({x:.4f}, {y:.4f}, {z:.4f}) · Save (.im) to write disk"
        )

    def _on_att_apply(self) -> None:
        if self._tzmf_bytes is not None and self._scene.kind == "trainzmesh":
            # tree edits already patch buffer; Apply = confirm + refresh lists
            self._refill_att_list(self._scene)
            self._status.showMessage("Applied attachment edits · Save to write .trainzmesh")
            return
        if self._im_doc is None or self._scene.kind != "im":
            self._status.showMessage("Attach write needs a single .im / .trainzmesh")
            return
        row = self._ed_att_list.currentRow()
        if row < 0:
            row = self.att_list.currentRow()
        if row < 0 or row >= len(self._im_doc.atts):
            self._status.showMessage("Select an attachment first")
            return
        name = self._att_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Apply", "Name cannot be empty.")
            return
        if any(i != row and a.name == name for i, a in enumerate(self._im_doc.atts)):
            QMessageBox.warning(self, "Apply", f"Name already used: {name}")
            return
        pos = (self._att_x.value(), self._att_y.value(), self._att_z.value())
        try:
            self._im_doc.update_one(row, name=name, pos=pos)
        except Exception as e:
            QMessageBox.warning(self, "Apply", str(e))
            return
        self._sync_scene_atts_from_im()
        self.att_list.setCurrentRow(row)
        self._ed_att_list.setCurrentRow(row)
        self._status.showMessage(f"Applied {name} → {pos}")

    def _unique_att_name(self, base: str = "a.new") -> str:
        names = {a.name for a in (self._im_doc.atts if self._im_doc else [])}
        if base not in names:
            return base
        n = 2
        while f"{base}{n}" in names:
            n += 1
        return f"{base}{n}"

    def _on_att_add(self) -> None:
        if self._im_doc is None or self._scene.kind != "im":
            self._status.showMessage("Add attachment needs a single .im")
            return
        name = self._att_name.text().strip() or self._unique_att_name()
        if any(a.name == name for a in self._im_doc.atts):
            name = self._unique_att_name(name)
        pos = (self._att_x.value(), self._att_y.value(), self._att_z.value())
        try:
            idx = self._im_doc.add(name, pos=pos)
        except Exception as e:
            QMessageBox.warning(self, "Add", str(e))
            return
        self._sync_scene_atts_from_im()
        self.att_list.setCurrentRow(idx)
        self._ed_att_list.setCurrentRow(idx)
        self._status.showMessage(f"Added {name} at {pos}")

    def _on_att_delete(self) -> None:
        if self._im_doc is None or self._scene.kind != "im":
            self._status.showMessage("Delete needs a single .im")
            return
        row = self._ed_att_list.currentRow()
        if row < 0:
            row = self.att_list.currentRow()
        if row < 0 or row >= len(self._im_doc.atts):
            self._status.showMessage("Select an attachment first")
            return
        name = self._im_doc.atts[row].name
        try:
            self._im_doc.remove(row)
        except Exception as e:
            QMessageBox.warning(self, "Delete", str(e))
            return
        self._sync_scene_atts_from_im()
        self._status.showMessage(f"Deleted {name}")

    def _on_att_save(self) -> None:
        if self._tzmf_bytes is not None and self._scene.kind == "trainzmesh":
            path = self._mesh_path
            if path is None:
                return
            from ..io.tzmf_edit import write_trainzmesh

            try:
                out = write_trainzmesh(path, self._tzmf_bytes, backup=True)
            except OSError as e:
                QMessageBox.critical(self, "Save .trainzmesh failed", str(e))
                return
            self._flush_two_sided_meta(out)
            self._tzmf_dirty = False
            self._autosave_pending = False
            clear_crash_backup()
            self._status.showMessage(f"Saved {out.name} (.trainzmesh.bak once if new)")
            return
        if self._im_doc is None:
            return
        try:
            out = self._im_doc.save()
        except Exception as e:
            QMessageBox.critical(self, "Save .im failed", str(e))
            return
        self._sync_scene_atts_from_im()
        self._mesh_path = out
        self._autosave_pending = False
        clear_crash_backup()
        self._status.showMessage(f"Saved {out} (.im.bak once if new)")

    def _on_att_save_as(self) -> None:
        if self._tzmf_bytes is not None and self._scene.kind == "trainzmesh":
            start = str(self._mesh_path or Path.home())
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save .trainzmesh As",
                start,
                "Trainz mesh (*.trainzmesh);;All (*.*)",
            )
            if not path:
                return
            from ..io.tzmf_edit import write_trainzmesh

            out_path = Path(path)
            try:
                write_trainzmesh(out_path, self._tzmf_bytes, backup=False)
            except OSError as e:
                QMessageBox.critical(self, "Save As failed", str(e))
                return
            self._flush_two_sided_meta(out_path)
            self._mesh_path = out_path
            self._mesh_folder = out_path.parent
            self._tzmf_dirty = False
            self._autosave_pending = False
            clear_crash_backup()
            self.setWindowTitle(f"MSTN Mesh Studio — {out_path.name}")
            self._status.showMessage(f"Saved As {out_path}")
            return
        if self._im_doc is None:
            return
        start = str(self._mesh_path or Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save .im As", start, "Trainz IM (*.im);;All (*.*)"
        )
        if not path:
            return
        try:
            out = self._im_doc.save(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Save As failed", str(e))
            return
        self._mesh_path = out
        self._mesh_folder = out.parent
        self._sync_scene_atts_from_im()
        self.setWindowTitle(f"MSTN Mesh Studio — {out.name}")
        self._status.showMessage(f"Saved As {out}")

    # ── drag / drop ──────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        self._handle_dropped_paths(paths)
        event.acceptProposedAction()

    def _handle_dropped_paths(self, paths: list[Path]) -> None:
        """Route mesh / audio / video / project drops from HOME or window."""
        if not paths:
            return
        hub = getattr(self, "_toasts", None)
        if hub is not None:
            hub.drop(paths)
        if self._busy:
            self._status.showMessage("Busy — wait for current load…")
            return
        # Pure folder drop anywhere → app-wide VE Rules on asset folder(s)
        dirs = [p for p in paths if p.is_dir()]
        files = [p for p in paths if p.is_file()]
        if dirs and not files:
            self.ve_scan(dirs, show_dialog=True, announce=True)
            return
        # Assets Packages — CDP / asset-folder drops (don't swallow as unknown).
        if getattr(self, "_studio_mode", "") == "assets":
            host = getattr(self, "_assets_host", None)
            if host is not None and hasattr(host, "handle_dropped_paths"):
                if host.handle_dropped_paths(paths):
                    return
        from ..audio.classify import partition_paths

        buckets = partition_paths(paths)
        meshes = buckets["mesh"]
        media = buckets["audio"] + buckets["video"]
        projects = buckets["project"]
        others: list[Path] = []
        for p in buckets["other"]:
            name = p.name.lower()
            if p.suffix.lower() == KIN_EXT:
                others.append(p)
            elif name.endswith(".texture.txt") or p.suffix.lower() == ".texture":
                others.append(p)
        if projects and not meshes and not media and not others:
            self._open_project(projects[0])
            return
        if media and not meshes:
            self.enter_sounds_studio(media)
            return
        if media and meshes:
            # Mesh first; queue audio for Sounds after.
            self._pending_sound_paths = list(media)
            self._studio_mode = "mesh"
            if len(meshes) > 1:
                self.open_paths(meshes, mode="replace")
            elif self._scene.parts:
                self.open_paths(meshes, mode="append")
            else:
                self.open_paths(meshes, mode="replace")
            return
        if not meshes and not others:
            if projects:
                self._open_project(projects[0])
                return
            self._status.showMessage(
                "Drop mesh (.fbx/.im/.trainzmesh), audio/video, or .mtzs project"
            )
            return
        if meshes:
            self._studio_mode = "mesh"
            if len(meshes) > 1:
                self.open_paths(meshes, mode="replace")
            elif self._scene.parts:
                self.open_paths(meshes, mode="append")
            else:
                self.open_paths(meshes, mode="replace")
            return
        for p in others:
            self._studio_mode = "mesh"
            self.open_path(p)
            break

    def closeEvent(self, event) -> None:
        if not getattr(self, "_quit_ready", False):
            if getattr(self, "_quit_animating", False):
                event.ignore()
                return
            event.ignore()
            self._quit_animating = True
            bar = getattr(self, "_title_bar", None)
            if bar is not None and hasattr(bar, "_close_menu"):
                bar._close_menu()  # type: ignore[attr-defined]
            from .motion import animate_window_quit

            def _finish() -> None:
                self._quit_ready = True
                self.close()

            animate_window_quit(self, _finish)
            return

        self._stop_anim()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        # Keep self-backup when quitting with unsaved tzMF edits; else clear.
        if self._tzmf_dirty and self._tzmf_bytes is not None:
            try:
                write_crash_backup(self._collect_project_state())
            except OSError:
                pass
        else:
            clear_crash_backup()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    """Entry point — thin boot in ``ui.boot`` (QApp before heavy import)."""
    _install_crash_log()
    from .boot import main as _boot_main

    return _boot_main(argv)
