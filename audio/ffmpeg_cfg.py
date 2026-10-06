"""Optional ffmpeg path override (Sounds import)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SETTINGS = Path.home() / ".cache" / "trainz_studio" / "settings.json"


def _load() -> dict:
    if not SETTINGS.is_file():
        return {}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_ffmpeg_path() -> str | None:
    """Configured path, else PATH lookup."""
    cfg = _load().get("ffmpeg_path")
    if cfg:
        p = Path(cfg)
        if p.is_file():
            return str(p)
    return shutil.which("ffmpeg")


def set_ffmpeg_path(path: str | None) -> None:
    data = _load()
    if path:
        data["ffmpeg_path"] = str(path)
    else:
        data.pop("ffmpeg_path", None)
    _save(data)


def ffmpeg_status() -> str:
    ff = get_ffmpeg_path()
    if ff:
        return f"ffmpeg: {ff}"
    return "ffmpeg: not found (set path to import mp3/video)"
