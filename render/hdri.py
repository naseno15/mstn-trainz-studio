"""Radiance RGBE (.hdr) load + Poly Haven asset catalog (CC0)."""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import PKG_ROOT

HERE = PKG_ROOT
HDRI_DIR = PKG_ROOT / "assets" / "hdri"


@dataclass(frozen=True)
class HdriAsset:
    key: str
    label: str
    path: Path
    credit: str = "Poly Haven — CC0"


def _read_rgbe_header(f) -> tuple[int, int]:
    width = height = 0
    while True:
        line = f.readline()
        if not line:
            raise ValueError("truncated HDR header")
        if line in (b"\n", b"\r\n"):
            break
        if line.startswith(b"FORMAT"):
            continue
    res = f.readline().decode("ascii", errors="ignore").strip()
    # -Y height +X width
    parts = res.replace("+", " +").replace("-", " -").split()
    for i, p in enumerate(parts):
        if p in ("-Y", "+Y") and i + 1 < len(parts):
            height = int(parts[i + 1])
        if p in ("+X", "-X") and i + 1 < len(parts):
            width = int(parts[i + 1])
    if width <= 0 or height <= 0:
        raise ValueError(f"bad HDR resolution: {res!r}")
    return width, height


def _decode_rgbe_scanline(f, width: int) -> np.ndarray:
    """Return float32 (width, 3) RGB for one scanline."""
    # New RLE: first pixel is 2,2,width>>8,width&255
    raw = f.read(4)
    if len(raw) < 4:
        raise ValueError("EOF in HDR scanline")
    r0, r1, r2, r3 = raw[0], raw[1], raw[2], raw[3]
    # ponytail: cast before << — np.uint8<<8 wraps to 0 and breaks RLE detect
    scan_w = (int(r2) << 8) | int(r3)
    if r0 == 2 and r1 == 2 and scan_w == width:
        channels = np.empty((4, width), dtype=np.uint8)
        for c in range(4):
            x = 0
            while x < width:
                count = f.read(1)[0]
                if count > 128:
                    run = count - 128
                    val = f.read(1)[0]
                    if run <= 0 or x + run > width:
                        raise ValueError(f"bad HDR RLE run c={c} x={x} run={run}")
                    channels[c, x : x + run] = val
                    x += run
                else:
                    if count == 0 or x + count > width:
                        raise ValueError(f"bad HDR RLE lit c={c} x={x} n={count}")
                    buf = f.read(count)
                    if len(buf) != count:
                        raise ValueError("EOF in HDR RLE literals")
                    channels[c, x : x + count] = np.frombuffer(buf, dtype=np.uint8)
                    x += count
        rgbe_px = np.stack([channels[0], channels[1], channels[2], channels[3]], axis=1)
    else:
        # flat older format — already have first pixel
        rest = f.read(4 * (width - 1))
        if len(rest) != 4 * (width - 1):
            raise ValueError("EOF in HDR flat scanline")
        first = np.array([[r0, r1, r2, r3]], dtype=np.uint8)
        rest_px = np.frombuffer(rest, dtype=np.uint8).reshape(-1, 4)
        rgbe_px = np.vstack([first, rest_px])

    e = rgbe_px[:, 3].astype(np.int32)
    rgb = rgbe_px[:, :3].astype(np.float32)
    out = np.zeros((width, 3), dtype=np.float32)
    mask = e != 0
    # Ldexp: rgb * 2^(e-128-8)
    out[mask] = (rgb[mask] / 255.0) * np.ldexp(1.0, e[mask] - 128).astype(np.float32)[:, None]
    return out


def load_rgbe(path: Path | str) -> tuple[int, int, np.ndarray]:
    """Load Radiance .hdr → (w, h, float32 RGB HxWx3)."""
    path = Path(path)
    with path.open("rb") as f:
        magic = f.readline()
        if not magic.startswith(b"#?RADIANCE") and not magic.startswith(b"#?RGBE"):
            raise ValueError(f"not a Radiance HDR: {path.name}")
        width, height = _read_rgbe_header(f)
        rows = []
        for _ in range(height):
            rows.append(_decode_rgbe_scanline(f, width))
        img = np.stack(rows, axis=0)
    return width, height, img


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 luminance; rgb HxWx3 float."""
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def auto_exposure(hdr: np.ndarray, *, target: float = 0.22) -> float:
    """UE5-ish mid-gray fit from median luminance (ignores pure black)."""
    lum = luminance(hdr)
    mask = lum > 1e-5
    if not np.any(mask):
        return 1.0
    med = float(np.median(lum[mask]))
    return float(np.clip(target / max(med, 1e-4), 0.04, 12.0))


def tonemap_aces(hdr: np.ndarray, exposure: float = 1.0) -> bytes:
    """ACES fitted curve → sRGB8 (prettier highlights than plain Reinhard)."""
    x = np.clip(hdr * exposure, 0.0, None).astype(np.float32)
    # Fitted ACES (Narkowicz) — keeps suns hot without washing the whole sky
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    ldr = (x * (a * x + b)) / (x * (c * x + d) + e)
    ldr = np.power(np.clip(ldr, 0.0, 1.0), 1.0 / 2.2)
    u8 = (ldr * 255.0 + 0.5).astype(np.uint8)
    return u8.tobytes()


def tonemap_reinhard(hdr: np.ndarray, exposure: float = 1.0) -> bytes:
    """float HxWx3 → RGB8 bytes (row-major) for GL upload."""
    return tonemap_aces(hdr, exposure=exposure)


def equirect_pixel_to_dir(ix: int, iy: int, w: int, h: int) -> tuple[float, float, float]:
    """Pixel (ix,iy) top-left origin → unit Y-up direction (matches sky dirToEquirect)."""
    u = (ix + 0.5) / max(w, 1)
    v_tex = (iy + 0.5) / max(h, 1)
    v = 1.0 - v_tex
    phi = (u - 0.5) * (2.0 * math.pi)  # atan2(z, x)
    el = (v - 0.5) * math.pi  # asin(y)
    cos_el = math.cos(el)
    return (cos_el * math.cos(phi), math.sin(el), cos_el * math.sin(phi))


def dir_to_az_el(dx: float, dy: float, dz: float) -> tuple[float, float]:
    """HDRI Y-up unit dir → (az, el) for sun_dir_zup (Trainz Z-up viewport)."""
    # Y-up (x,y,z) → Z-up (x, -z, y)
    zx, zy, zz = float(dx), float(-dz), float(dy)
    el = math.degrees(math.asin(float(np.clip(zz, -1.0, 1.0))))
    az = math.degrees(math.atan2(zx, zy))
    if az < 0.0:
        az += 360.0
    return az, el


def find_sun_dir(hdr: np.ndarray) -> tuple[float, float, float]:
    """Brightest region on equirect → sun direction (small box blur kills fireflies)."""
    h, w = hdr.shape[:2]
    lum = luminance(hdr)
    # 3×3 max-of-mean — cheap anti-firefly without scipy
    pad = np.pad(lum, 1, mode="edge")
    score = np.zeros_like(lum)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            score += pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    score *= 1.0 / 9.0
    iy, ix = np.unravel_index(int(np.argmax(score)), score.shape)
    return equirect_pixel_to_dir(int(ix), int(iy), w, h)


def resolve_hdri_path(path: Path | str) -> Path:
    """Prefer sibling .hdr over tonemapped .jpg when both exist."""
    path = Path(path)
    if path.suffix.lower() == ".hdr" and path.is_file():
        return path
    hdr = path.with_suffix(".hdr")
    if hdr.is_file():
        return hdr
    return path


def load_hdri_rgba8(
    path: Path | str,
    *,
    max_w: int = 1536,
    exposure: float | None = None,
) -> tuple[int, int, bytes, dict]:
    """Load .hdr (or LDR) as RGBA8 for OpenGL.

    Returns (w, h, rgba_bytes, meta) where meta may include sun_az/sun_el/exposure.
    """
    path = resolve_hdri_path(path)
    meta: dict = {"path": str(path), "exposure": 1.0}
    if path.suffix.lower() == ".hdr":
        try:
            w, h, img = load_rgbe(path)
        except Exception as exc:
            jpg = path.with_suffix(".jpg")
            if jpg.is_file():
                print(f"trainz_studio: HDR decode failed ({exc}); using {jpg.name}", flush=True)
                return load_hdri_rgba8(jpg, max_w=max_w, exposure=exposure)
            raise
        if w > max_w:
            step = int(np.ceil(w / max_w))
            img = img[::step, ::step]
            h, w = img.shape[:2]
        exp = float(exposure) if exposure is not None else auto_exposure(img)
        meta["exposure"] = exp
        sx, sy, sz = find_sun_dir(img)
        az, el = dir_to_az_el(sx, sy, sz)
        meta["sun_dir"] = (sx, sy, sz)
        meta["sun_az"] = az
        meta["sun_el"] = el
        rgb = tonemap_aces(img, exposure=exp)
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = np.frombuffer(rgb, dtype=np.uint8).reshape(h, w, 3)
        rgba[..., 3] = 255
        return w, h, rgba.tobytes(), meta
    from PIL import Image

    im = Image.open(path).convert("RGBA")
    if im.width > max_w:
        nh = max(1, int(im.height * (max_w / im.width)))
        im = im.resize((max_w, nh), Image.Resampling.BILINEAR)
    # LDR fallback — rough sun from brightest pixel
    arr = np.asarray(im, dtype=np.float32)[..., :3] / 255.0
    sx, sy, sz = find_sun_dir(arr)
    az, el = dir_to_az_el(sx, sy, sz)
    meta["sun_dir"] = (sx, sy, sz)
    meta["sun_az"] = az
    meta["sun_el"] = el
    return im.width, im.height, im.tobytes(), meta


def list_hdri_assets() -> list[HdriAsset]:
    man = HDRI_DIR / "manifest.json"
    out: list[HdriAsset] = []
    if man.is_file():
        for row in json.loads(man.read_text(encoding="utf-8")):
            p = resolve_hdri_path(HDRI_DIR / row["file"])
            if p.is_file():
                out.append(
                    HdriAsset(
                        key=row["key"],
                        label=row.get("label") or row["key"],
                        path=p,
                        credit=row.get("credit") or "Poly Haven — CC0",
                    )
                )
        if out:
            return out
    # fallback: any .hdr/.jpg in folder (hdr first, skip jpg twin)
    seen: set[str] = set()
    for p in sorted(HDRI_DIR.glob("*.hdr")) + sorted(HDRI_DIR.glob("*.jpg")):
        if p.stem in seen:
            continue
        seen.add(p.stem)
        out.append(HdriAsset(key=p.stem, label=p.stem.replace("_", " ").title(), path=p))
    return out
