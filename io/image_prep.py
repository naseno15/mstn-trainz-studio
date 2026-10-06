"""Batch image prep for Trainz textures — resize with map-aware handling.

Ported logic from BatchImageResizer ``image_processor.py`` (Pillow + numpy).
Default output: ``<parent>/_prep/<name>`` (non-destructive).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from .texture import material_family

MapMode = Literal["auto", "albedo", "normal", "parameter"]
ResizeMode = Literal["percentage", "exact", "max", "pot"]
OutFormat = Literal["SAME", "PNG", "TGA", "JPG"]

_PREP_DIR = "_prep"

_FILTERS: dict[str, Image.Resampling] = {
    "lanczos": Image.Resampling.LANCZOS,
    "bicubic": Image.Resampling.BICUBIC,
    "bilinear": Image.Resampling.BILINEAR,
    "box": Image.Resampling.BOX,
    "nearest": Image.Resampling.NEAREST,
}


def detect_map_mode(path: str | Path) -> MapMode:
    """Infer albedo / normal / parameter from filename (material_family)."""
    _, role = material_family(Path(path).name)
    if role in ("normal", "parameter", "albedo"):
        return role  # type: ignore[return-value]
    return "albedo"


def prep_out_path(src: Path, *, out_format: OutFormat = "SAME") -> Path:
    """``parent/_prep/stem.ext`` — creates parent when writing."""
    ext = src.suffix if out_format == "SAME" else f".{out_format.lower()}"
    if out_format == "JPG":
        ext = ".jpg"
    return src.parent / _PREP_DIR / f"{src.stem}{ext}"


def calculate_target_size(
    orig_w: int,
    orig_h: int,
    resize_mode: ResizeMode,
    *,
    percent: float = 50.0,
    target_w: int = 1024,
    target_h: int = 1024,
    max_dim: int = 2048,
    pot_down: bool = True,
) -> tuple[int, int]:
    if resize_mode == "percentage":
        f = percent / 100.0
        return max(1, int(round(orig_w * f))), max(1, int(round(orig_h * f)))
    if resize_mode == "exact":
        return max(1, target_w), max(1, target_h)
    if resize_mode == "max":
        if orig_w <= max_dim and orig_h <= max_dim:
            return orig_w, orig_h
        aspect = orig_w / max(orig_h, 1)
        if orig_w >= orig_h:
            return max_dim, max(1, int(round(max_dim / aspect)))
        return max(1, int(round(max_dim * aspect))), max_dim
    # pot
    def _po2(n: int) -> int:
        if n <= 1:
            return 1
        v = 1
        while v < n:
            v *= 2
        if v == n:
            return v
        return v // 2 if pot_down else v

    return _po2(orig_w), _po2(orig_h)


def resize_normal_map(
    img: Image.Image,
    target: tuple[int, int],
    resample: Image.Resampling,
    *,
    flip_green: bool = False,
) -> Image.Image:
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    alpha = None
    if has_alpha:
        rgba = img.convert("RGBA")
        alpha = rgba.split()[-1].resize(target, resample)
        rgb = rgba.convert("RGB")
    else:
        rgb = img.convert("RGB")
    res = rgb.resize(target, resample)
    arr = np.asarray(res, dtype=np.float32)
    max_val = 65535.0 if arr.max() > 255.0 else 255.0
    normals = (arr / max_val) * 2.0 - 1.0
    if flip_green:
        normals[..., 1] = -normals[..., 1]
    length = np.sqrt(np.sum(normals**2, axis=-1, keepdims=True))
    length = np.maximum(length, 1e-8)
    packed = np.clip((normals / length * 0.5 + 0.5) * max_val, 0, max_val)
    if max_val == 65535.0:
        out = Image.fromarray(packed.astype(np.uint16), mode="RGB")
    else:
        out = Image.fromarray(packed.astype(np.uint8), mode="RGB")
    if alpha is not None:
        out.putalpha(alpha)
    return out


def resize_parameter_map(
    img: Image.Image,
    target: tuple[int, int],
    resample: Image.Resampling,
) -> Image.Image:
    if img.mode in ("L", "LA", "RGB", "RGBA", "I;16", "F"):
        return img.resize(target, resample)
    if "transparency" in img.info or img.mode == "P":
        return img.convert("RGBA").resize(target, resample)
    return img.convert("RGB").resize(target, resample)


def process_image(
    src: Path,
    *,
    mode: MapMode = "auto",
    resize_mode: ResizeMode = "max",
    percent: float = 50.0,
    target_w: int = 1024,
    target_h: int = 1024,
    max_dim: int = 2048,
    pot_down: bool = True,
    filter_name: str = "lanczos",
    out_format: OutFormat = "SAME",
    quality: int = 95,
    flip_green: bool = False,
    out_path: Path | None = None,
) -> tuple[bool, Path, str]:
    """Resize one image into ``_prep/`` (or ``out_path``). Returns (ok, path, msg)."""
    src = Path(src)
    if not src.is_file():
        return False, src, "not found"
    try:
        with Image.open(src) as img:
            ow, oh = img.size
            icc = img.info.get("icc_profile")
            tw, th = calculate_target_size(
                ow,
                oh,
                resize_mode,
                percent=percent,
                target_w=target_w,
                target_h=target_h,
                max_dim=max_dim,
                pot_down=pot_down,
            )
            resample = _FILTERS.get(filter_name, Image.Resampling.LANCZOS)
            eff: MapMode = detect_map_mode(src) if mode == "auto" else mode
            if eff == "normal":
                out_img = resize_normal_map(img, (tw, th), resample, flip_green=flip_green)
            elif eff == "parameter":
                out_img = resize_parameter_map(img, (tw, th), resample)
            else:
                out_img = img.resize((tw, th), resample)

            dest = Path(out_path) if out_path is not None else prep_out_path(src, out_format=out_format)
            dest.parent.mkdir(parents=True, exist_ok=True)
            ext = dest.suffix.lower()
            kwargs: dict = {}
            save_img = out_img
            if ext in (".jpg", ".jpeg"):
                if save_img.mode in ("RGBA", "LA", "P"):
                    save_img = save_img.convert("RGB")
                kwargs["quality"] = quality
            elif ext == ".png":
                kwargs["compress_level"] = 3
            elif ext == ".tga" and save_img.mode == "P":
                save_img = save_img.convert("RGBA")
            if icc and ext not in (".tga", ".hdr"):
                kwargs["icc_profile"] = icc
            save_img.save(dest, **kwargs)
        return True, dest, f"{ow}x{oh} → {tw}x{th} [{eff}]"
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return False, src, str(exc)
