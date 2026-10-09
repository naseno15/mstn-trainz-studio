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
        return view_channel_color(src, solo)
    return view_param_composite(src, r=r, g=g, b=b, a=a)


def view_param_composite(
    rgba: np.ndarray,
    *,
    r: bool = True,
    g: bool = True,
    b: bool = True,
    a: bool = True,
) -> np.ndarray:
    """Opaque RGB of the ticked channels. Metallic screens on so A stays visible."""
    src = np.asarray(rgba, dtype=np.uint8)
    rgb = np.zeros(src.shape[:2] + (3,), dtype=np.float32)
    if r:
        rgb[..., 0] = src[..., 0]
    if g:
        rgb[..., 1] = src[..., 1]
    if b:
        rgb[..., 2] = src[..., 2]
    if a:
        # Half-strength screen — full metal would wipe the color to white.
        metal = src[..., 3].astype(np.float32) / 255.0 * 0.55
        rgb += (255.0 - rgb) * metal[..., None]
    out = np.empty_like(src)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = 255
    return out


def luminance(src: np.ndarray) -> np.ndarray:
    """One gray plane. A color image uses Rec.601. A gray image stays as-is."""
    rgba = _as_rgba(src)
    r = rgba[..., 0].astype(np.float32)
    g = rgba[..., 1].astype(np.float32)
    b = rgba[..., 2].astype(np.float32)
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)


def view_plane(plane: np.ndarray, key: str, *, gray: bool) -> np.ndarray:
    """Preview one channel. ``gray`` forces black-and-white for every channel."""
    src = np.asarray(plane, dtype=np.uint8)
    out = np.zeros(src.shape + (4,), dtype=np.uint8)
    if gray or key == "A":
        out[..., 0] = src
        out[..., 1] = src
        out[..., 2] = src
    elif key == "R":
        out[..., 0] = src
    elif key == "G":
        out[..., 1] = src
    else:
        out[..., 2] = src
    out[..., 3] = 255
    return out


def downscale_rgba(rgba: np.ndarray, max_edge: int) -> np.ndarray:
    """Shrink so the long side is at most ``max_edge``. Preview only."""
    src = np.asarray(rgba, dtype=np.uint8)
    height, width = src.shape[:2]
    long_side = max(height, width, 1)
    if long_side <= max_edge:
        return src
    scale = max_edge / long_side
    return cv2.resize(
        src,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def view_channel_color(rgba: np.ndarray, key: str) -> np.ndarray:
    """One channel in its own color. A is white."""
    src = np.asarray(rgba, dtype=np.uint8)
    gray = src[..., CHANNEL_INDEX[key]]
    out = np.zeros_like(src)
    slots = {"R": (0,), "G": (1,), "B": (2,), "A": (0, 1, 2)}[key]
    for slot in slots:
        out[..., slot] = gray
    out[..., 3] = 255
    return out


def magic_mask(
    rgba: np.ndarray,
    x: float,
    y: float,
    tol: int = 24,
    contiguous: bool = True,
) -> np.ndarray:
    """Pixels whose RGBA is within ``tol`` of the seed. Contiguous = one island."""
    src = np.asarray(rgba, dtype=np.uint8)
    height, width = src.shape[:2]
    xi = int(np.clip(round(x), 0, width - 1))
    yi = int(np.clip(round(y), 0, height - 1))
    seed = src[yi, xi].astype(np.int16)
    near = np.max(np.abs(src.astype(np.int16) - seed), axis=2) <= int(tol)
    if not contiguous:
        return near
    _count, labels = cv2.connectedComponents(near.astype(np.uint8), connectivity=4)
    island = int(labels[yi, xi])
    if island == 0:
        picked = np.zeros((height, width), dtype=bool)
        picked[yi, xi] = True
        return picked
    return labels == island


def apply_stamp_at(
    rgba: np.ndarray,
    selected: set[str],
    src: np.ndarray,
    x: float,
    y: float,
    mode: str = "blend",
    opacity: float = 1.0,
    source_channel: str = "gray",
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Paste ``src`` with its top-left at pixel (x, y)."""
    out = np.asarray(rgba, dtype=np.uint8).copy()
    if not selected:
        return out
    src_rgba = _as_rgba(src)
    sh, sw = src_rgba.shape[:2]
    height, width = out.shape[:2]
    x0, y0 = int(round(x)), int(round(y))
    x1, y1 = x0 + sw, y0 + sh
    sx0 = sy0 = 0
    if x0 < 0:
        sx0 = -x0
        x0 = 0
    if y0 < 0:
        sy0 = -y0
        y0 = 0
    if x1 > width:
        x1 = width
    if y1 > height:
        y1 = height
    if x0 >= x1 or y0 >= y1:
        return out
    crop = src_rgba[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
    stamped = apply_overlay(
        out[y0:y1, x0:x1],
        selected,
        crop,
        mode=mode,
        opacity=opacity,
        source_channel=source_channel,
    )
    if mask is not None:
        keep = mask[y0:y1, x0:x1].astype(np.float32)[..., None]
        orig = out[y0:y1, x0:x1].astype(np.float32)
        stamped = np.clip(
            orig * (1.0 - keep) + stamped.astype(np.float32) * keep, 0, 255
        ).astype(np.uint8)
    out[y0:y1, x0:x1] = stamped
    return out


def _self_check() -> None:
    img = np.zeros((4, 4, 4), np.uint8)
    img[..., 0] = 200
    img[..., 3] = 255
    view = view_param_composite(img, r=True, g=False, b=False, a=True)
    assert int(view[0, 0, 0]) > 200
    assert int(view[0, 0, 1]) > 100
    img[1, 1] = (10, 10, 10, 10)
    img[1, 2] = (12, 12, 12, 12)
    img[2, 2] = (200, 0, 0, 0)
    picked = magic_mask(img, 1, 1, tol=8, contiguous=True)
    assert bool(picked[1, 2]) and not bool(picked[2, 2])
    gray = luminance(np.array([[[255, 0, 0, 255]]], np.uint8))
    assert int(gray[0, 0]) == 76
    small = downscale_rgba(np.zeros((80, 40, 4), np.uint8), 20)
    assert max(small.shape[:2]) <= 20
    stamped = apply_stamp_at(img, {"R"}, np.full((2, 2, 4), 80, np.uint8), 1, 1)
    assert int(stamped[1, 1, 0]) != int(img[1, 1, 0])


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
    mask: np.ndarray | None = None,
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
    if mask is not None:
        strength = strength * mask[y0:y1, x0:x1].astype(np.float32)
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
    mask: np.ndarray | None = None,
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
            mask=mask,
        )


def open_parameter(path: str | Path):
    """Convenience — load via shared Trainz image loader."""
    return load_rgba(Path(path))


def save_parameter(path: str | Path, rgba: np.ndarray, *, bak: bool = True) -> Path:
    return save_trainz_image(Path(path), rgba, bak=bak)
