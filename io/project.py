"""Trainz Studio project (.mtzs) + crash self-backup recovery."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

CACHE = Path.home() / ".cache" / "trainz_studio"
CRASH_DIR = CACHE / "crash_recover"
CRASH_META = CRASH_DIR / "session.json"
CRASH_BUF = CRASH_DIR / "buffer.trainzmesh"
CRASH_MARKER = CRASH_DIR / "dirty.flag"

PROJECT_VERSION = 1
PROJECT_SUFFIX = ".mtzs"


@dataclass
class ProjectState:
    mesh_paths: list[str] = field(default_factory=list)
    studio_page: str = "editor"
    editor_tab: str = "attachments"  # attachments | meshes
    sel_att: int = -1
    sel_mesh: int = -1
    theme: str = "dark"
    tzmf_dirty: bool = False
    buffer: bytes | None = None  # unsaved .trainzmesh edits
    project_path: str | None = None
    saved_at: float = 0.0

    def to_meta(self) -> dict:
        return {
            "version": PROJECT_VERSION,
            "mesh_paths": list(self.mesh_paths),
            "studio_page": self.studio_page,
            "editor_tab": self.editor_tab,
            "sel_att": int(self.sel_att),
            "sel_mesh": int(self.sel_mesh),
            "theme": self.theme,
            "tzmf_dirty": bool(self.tzmf_dirty),
            "has_buffer": self.buffer is not None and len(self.buffer) > 0,
            "saved_at": float(self.saved_at or time.time()),
        }

    @classmethod
    def from_meta(cls, meta: dict, *, buffer: bytes | None = None) -> ProjectState:
        return cls(
            mesh_paths=[str(p) for p in meta.get("mesh_paths") or []],
            studio_page=str(meta.get("studio_page") or "editor"),
            editor_tab=str(meta.get("editor_tab") or "attachments"),
            sel_att=int(meta.get("sel_att", -1)),
            sel_mesh=int(meta.get("sel_mesh", -1)),
            theme=str(meta.get("theme") or "dark"),
            tzmf_dirty=bool(meta.get("tzmf_dirty")),
            buffer=buffer,
            saved_at=float(meta.get("saved_at") or 0.0),
        )


def buffer_sidecar(project_path: Path) -> Path:
    return project_path.with_suffix(project_path.suffix + ".buf")


def save_project(path: Path, state: ProjectState) -> Path:
    """Write ``*.mtzs`` JSON + optional ``*.mtzs.buf`` dirty buffer."""
    path = Path(path)
    if path.suffix.lower() != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.saved_at = time.time()
    state.project_path = str(path)
    meta = state.to_meta()
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    side = buffer_sidecar(path)
    if state.buffer is not None and len(state.buffer) > 0 and state.tzmf_dirty:
        side.write_bytes(state.buffer)
    elif side.is_file():
        side.unlink(missing_ok=True)
    return path


def load_project(path: Path) -> ProjectState:
    path = Path(path)
    meta = json.loads(path.read_text(encoding="utf-8"))
    if int(meta.get("version", 0)) > PROJECT_VERSION:
        raise ValueError(f"Unsupported project version {meta.get('version')}")
    buf: bytes | None = None
    side = buffer_sidecar(path)
    if meta.get("has_buffer") and side.is_file():
        buf = side.read_bytes()
    state = ProjectState.from_meta(meta, buffer=buf)
    state.project_path = str(path)
    return state


def write_crash_backup(state: ProjectState) -> None:
    """Atomic-ish self-backup for sudden quit / crash recovery."""
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    state.saved_at = time.time()
    meta = state.to_meta()
    tmp = CRASH_META.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CRASH_META)
    if state.buffer is not None and len(state.buffer) > 0 and state.tzmf_dirty:
        btmp = CRASH_BUF.with_suffix(".tmp")
        btmp.write_bytes(state.buffer)
        btmp.replace(CRASH_BUF)
        CRASH_MARKER.write_text("1\n", encoding="utf-8")
    else:
        if CRASH_BUF.is_file():
            CRASH_BUF.unlink(missing_ok=True)
        if CRASH_MARKER.is_file():
            CRASH_MARKER.unlink(missing_ok=True)


def has_crash_recovery() -> bool:
    return CRASH_MARKER.is_file() and CRASH_META.is_file()


def load_crash_backup() -> ProjectState | None:
    if not CRASH_META.is_file():
        return None
    try:
        meta = json.loads(CRASH_META.read_text(encoding="utf-8"))
    except Exception:
        return None
    buf: bytes | None = None
    if CRASH_BUF.is_file():
        try:
            buf = CRASH_BUF.read_bytes()
        except OSError:
            buf = None
    state = ProjectState.from_meta(meta, buffer=buf)
    return state


def clear_crash_backup() -> None:
    if CRASH_DIR.is_dir():
        shutil.rmtree(CRASH_DIR, ignore_errors=True)
