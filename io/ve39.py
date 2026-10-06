"""VE39 solid-texture fixer — Trainz rejects near-uniform maps.

Ported from TrainzTextureEditor (add noise dots / optional shrink).
Writes in-place after a one-time sibling ``.bak``.
"""
from __future__ import annotations

import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


def is_uniform_color(img: Image.Image, tolerance: int = 2) -> tuple[bool, tuple[int, int, int, int]]:
    """Fast uniform check — downsample then corner/center spot-check."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    sample_w = min(64, w)
    sample_h = min(64, h)
    small = rgba if (w <= 64 and h <= 64) else rgba.resize((sample_w, sample_h), Image.NEAREST)
    pixels = small.getdata()
    it = iter(pixels)
    try:
        base = next(it)
    except StopIteration:
        return False, (0, 0, 0, 255)
    for px in it:
        if any(abs(int(px[i]) - int(base[i])) > tolerance for i in range(4)):
            return False, base
    if w * h > 4096:
        for x, y in (
            (0, 0),
            (w - 1, 0),
            (0, h - 1),
            (w - 1, h - 1),
            (w // 2, h // 2),
            (w // 4, h // 4),
            (3 * w // 4, 3 * h // 4),
        ):
            px = rgba.getpixel((x, y))
            if any(abs(int(px[i]) - int(base[i])) > tolerance for i in range(4)):
                return False, base
    return True, base


def color_to_hex(rgba: tuple[int, ...]) -> str:
    return "#{:02X}{:02X}{:02X}".format(rgba[0], rgba[1], rgba[2])


def add_noise_pixels(
    img: Image.Image,
    *,
    num_dots: int = 3,
    max_size: int = 5,
) -> Image.Image:
    """Paint a few inverse-color dots so the map is no longer uniform."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    draw = ImageDraw.Draw(rgba)
    base = rgba.getpixel((0, 0))
    noise = (255 - base[0], 255 - base[1], 255 - base[2], 255)
    for _ in range(max(1, num_dots)):
        x = random.randint(0, max(0, w - 1))
        y = random.randint(0, max(0, h - 1))
        sz = random.randint(1, max(1, max_size))
        rad = max(0, sz // 2)
        draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=noise)
    return rgba


def scan_ve39(path: Path) -> dict:
    """Return scan row: path, size, uniform, color_hex, error."""
    path = Path(path)
    out: dict = {
        "path": path,
        "size": "",
        "uniform": False,
        "color_hex": "-",
        "error": "",
    }
    try:
        with Image.open(path) as img:
            out["size"] = f"{img.size[0]}x{img.size[1]}"
            uniform, color = is_uniform_color(img)
            out["uniform"] = uniform
            out["color_hex"] = color_to_hex(color) if uniform else "-"
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


def fix_ve39(
    path: Path,
    *,
    bak: bool = True,
    num_dots: int = 3,
    max_size: int = 5,
    shrink_4x4: bool = False,
) -> tuple[bool, str]:
    """Fix a uniform texture in-place. Skips non-uniform. Returns (ok, msg)."""
    path = Path(path)
    if not path.is_file():
        return False, "not found"
    try:
        with Image.open(path) as img:
            uniform, color = is_uniform_color(img)
            if not uniform:
                return False, "not uniform (skip)"
            if bak:
                bak_path = path.with_suffix(path.suffix + ".bak")
                if not bak_path.is_file():
                    # ponytail: copy file bytes — ceiling = large TGA twice on disk
                    shutil.copy2(path, bak_path)
            if shrink_4x4:
                Image.new("RGBA", (4, 4), color).save(path)
                return True, "fixed (4×4)"
            add_noise_pixels(img, num_dots=num_dots, max_size=max_size).save(path)
            return True, "fixed (dots)"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
