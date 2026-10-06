"""Fast texture decode + disk precache for Mesh Studio preview.

Pipeline:
  1) Look up sidecar RGBA8 cache (mtime-keyed) — millisecond reload
  2) Else decode with Pillow, downsample for preview, write cache
  3) Parallel preload via ThreadPoolExecutor during mesh open

Preview downsamples to PREVIEW_MAX_DIM (default 2048) — cabin PNGs are often
4k–8k and dominate load time; GPU still looks sharp at 2k in this viewer.
"""
from __future__ import annotations

import hashlib
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ..util.hw import decode_workers

# Soft cap for preview GPU upload size (longest edge). 0 = full res.
# Albedo downs to 2k on open (cabin 4k–8k dominated load); normals/params stay full —
# downsampling those tore ceilings under lamp cast.
PREVIEW_MAX_DIM = 0
PREVIEW_MAX_DIM_ALBEDO = 2048
# Parallel CPU decoders during open — sized to this machine
DECODE_WORKERS = decode_workers()

_CACHE_MAGIC = b"MSRGBA1\0"
_CACHE_VER = 1


def cache_root() -> Path:
    """User-local cache (survives across mesh folders / sessions)."""
    base = Path.home() / ".cache" / "trainz_studio" / "tex"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_path(src: Path, *, flip_v: bool, max_dim: int) -> Path:
    try:
        st = src.stat()
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        size = st.st_size
    except OSError:
        mtime_ns, size = 0, 0
    key = f"{src.resolve()}|{mtime_ns}|{size}|flip={int(flip_v)}|dim={max_dim}|v{_CACHE_VER}"
    digest = hashlib.sha1(key.encode("utf-8", errors="replace")).hexdigest()
    return cache_root() / f"{digest}.rgba"


def _write_cache(path: Path, w: int, h: int, pixels: bytes) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(_CACHE_MAGIC)
            f.write(struct.pack("<III", _CACHE_VER, w, h))
            f.write(pixels)
        tmp.replace(path)
    except OSError:
        pass


def _read_cache(path: Path) -> tuple[int, int, bytes] | None:
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
            if magic != _CACHE_MAGIC:
                return None
            ver, w, h = struct.unpack("<III", f.read(12))
            if ver != _CACHE_VER or w < 1 or h < 1 or w * h > 64_000_000:
                return None
            need = w * h * 4
            data = f.read(need)
            if len(data) != need:
                return None
            return w, h, data
    except OSError:
        return None


def load_rgba(
    path: str | Path,
    *,
    flip_v: bool = False,
    max_dim: int = PREVIEW_MAX_DIM,
    use_cache: bool = True,
) -> tuple[int, int, bytes]:
    """Decode image → RGBA8 bytes (optionally cached + downsampled)."""
    src = Path(path)
    if use_cache:
        cp = _cache_path(src, flip_v=flip_v, max_dim=max_dim)
        hit = _read_cache(cp)
        if hit is not None:
            return hit

    from PIL import Image, ImageOps

    with Image.open(src) as im:
        img = im.convert("RGBA")
        if flip_v:
            img = ImageOps.flip(img)
        if max_dim > 0 and max(img.width, img.height) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.BILINEAR)
        w, h = img.width, img.height
        pixels = img.tobytes()

    if use_cache:
        _write_cache(_cache_path(src, flip_v=flip_v, max_dim=max_dim), w, h, pixels)
    return w, h, pixels


def collect_scene_texture_paths(parts) -> list[str]:
    """Unique existing albedo / normal / parameter paths (albedo first)."""
    albedos, others = collect_scene_texture_paths_split(parts)
    return albedos + others


def collect_scene_texture_paths_split(parts) -> tuple[list[str], list[str]]:
    """Return (albedo_paths, normal_and_param_paths) — unique existing files."""
    seen: set[str] = set()
    albedos: list[str] = []
    others: list[str] = []
    for part in parts:
        for p, bucket in (
            (getattr(part, "albedo_path", None), albedos),
            (getattr(part, "normal_path", None), others),
            (getattr(part, "parameter_path", None), others),
        ):
            if not p or p in seen:
                continue
            if Path(p).is_file():
                seen.add(p)
                bucket.append(p)
    return albedos, others


ProgressCb = Callable[[str, int], None] | None


def preload_textures(
    paths: list[str],
    *,
    flip_v: bool = False,
    max_dim: int = PREVIEW_MAX_DIM,
    workers: int = DECODE_WORKERS,
    progress: ProgressCb = None,
) -> dict[str, tuple[int, int, bytes]]:
    """Decode many textures in parallel. Returns path → (w, h, rgba bytes)."""
    out: dict[str, tuple[int, int, bytes]] = {}
    if not paths:
        return out
    n = len(paths)
    workers = max(1, min(workers, n))
    done = 0
    t0 = time.perf_counter()

    def _one(p: str) -> tuple[str, tuple[int, int, bytes] | None]:
        try:
            return p, load_rgba(p, flip_v=flip_v, max_dim=max_dim)
        except Exception:
            return p, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, p) for p in paths]
        for fut in as_completed(futs):
            path, rgba = fut.result()
            done += 1
            if rgba is not None:
                out[path] = rgba
            if progress is not None:
                pct = int(5 + 90 * done / n)
                progress(f"Precache textures {done}/{n}…", pct)

    if progress is not None:
        dt = time.perf_counter() - t0
        progress(f"Precached {len(out)}/{n} textures in {dt:.2f}s", 96)
    return out


def clear_cache() -> int:
    """Delete all disk precache files. Returns count removed."""
    root = cache_root()
    n = 0
    for p in root.glob("*.rgba"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n
