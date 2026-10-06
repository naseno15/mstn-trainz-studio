"""Resolve Trainz texture references to loadable images."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PIL import Image


IMAGE_EXTS = (".png", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


def _stem_candidates(ref: str) -> List[str]:
    base = os.path.basename(ref.replace("\\", "/"))
    stem, _ext = os.path.splitext(base)
    # balckin_albedo.texture -> balckin_albedo
    names = [stem, base]
    if stem.endswith(".texture"):
        names.append(stem[: -len(".texture")])
    # common Trainz patterns: foo.texture.txt points at foo.tga
    out: List[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def _search_dirs(mesh_dir: str) -> List[str]:
    dirs = [mesh_dir]
    parent = os.path.dirname(mesh_dir)
    if parent and parent not in dirs:
        dirs.append(parent)
    return dirs


def resolve_texture_path(mesh_dir: str, ref: str) -> Optional[str]:
    if not ref or ref.startswith("$"):
        return None
    ref_norm = ref.replace("\\", "/").lstrip("./")
    direct = os.path.join(mesh_dir, ref_norm)
    if os.path.isfile(direct) and not direct.lower().endswith(".texture"):
        return direct

    stems = _stem_candidates(ref_norm)
    for folder in _search_dirs(mesh_dir):
        for stem in stems:
            for ext in IMAGE_EXTS:
                candidate = os.path.join(folder, stem + ext)
                if os.path.isfile(candidate):
                    return candidate
            # texture.txt sidecar naming: name.texture.txt
            txt = os.path.join(folder, stem + ".texture.txt")
            if os.path.isfile(txt):
                pointed = _parse_texture_txt(txt, folder)
                if pointed:
                    return pointed
            # Sometimes the compiled .texture exists next to source image with same stem
            for ext in IMAGE_EXTS:
                # strip trailing _albedo etc already in stem
                candidate = os.path.join(folder, stem + ext)
                if os.path.isfile(candidate):
                    return candidate
    return None


def _parse_texture_txt(path: str, folder: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        # Primary=foo.tga / Source=foo.tga / Alpha=...
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip().lower()
            val = val.strip().strip('"')
            if key in {"primary", "source", "image", "diffuse", "albedo"} and val:
                candidate = val if os.path.isabs(val) else os.path.join(folder, val)
                if os.path.isfile(candidate):
                    return candidate
        elif any(line.lower().endswith(ext) for ext in IMAGE_EXTS):
            candidate = os.path.join(folder, line)
            if os.path.isfile(candidate):
                return candidate
    return None


def load_rgba(path: str) -> Tuple[int, int, bytes]:
    img = Image.open(path)
    img = img.convert("RGBA")
    return img.width, img.height, img.tobytes()


def make_placeholder(rgb: Tuple[int, int, int] = (180, 180, 185)) -> Tuple[int, int, bytes]:
    w = h = 4
    r, g, b = rgb
    pixel = bytes((r, g, b, 255))
    return w, h, pixel * (w * h)
