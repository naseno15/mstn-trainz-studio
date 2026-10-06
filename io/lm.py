"""Trainz *.lm.txt — LOD mesh table (ASCII). Wiki + in-tree samples."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_MESH_RE = re.compile(
    r'mesh\s*\(\s*"([^"]+)"\s*\)\s*\{\s*name\s*=\s*"([^"]+)"\s*;?\s*\}',
    re.IGNORECASE | re.DOTALL,
)
_KV_RE = re.compile(
    r"^(offset|calcPoint|calcpoint|multiplier|animationCutOff|renderCutOff|attachmentCutOff)"
    r"\s*=\s*([^;]+);",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class LmMesh:
    width: float  # screen-width fraction; ascending
    name: str  # mesh filename (.im / .trainzmesh)


@dataclass
class LmFile:
    version: str = "1.0"
    offset: float = 0.01
    calc_point: str = "center"  # center | near | far
    multiplier: float = 1.0
    animation_cutoff: float = 0.0
    render_cutoff: float = 0.0
    attachment_cutoff: float = 0.06
    meshes: list[LmMesh] = field(default_factory=list)

    def sorted_meshes(self) -> list[LmMesh]:
        return sorted(self.meshes, key=lambda m: m.width)


def parse_lm_txt(text: str) -> LmFile:
    lm = LmFile()
    for m in re.finditer(r"^version\s+(\S+)", text, re.IGNORECASE | re.MULTILINE):
        lm.version = m.group(1).strip()
        break
    for m in _KV_RE.finditer(text):
        key = m.group(1).lower()
        raw = m.group(2).strip().rstrip(";")
        if key == "calcpoint":
            lm.calc_point = raw
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if key == "offset":
            lm.offset = val
        elif key == "multiplier":
            lm.multiplier = val
        elif key == "animationcutoff":
            lm.animation_cutoff = val
        elif key == "rendercutoff":
            lm.render_cutoff = val
        elif key == "attachmentcutoff":
            lm.attachment_cutoff = val
    lm.meshes = [
        LmMesh(width=float(w), name=name.strip())
        for w, name in _MESH_RE.findall(text)
    ]
    return lm


def format_lm_txt(lm: LmFile) -> str:
    """Write wiki-style *.lm.txt (meshes ascending by width)."""
    meshes = lm.sorted_meshes()
    if not meshes:
        raise ValueError("LM needs at least one mesh(...) entry")
    lines = [
        f"version {lm.version}",
        f"offset = {lm.offset:g};",
        f"calcPoint = {lm.calc_point};",
        f"multiplier = {lm.multiplier:g};",
        f"animationCutOff = {lm.animation_cutoff:g};",
        f"renderCutOff = {lm.render_cutoff:g};",
        f"attachmentCutOff = {lm.attachment_cutoff:g};",
        "",
    ]
    for mesh in meshes:
        lines.append(f'mesh("{mesh.width:g}")')
        lines.append("{")
        lines.append(f'  name="{mesh.name}";')
        lines.append("}")
    return "\n".join(lines) + "\n"


def write_lm_txt(path: Path, lm: LmFile) -> Path:
    path = Path(path)
    if path.suffix.lower() == ".lm":
        path = path.with_suffix(".lm.txt")
    elif not path.name.lower().endswith(".lm.txt"):
        path = path.with_name(path.name + ".lm.txt") if path.suffix else path.with_suffix(".lm.txt")
    path.write_text(format_lm_txt(lm), encoding="utf-8", newline="\n")
    return path


def read_lm_txt(path: Path) -> LmFile:
    return parse_lm_txt(Path(path).read_text(encoding="utf-8", errors="replace"))
