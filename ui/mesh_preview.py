"""Fast Trainz mesh preview — no HOME / Editor / frost.

Modes:
  --preview FILE                 standalone window (Quick Preview / Open)
  --explorer-preview FILE        embed into Explorer Preview pane HWND
      --parent-hwnd HWND
      --rect L,T,R,B             client rect in parent coords
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QSurfaceFormat, QWindow
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

MESH_EXTS = {".fbx", ".im", ".trainzmesh"}

# Title prefix so the shell handler can FindWindow + MoveWindow on SetRect.
_EMBED_TITLE_PREFIX = "__MSTN_MESH_PREVIEW__"


def _configure_gl_surface() -> None:
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    QSurfaceFormat.setDefaultFormat(fmt)


def parse_preview_argv(argv: list[str]) -> dict:
    """Parse --preview / --explorer-preview flags. Raises ValueError on bad input."""
    mode = None
    parent_hwnd = 0
    rect = (0, 0, 0, 0)
    paths: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--preview", "-p"):
            mode = "preview"
            i += 1
            continue
        if a == "--explorer-preview":
            mode = "explorer"
            i += 1
            continue
        if a.startswith("--parent-hwnd="):
            parent_hwnd = int(a.split("=", 1)[1], 0)
            i += 1
            continue
        if a == "--parent-hwnd":
            i += 1
            if i >= len(argv):
                raise ValueError("--parent-hwnd needs a value")
            parent_hwnd = int(argv[i], 0)
            i += 1
            continue
        if a.startswith("--rect="):
            parts = a.split("=", 1)[1].split(",")
            if len(parts) != 4:
                raise ValueError("--rect needs L,T,R,B")
            rect = tuple(int(x) for x in parts)  # type: ignore[assignment]
            i += 1
            continue
        if a == "--rect":
            i += 1
            if i >= len(argv):
                raise ValueError("--rect needs L,T,R,B")
            parts = argv[i].split(",")
            if len(parts) != 4:
                raise ValueError("--rect needs L,T,R,B")
            rect = tuple(int(x) for x in parts)  # type: ignore[assignment]
            i += 1
            continue
        if a.startswith("-"):
            # ignore unknown flags (forward-compat)
            i += 1
            continue
        paths.append(a)
        i += 1
    if mode is None:
        raise ValueError("need --preview or --explorer-preview")
    if not paths:
        raise ValueError("need a mesh path")
    path = Path(paths[0])
    if path.suffix.lower() not in MESH_EXTS:
        raise ValueError(f"unsupported mesh type: {path.suffix}")
    if not path.is_file():
        raise ValueError(f"file not found: {path}")
    return {
        "mode": mode,
        "path": path,
        "parent_hwnd": int(parent_hwnd),
        "rect": rect,
    }


class _GeoWorker(QThread):
    """Geometry only — textures warm later on the UI thread."""

    ok = Signal(object)
    err = Signal(str)

    def __init__(self, path: Path, parent=None, *, preview_fast: bool = False) -> None:
        super().__init__(parent)
        self.path = path
        self.preview_fast = preview_fast

    def run(self) -> None:
        try:
            from ..io.loaders import load_any

            self.ok.emit(load_any(self.path, preview_fast=self.preview_fast))
        except Exception as exc:
            self.err.emit(f"{exc}\n{traceback.format_exc()}")


class _TexWorker(QThread):
    """PBR maps: albedo ≤2k + full normal/parameter — seed after first geo paint."""

    ok = Signal(object)

    def __init__(self, scene, parent=None) -> None:
        super().__init__(parent)
        self.scene = scene

    def run(self) -> None:
        try:
            from ..io.texcache import (
                PREVIEW_MAX_DIM_ALBEDO,
                collect_scene_texture_paths_split,
                preload_textures,
            )

            albedos, others = collect_scene_texture_paths_split(self.scene.parts)
            decoded: dict = {}
            if albedos:
                decoded.update(
                    preload_textures(
                        albedos, flip_v=False, max_dim=PREVIEW_MAX_DIM_ALBEDO
                    )
                )
            if others:
                # normal + parameter at full res (rough/metal/emis need detail)
                decoded.update(
                    preload_textures(others, flip_v=False, max_dim=0)
                )
            self.ok.emit(decoded)
        except Exception:
            self.ok.emit({})


class _PreviewSurface(QWidget):
    """MeshView + thin status strip — Lit/PBR, or solid fast preview."""

    def __init__(
        self,
        path: Path | None = None,
        parent=None,
        *,
        preview_fast: bool = False,
    ) -> None:
        super().__init__(parent)
        from ..render.view3d import SHADING_RENDERED, SHADING_SOLID, MeshView

        self._path: Path | None = path
        self._preview_fast = preview_fast
        self._SHADING_RENDERED = SHADING_RENDERED
        self._SHADING_SOLID = SHADING_SOLID
        self._geo: _GeoWorker | None = None
        self._tex: _TexWorker | None = None
        self._load_gen = 0

        self.view = MeshView(self)
        self.view.set_show_lamp_gizmos(False)
        self.view.set_show_attachments(False if preview_fast else True)
        self.view.set_environment("none")
        self.view.set_sun(True, 135.0, 45.0, 1.4)
        self.view.set_shading(SHADING_SOLID if preview_fast else SHADING_RENDERED)
        self.view.setMinimumSize(64, 64)

        self.status = QLabel("Ready", self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status.setStyleSheet(
            "QLabel{color:#c8ccd0;background:#1a1d20;padding:4px 8px;"
            "font:11px 'Cascadia Mono',Consolas,monospace;}"
        )
        self.status.setFixedHeight(22)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.status, 0)

        if path is not None:
            self.load_path(path)

    def _stop_workers(self) -> None:
        for worker in (self._geo, self._tex):
            if worker is None:
                continue
            try:
                worker.ok.disconnect()
            except Exception:
                pass
            try:
                worker.err.disconnect()
            except Exception:
                pass
            if worker.isRunning():
                worker.requestInterruption()
                # ponytail: never wait() here — blocks Packages Finder
        self._geo = None
        self._tex = None

    def load_path(self, path: Path, *, preview_fast: bool | None = None) -> None:
        """Load / reload a mesh path (Packages CDP staging + CLI preview)."""
        path = Path(path)
        if preview_fast is not None:
            self._preview_fast = preview_fast
        self._stop_workers()
        self.set_active(True)
        self._path = path
        self._load_gen += 1
        gen = self._load_gen
        mode = "fast" if self._preview_fast else "PBR"
        self.status.setText(f"Loading {path.name} ({mode})…")
        self.view.set_show_attachments(not self._preview_fast)
        self._geo = _GeoWorker(path, self, preview_fast=self._preview_fast)
        self._geo.ok.connect(lambda scene, g=gen: self._on_geo(scene, g))
        self._geo.err.connect(lambda msg, g=gen: self._on_err(msg, g))
        self._geo.start()

    def apply_scene(self, scene, path: Path | None = None, *, preview_fast: bool = True) -> None:
        """Apply a pre-warmed scene (no second parse)."""
        self._stop_workers()
        self.set_active(True)
        self._preview_fast = preview_fast
        if path is not None:
            self._path = Path(path)
        self._load_gen += 1
        self._on_geo(scene, self._load_gen)

    def set_active(self, on: bool) -> None:
        """Stop workers + camera timer when Packages preview is not the front GL."""
        if not on:
            self._stop_workers()
        self.view.set_render_active(on)

    def _on_err(self, msg: str, gen: int | None = None) -> None:
        if gen is not None and gen != self._load_gen:
            return
        self.status.setText(msg.splitlines()[0][:180])

    def _on_geo(self, scene, gen: int | None = None) -> None:
        if gen is not None and gen != self._load_gen:
            return
        self.view.set_scene(scene)
        self.view.set_show_attachments(False if self._preview_fast else True)
        self.view.set_show_lamp_gizmos(False)
        self.view.set_environment("none")
        self.view.set_sun(True, 135.0, 45.0, 1.4)
        if self._preview_fast:
            self.view.set_shading(self._SHADING_SOLID)
        else:
            self.view.set_shading(self._SHADING_RENDERED)
        note = scene.note or scene.kind or ""
        name = self._path.name if self._path else "?"
        if self._preview_fast:
            self.status.setText(
                f"{name}  ·  solid  ·  {scene.vertex_count:,}v  {scene.face_count:,}f"
                + (f"  ·  {note}" if note else "")
            )
            return
        self.status.setText(
            f"{name}  ·  PBR  ·  {scene.vertex_count:,}v  {scene.face_count:,}f"
            f"  ·  {len(scene.attachments)} a.*"
            + (f"  ·  {note}" if note else "")
        )
        if scene.parts:
            self._tex = _TexWorker(scene, self)
            self._tex.ok.connect(lambda decoded, g=gen: self._on_tex(decoded, g))
            self._tex.start()

    def _on_tex(self, decoded: dict, gen: int | None = None) -> None:
        if gen is not None and gen != self._load_gen:
            return
        if decoded:
            self.view.seed_decoded_textures(decoded)
        self.view.set_shading(self._SHADING_RENDERED)
        cur = self.status.text()
        if "tex" not in cur:
            self.status.setText(cur + f"  ·  {len(decoded)} tex")


class FastPreviewWindow(QMainWindow):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.setWindowTitle(f"Mesh Preview — {path.name}")
        self.setMinimumSize(480, 360)
        self.resize(960, 640)
        self.setCentralWidget(_PreviewSurface(path, self))

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
            return
        if key == Qt.Key.Key_F:
            surf = self.centralWidget()
            if isinstance(surf, _PreviewSurface):
                surf.view.reset_camera()
            return
        super().keyPressEvent(event)


def _embed_into_parent(widget: QWidget, parent_hwnd: int, rect: tuple[int, int, int, int]) -> None:
    """Parent Qt widget under Explorer's preview HWND and size to rect.

    Must setParent *before* show — QOpenGLWidget shown as top-level then
    reparented paints white forever in the Preview pane.
    """
    widget.setWindowTitle(f"{_EMBED_TITLE_PREFIX}{int(parent_hwnd)}")
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
    # Dark plate so a failed GL clear never flashes Explorer-white.
    widget.setStyleSheet("background:#1a1d20;")
    l, t, r, b = rect
    w = (r - l) if r > l else 320
    h = (b - t) if b > t else 240
    widget.setGeometry(QRect(0, 0, max(64, w), max(64, h)))
    # Create HWND without mapping, parent under Explorer, then show.
    _ = widget.winId()
    host = QWindow.fromWinId(int(parent_hwnd))
    wh = widget.windowHandle()
    if wh is None:
        raise RuntimeError("no windowHandle after winId")
    wh.setParent(host)
    widget.show()


def run_preview(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")
    os.environ.setdefault("PYOPENGL_ERROR_LOGGING", "0")
    try:
        from ..util.hw import apply_all

        apply_all()
    except Exception:
        pass

    try:
        opts = parse_preview_argv(argv)
    except ValueError as exc:
        print(f"mesh_preview: {exc}", file=sys.stderr)
        return 2

    _configure_gl_surface()
    app = QApplication(argv)
    app.setApplicationName("MSTN Mesh Preview")
    app.setStyle("Fusion")

    path: Path = opts["path"]
    if opts["mode"] == "explorer":
        # Embed: bare surface, no chrome. Solid path — no shadow FBO (white risk).
        surf = _PreviewSurface(None, preview_fast=True)
        try:
            _embed_into_parent(surf, opts["parent_hwnd"], opts["rect"])
            surf.load_path(path, preview_fast=True)
        except Exception as exc:
            surf.setWindowTitle(f"Mesh Preview — {path.name}")
            surf.resize(640, 480)
            surf.show()
            surf.load_path(path, preview_fast=True)
            surf.status.setText(f"embed failed: {exc}")
        return app.exec()

    win = FastPreviewWindow(path)
    win.show()
    return app.exec()


def wants_preview(argv: list[str] | None = None) -> bool:
    argv = list(sys.argv if argv is None else argv)
    return any(a in ("--preview", "-p", "--explorer-preview") for a in argv[1:])
