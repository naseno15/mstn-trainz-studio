"""Albedo / Normal / Parameter map edit — channel view + Trainz-safe save.

Working buffer is always RGBA uint8. Display can solo/mute R·G·B·A like PS.
Save writes the image only (``.texture.txt`` stays separate); first overwrite
gets a sibling ``.bak`` once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MapRole = str  # "albedo" | "normal" | "parameter" | ""

_UNDO_CAP = 24


def load_rgba(path: Path) -> np.ndarray:
    """Load any Trainz-common image → HxWx4 uint8."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"), dtype=np.uint8).copy()


def rgba_to_qimage_bytes(rgba: np.ndarray) -> tuple[bytes, int, int]:
    """Contiguous RGBA bytes + size for ``QImage.Format_RGBA8888``."""
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("rgba must be HxWx4")
    h, w = int(arr.shape[0]), int(arr.shape[1])
    return arr.tobytes(), w, h


def view_channels(
    rgba: np.ndarray,
    *,
    r: bool = True,
    g: bool = True,
    b: bool = True,
    a: bool = True,
) -> np.ndarray:
    """Channel mute / solo for preview (does not mutate ``rgba``).

    - One of R/G/B alone → grayscale of that channel (A preserved if on).
    - Several of R/G/B → muted channels forced to 0.
    - A off → display opaque; A alone (no RGB) → grayscale of alpha.
    """
    src = np.asarray(rgba, dtype=np.uint8)
    out = src.copy()
    rgb_on = (r, g, b)
    n_rgb = sum(1 for x in rgb_on if x)

    if n_rgb == 0 and a:
        gray = src[..., 3]
        out[..., 0] = gray
        out[..., 1] = gray
        out[..., 2] = gray
        out[..., 3] = 255
        return out

    if n_rgb == 1:
        idx = 0 if r else (1 if g else 2)
        gray = src[..., idx]
        out[..., 0] = gray
        out[..., 1] = gray
        out[..., 2] = gray
    else:
        if not r:
            out[..., 0] = 0
        if not g:
            out[..., 1] = 0
        if not b:
            out[..., 2] = 0

    if not a:
        out[..., 3] = 255
    return out


def adjust_brightness_contrast(
    rgba: np.ndarray,
    *,
    brightness: float = 0.0,
    contrast: float = 0.0,
    channels: tuple[bool, bool, bool, bool] = (True, True, True, False),
) -> np.ndarray:
    """``brightness`` / ``contrast`` in −100…100; only flagged channels."""
    out = np.asarray(rgba, dtype=np.float32).copy()
    c = max(-100.0, min(100.0, float(contrast)))
    b = max(-100.0, min(100.0, float(brightness)))
    factor = (259.0 * (c + 255.0)) / (255.0 * (259.0 - c)) if c != 0 else 1.0
    for i, on in enumerate(channels):
        if not on:
            continue
        ch = out[..., i]
        if c != 0:
            ch = factor * (ch - 128.0) + 128.0
        if b != 0:
            ch = ch + (b * 255.0 / 100.0)
        out[..., i] = ch
    return np.clip(out, 0, 255).astype(np.uint8)


def invert_channels(
    rgba: np.ndarray,
    channels: tuple[bool, bool, bool, bool],
) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    for i, on in enumerate(channels):
        if on:
            out[..., i] = 255 - out[..., i]
    return out


def flip_green(rgba: np.ndarray) -> np.ndarray:
    """DX ↔ GL normal Y (green)."""
    out = np.asarray(rgba, dtype=np.uint8).copy()
    out[..., 1] = 255 - out[..., 1]
    return out


def flip_horizontal(rgba: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.fliplr(np.asarray(rgba)))


def flip_vertical(rgba: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.flipud(np.asarray(rgba)))


def fill_channel(rgba: np.ndarray, index: int, value: int) -> np.ndarray:
    out = np.asarray(rgba, dtype=np.uint8).copy()
    out[..., max(0, min(3, index))] = max(0, min(255, int(value)))
    return out


def _renormalize_normals(rgb: np.ndarray) -> np.ndarray:
    """Re-pack unit normals after spatial filter (Trainz tangent maps)."""
    n = rgb.astype(np.float32) / 255.0 * 2.0 - 1.0
    length = np.sqrt(np.sum(n * n, axis=-1, keepdims=True))
    length = np.maximum(length, 1e-8)
    packed = np.clip((n / length) * 0.5 + 0.5, 0.0, 1.0) * 255.0
    return packed.astype(np.uint8)


def denoise_rgba(
    rgba: np.ndarray,
    *,
    strength: float = 40.0,
    role: MapRole = "",
    channels: tuple[bool, bool, bool, bool] = (True, True, True, False),
) -> np.ndarray:
    """Mild denoise via median + gaussian (Pillow — no OpenCV).

    ``strength`` 0…100. Alpha untouched unless ``channels[3]``.
    Normal maps: RGB filtered then re-normalized (keeps unit length).
    """
    src = np.asarray(rgba, dtype=np.uint8)
    s = max(0.0, min(100.0, float(strength)))
    if s < 0.5:
        return src.copy()

    # Map strength → odd median size + blur radius.
    if s < 25:
        median_size, blur = 3, 0.4 + s / 50.0
    elif s < 55:
        median_size, blur = 3, 0.8 + (s - 25) / 40.0
    elif s < 80:
        median_size, blur = 5, 1.2 + (s - 55) / 35.0
    else:
        median_size, blur = 5, 1.8 + (s - 80) / 25.0

    out = src.copy()
    # Filter only flagged channels; rebuild as RGBA for Pillow.
    work = Image.fromarray(src, mode="RGBA")
    filtered = work.filter(ImageFilter.MedianFilter(size=median_size))
    if blur > 0.05:
        filtered = filtered.filter(ImageFilter.GaussianBlur(radius=blur))
    farr = np.asarray(filtered, dtype=np.uint8)

    for i, on in enumerate(channels):
        if on:
            out[..., i] = farr[..., i]

    if role == "normal" and any(channels[:3]):
        rgb = out[..., :3].copy()
        # Always use filtered RGB for renorm when any RGB channel was touched.
        out[..., :3] = _renormalize_normals(rgb)

    return out


def save_trainz_image(
    path: Path,
    rgba: np.ndarray,
    *,
    bak: bool = True,
) -> Path:
    """Overwrite image; one-time sibling ``.bak``; keep extension semantics."""
    path = Path(path)
    if bak:
        bak_path = path.with_suffix(path.suffix + ".bak")
        if path.is_file() and not bak_path.exists():
            bak_path.write_bytes(path.read_bytes())

    arr = np.asarray(rgba, dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGBA")
    ext = path.suffix.lower()
    kwargs: dict = {}
    save_img = img
    if ext in (".jpg", ".jpeg"):
        save_img = img.convert("RGB")
        kwargs["quality"] = 95
    elif ext == ".png":
        kwargs["compress_level"] = 3
    elif ext == ".tga":
        # Trainz prefers uncompressed TGA; Pillow default is fine.
        pass
    elif ext in (".bmp",):
        save_img = img.convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_img.save(path, **kwargs)
    return path


@dataclass
class TexMapSession:
    """One open map — undo stack + dirty flag."""

    path: Path
    role: MapRole = ""
    pixels: np.ndarray = field(default_factory=lambda: np.zeros((1, 1, 4), np.uint8))
    dirty: bool = False
    _undo: list[np.ndarray] = field(default_factory=list)
    _redo: list[np.ndarray] = field(default_factory=list)

    @classmethod
    def open(cls, path: Path, *, role: MapRole = "") -> TexMapSession:
        path = Path(path)
        return cls(path=path, role=role, pixels=load_rgba(path), dirty=False)

    def snapshot(self) -> None:
        self._undo.append(self.pixels.copy())
        if len(self._undo) > _UNDO_CAP:
            self._undo.pop(0)
        self._redo.clear()

    def apply(self, new_pixels: np.ndarray, *, push_undo: bool = True) -> None:
        if push_undo:
            self.snapshot()
        self.pixels = np.asarray(new_pixels, dtype=np.uint8).copy()
        self.dirty = True

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.pixels.copy())
        self.pixels = self._undo.pop()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.pixels.copy())
        self.pixels = self._redo.pop()
        self.dirty = True
        return True

    def revert(self) -> None:
        self.pixels = load_rgba(self.path)
        self.dirty = False
        self._undo.clear()
        self._redo.clear()

    def save(self, *, bak: bool = True) -> Path:
        out = save_trainz_image(self.path, self.pixels, bak=bak)
        self.dirty = False
        return out
