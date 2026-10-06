"""Classify dropped / CLI paths into mesh vs audio vs video vs project."""
from __future__ import annotations

from pathlib import Path

MESH_EXTS = {".fbx", ".im", ".trainzmesh", ".obj"}
PROJECT_EXTS = {".mtzs"}
AUDIO_EXTS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".oga",
    ".aiff",
    ".aif",
    ".m4a",
    ".aac",
    ".wma",
    ".opus",
}
VIDEO_EXTS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".wmv",
    ".m4v",
    ".mpg",
    ".mpeg",
}


def classify_path(path: Path) -> str:
    """Return 'mesh' | 'audio' | 'video' | 'project' | 'other'."""
    suf = path.suffix.lower()
    name = path.name.lower()
    if suf in MESH_EXTS:
        return "mesh"
    if suf in PROJECT_EXTS:
        return "project"
    if suf in AUDIO_EXTS:
        return "audio"
    if suf in VIDEO_EXTS:
        return "video"
    if name.endswith(".texture.txt") or suf == ".texture":
        return "other"
    if suf == ".kin":
        return "other"
    return "other"


def partition_paths(paths: list[Path]) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {
        "mesh": [],
        "audio": [],
        "video": [],
        "project": [],
        "other": [],
    }
    for p in paths:
        out[classify_path(p)].append(p)
    return out
