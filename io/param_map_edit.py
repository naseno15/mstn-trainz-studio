"""Trainz m.pbrmetal Parameter map edits (RGBA = Emissive, Roughness, AO, Metallic).

Working buffer is always RGBA uint8 (same as ``tex_map_edit``). Save via
``save_trainz_image`` — overwrite only when the UI calls save.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .tex_map_edit import load_rgba, save_trainz_image

IMAGE_EXTS = {".png", ".tga", ".tif", ".tiff", ".bmp", ".webp", ".jpg", ".jpeg"}

# Trainz parameter channel order (linear space)
CHANNELS = (
    ("R", "Emissive", 0),
    ("G", "Roughness", 1),
    ("B", "AO", 2),
    ("A", "Metallic", 3),
)

CHANNEL_KEYS = ("R", "G", "B", "A")
CHANNEL_INDEX = {"R": 0, "G": 1, "B": 2, "A": 3}


def selected_mask(selected: set[str]) -> tuple[bool, bool, bool, bool]:
    return tuple(k in selected for k in CHANNEL_KEYS)  # type: ignore[return-value]


def apply_fill(rgba: np.ndarray, selected: set[str], value: int) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    v = int(np.clip(value, 0, 255))
    for key in selected:
        out[..., CHANNEL_INDEX[key]] = v
    return out


def apply_offset(rgba: np.ndarray, selected: set[str], delta: int) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    for key in selected:
        i = CHANNEL_INDEX[key]
        out[..., i] = np.clip(out[..., i].astype(np.int16) + int(delta), 0, 255).astype(np.uint8)
    return out


def apply_scale(rgba: np.ndarray, selected: set[str], factor: float) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    for key in selected:
        i = CHANNEL_INDEX[key]
        out[..., i] = np.clip(out[..., i].astype(np.float32) * float(factor), 0, 255).astype(
            np.uint8
        )
    return out


def apply_brightness_contrast(
    rgba: np.ndarray,
    selected: set[str],
    brightness: int,
    contrast: float = 1.0,
) -> np.ndarray:
    """brightness −255…255 · contrast 0…3 around mid-gray 127.5."""
    out = np.asarray(rgba, dtype=np.uint8).copy()
    b = float(brightness)
    c = float(contrast)
    for key in selected:
        i = CHANNEL_INDEX[key]
        x = out[..., i].astype(np.float32)
        out[..., i] = np.clip((x - 127.5) * c + 127.5 + b, 0, 255).astype(np.uint8)
    return out


def apply_retarget_mean(rgba: np.ndarray, selected: set[str], target: int) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    t = float(np.clip(target, 0, 255))
    for key in selected:
        i = CHANNEL_INDEX[key]
        x = out[..., i].astype(np.float32)
        out[..., i] = np.clip(x + (t - float(x.mean())), 0, 255).astype(np.uint8)
    return out


def apply_invert(rgba: np.ndarray, selected: set[str]) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    for key in selected:
        i = CHANNEL_INDEX[key]
        out[..., i] = 255 - out[..., i]
    return out


def _as_rgba(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return np.dstack([img, img, img, np.full(img.shape, 255, np.uint8)])
    if img.shape[2] == 3:
        a = np.full(img.shape[:2], 255, dtype=np.uint8)
        return np.dstack([img[..., 0], img[..., 1], img[..., 2], a])
    return img.astype(np.uint8, copy=False)


def _resize_rgba(src: np.ndarray, size_hw: tuple[int, int]) -> np.ndarray:
    h, w = size_hw
    if src.shape[0] == h and src.shape[1] == w:
        return src
    return cv2.resize(src, (w, h), interpolation=cv2.INTER_LINEAR)


def extract_overlay_maps(src: np.ndarray, source_channel: str) -> dict[str, np.ndarray]:
    rgba = _as_rgba(src)
    planes = {k: rgba[..., CHANNEL_INDEX[k]] for k in CHANNEL_KEYS}
    if source_channel == "match":
        return {k: planes[k].astype(np.uint8) for k in CHANNEL_KEYS}
    if source_channel in CHANNEL_KEYS:
        m = planes[source_channel].astype(np.uint8)
        return {k: m for k in CHANNEL_KEYS}
    gray = (
        0.299 * rgba[..., 0].astype(np.float32)
        + 0.587 * rgba[..., 1].astype(np.float32)
        + 0.114 * rgba[..., 2].astype(np.float32)
    ).astype(np.uint8)
    return {k: gray for k in CHANNEL_KEYS}


def overlay_mask(src: np.ndarray, mode: str, black_threshold: int = 0) -> np.ndarray:
    rgba = _as_rgba(src)
    a = rgba[..., 3].astype(np.float32) / 255.0
    if mode == "replace":
        return np.ones(a.shape, dtype=np.float32)
    gray = (
        0.299 * rgba[..., 0].astype(np.float32)
        + 0.587 * rgba[..., 1].astype(np.float32)
        + 0.114 * rgba[..., 2].astype(np.float32)
    )
    if mode == "stamp":
        solid = (rgba[..., 3] > 0) & (gray > int(black_threshold))
        return solid.astype(np.float32) * a
    return a


def apply_overlay(
    rgba: np.ndarray,
    selected: set[str],
    src: np.ndarray,
    mode: str = "blend",
    opacity: float = 1.0,
    source_channel: str = "gray",
    black_threshold: int = 0,
) -> np.ndarray:
    if not selected:
        return np.asarray(rgba, dtype=np.uint8).copy()

    src_rgba = _resize_rgba(_as_rgba(src), rgba.shape[:2])
    maps = extract_overlay_maps(src_rgba, source_channel)
    mask = overlay_mask(src_rgba, mode, black_threshold=black_threshold)
    strength = np.clip(mask * float(opacity), 0.0, 1.0)

    out = np.asarray(rgba, dtype=np.uint8).copy()
    for key in selected:
        i = CHANNEL_INDEX[key]
        base = out[..., i].astype(np.float32)
        top = maps[key].astype(np.float32)
        out[..., i] = np.clip(base * (1.0 - strength) + top * strength, 0, 255).astype(np.uint8)
    return out


def channel_stats(rgba: np.ndarray) -> dict[str, tuple[int, int, float]]:
    arr = np.asarray(rgba, dtype=np.uint8)
    return {
        k: (
            int(arr[..., CHANNEL_INDEX[k]].min()),
            int(arr[..., CHANNEL_INDEX[k]].max()),
            float(arr[..., CHANNEL_INDEX[k]].mean()),
        )
        for k in CHANNEL_KEYS
    }


def view_param_channels(
    rgba: np.ndarray,
    *,
    r: bool = True,
    g: bool = True,
    b: bool = True,
    a: bool = True,
    solo: str | None = None,
) -> np.ndarray:
    """Preview composite or solo channel as grayscale RGB."""
    src = np.asarray(rgba, dtype=np.uint8)
    if solo in CHANNEL_KEYS:
        gray = src[..., CHANNEL_INDEX[solo]]
        out = np.empty_like(src)
        out[..., 0] = gray
        out[..., 1] = gray
        out[..., 2] = gray
        out[..., 3] = 255
        return out
    out = src.copy()
    if not r:
        out[..., 0] = 0
    if not g:
        out[..., 1] = 0
    if not b:
        out[..., 2] = 0
    if not a:
        out[..., 3] = 255
    return out


def _brush_mask(radius: int, hardness: float) -> np.ndarray:
    r = max(int(radius), 1)
    yy, xx = np.ogrid[-r : r + 1, -r : r + 1]
    dist = np.sqrt(xx * xx + yy * yy).astype(np.float32)
    hard = float(np.clip(hardness, 0.0, 1.0))
    inner = r * hard
    mask = np.zeros_like(dist)
    solid = dist <= inner
    mask[solid] = 1.0
    ring = (dist > inner) & (dist <= r)
    if np.any(ring):
        mask[ring] = 1.0 - (dist[ring] - inner) / max(r - inner, 1e-6)
    return np.clip(mask, 0.0, 1.0)


def paint_dab(
    rgba: np.ndarray,
    selected: set[str],
    x: float,
    y: float,
    radius: int,
    value: int,
    hardness: float = 0.6,
    opacity: float = 1.0,
) -> None:
    """Paint one dab in-place onto selected RGBA channels."""
    if not selected or rgba is None:
        return
    h, w = rgba.shape[:2]
    r = max(int(radius), 1)
    cx, cy = int(round(x)), int(round(y))
    kernel = _brush_mask(r, hardness) * float(np.clip(opacity, 0.0, 1.0))
    x0, y0 = cx - r, cy - r
    x1, y1 = cx + r + 1, cy + r + 1
    kx0 = ky0 = 0
    kx1, ky1 = kernel.shape[1], kernel.shape[0]
    if x0 < 0:
        kx0 = -x0
        x0 = 0
    if y0 < 0:
        ky0 = -y0
        y0 = 0
    if x1 > w:
        kx1 -= x1 - w
        x1 = w
    if y1 > h:
        ky1 -= y1 - h
        y1 = h
    if x0 >= x1 or y0 >= y1:
        return

    strength = kernel[ky0:ky1, kx0:kx1]
    v = float(np.clip(value, 0, 255))
    for key in selected:
        i = CHANNEL_INDEX[key]
        base = rgba[y0:y1, x0:x1, i].astype(np.float32)
        rgba[y0:y1, x0:x1, i] = np.clip(
            base * (1.0 - strength) + v * strength, 0, 255
        ).astype(np.uint8)


def paint_line(
    rgba: np.ndarray,
    selected: set[str],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: int,
    value: int,
    hardness: float = 0.6,
    opacity: float = 1.0,
) -> None:
    dx = x1 - x0
    dy = y1 - y0
    dist = float(np.hypot(dx, dy))
    step = max(radius * 0.35, 1.0)
    n = max(int(dist / step), 1)
    for i in range(n + 1):
        t = i / n
        paint_dab(
            rgba,
            selected,
            x0 + dx * t,
            y0 + dy * t,
            radius,
            value,
            hardness=hardness,
            opacity=opacity,
        )


def open_parameter(path: str | Path):
    """Convenience — load via shared Trainz image loader."""
    return load_rgba(Path(path))


def save_parameter(path: str | Path, rgba: np.ndarray, *, bak: bool = True) -> Path:
    return save_trainz_image(Path(path), rgba, bak=bak)
