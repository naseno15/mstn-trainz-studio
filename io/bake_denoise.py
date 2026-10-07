"""Bake-aware denoise for AO / lightmap / mesh-map grains.

Primary: Intel Open Image Denoise (RTLightmap) under ``vendor/oidn/``.
Fallback: OpenCV Non-Local Means (+ Guided Filter when ximgproc is present).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .. import PKG_ROOT

OIDN_EXE = PKG_ROOT / "vendor" / "oidn" / "bin" / "oidnDenoise.exe"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".exr", ".hdr", ".tga"}


@dataclass
class DenoiseSettings:
    strength: str = "heavy"  # light | balanced | heavy | nuclear
    preserve_black: bool = True
    black_threshold: int = 8
    restore_detail: float | None = None  # None → preset default
    prefer_oidn: bool = True
    color_mode: str = "auto"  # auto | gray | color


STRENGTH_PRESETS = {
    "light": {
        "oidn_quality": "balanced",
        "nlm_h": 12,
        "nlm_h2": 0,
        "nlm_search": 21,
        "guided_radius": 3,
        "guided_eps": 40.0,
        "detail": 0.28,
    },
    "balanced": {
        "oidn_quality": "high",
        "nlm_h": 18,
        "nlm_h2": 8,
        "nlm_search": 25,
        "guided_radius": 4,
        "guided_eps": 60.0,
        "detail": 0.24,
    },
    "heavy": {
        "oidn_quality": "high",
        "nlm_h": 26,
        "nlm_h2": 12,
        "nlm_search": 35,
        "guided_radius": 6,
        "guided_eps": 80.0,
        "detail": 0.20,
    },
    "nuclear": {
        "oidn_quality": "high",
        "nlm_h": 34,
        "nlm_h2": 16,
        "nlm_search": 41,
        "guided_radius": 8,
        "guided_eps": 110.0,
        "detail": 0.16,
    },
}


ProgressCb = Optional[Callable[[str, float], None]]


def oidn_available() -> bool:
    return OIDN_EXE.is_file()


def _emit(cb: ProgressCb, msg: str, frac: float) -> None:
    if cb:
        cb(msg, max(0.0, min(1.0, float(frac))))


def _guided_filter(guide: np.ndarray, src: np.ndarray, *, radius: int, eps: float) -> np.ndarray:
    """ximgproc.guidedFilter when available; else bilateral soft-edge polish."""
    ximg = getattr(cv2, "ximgproc", None)
    if ximg is not None and hasattr(ximg, "guidedFilter"):
        return ximg.guidedFilter(guide=guide, src=src, radius=int(radius), eps=float(eps))
    # ponytail: no contrib → bilateral; upgrade = opencv-contrib-python-headless
    d = max(3, int(radius) * 2 + 1)
    sigma = max(10.0, float(eps) ** 0.5)
    if src.ndim == 2:
        return cv2.bilateralFilter(src, d, sigma, sigma)
    return cv2.bilateralFilter(src, d, sigma, sigma)


def _island_mask(gray: np.ndarray, threshold: int) -> np.ndarray:
    mask = (gray > threshold).astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def _unsharp(img: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0.001:
        return img
    blur = cv2.GaussianBlur(img, (0, 0), 0.9)
    return cv2.addWeighted(img, 1.0 + amount, blur, -amount, 0)


def _write_pfm(path: Path, rgb_f32: np.ndarray) -> None:
    h, w = rgb_f32.shape[:2]
    data = np.flipud(rgb_f32.astype(np.float32, copy=False))
    with open(path, "wb") as f:
        f.write(b"PF\n")
        f.write(f"{w} {h}\n".encode("ascii"))
        f.write(b"-1.0\n")
        f.write(data.tobytes(order="C"))


def _read_pfm(path: Path) -> np.ndarray:
    with open(path, "rb") as f:
        magic = f.readline().strip()
        dims = f.readline().strip()
        _scale = float(f.readline().strip())
        w, h = map(int, dims.split())
        channels = 3 if magic == b"PF" else 1
        data = np.frombuffer(f.read(), dtype=np.float32)
        img = data.reshape((h, w, channels) if channels > 1 else (h, w))
        return np.flipud(img)


def _to_uint8(img_f: np.ndarray) -> np.ndarray:
    return np.clip(np.round(img_f * 255.0), 0, 255).astype(np.uint8)


def denoise_oidn(
    bgr: np.ndarray,
    settings: DenoiseSettings,
    progress: ProgressCb = None,
) -> np.ndarray:
    if not oidn_available():
        raise FileNotFoundError("OIDN not found")

    preset = STRENGTH_PRESETS[settings.strength]
    _emit(progress, "Preparing OIDN…", 0.15)

    if bgr.ndim == 2:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_GRAY2RGB)
        was_gray = True
    else:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        was_gray = False

    rgb_f = rgb.astype(np.float32) / 255.0

    with tempfile.TemporaryDirectory(prefix="bake_denoise_") as tmp:
        tmp_path = Path(tmp)
        in_pfm = tmp_path / "in.pfm"
        out_pfm = tmp_path / "out.pfm"
        _write_pfm(in_pfm, rgb_f)

        quality = str(preset["oidn_quality"])
        cmd = [
            str(OIDN_EXE),
            "-f",
            "RTLightmap",
            "-q",
            quality,
            "--ldr",
            str(in_pfm),
            "-o",
            str(out_pfm),
        ]

        _emit(progress, "OIDN RTLightmap…", 0.35)
        env = os.environ.copy()
        env["PATH"] = str(OIDN_EXE.parent) + os.pathsep + env.get("PATH", "")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(OIDN_EXE.parent),
            env=env,
        )
        if proc.returncode != 0 or not out_pfm.is_file():
            cmd_rt = [
                str(OIDN_EXE),
                "-f",
                "RT",
                "-q",
                quality,
                "--ldr",
                str(in_pfm),
                "-o",
                str(out_pfm),
            ]
            proc = subprocess.run(
                cmd_rt,
                capture_output=True,
                text=True,
                cwd=str(OIDN_EXE.parent),
                env=env,
            )
            if proc.returncode != 0 or not out_pfm.is_file():
                err = (proc.stderr or proc.stdout or "OIDN failed").strip()
                raise RuntimeError(err)

        _emit(progress, "Reading OIDN…", 0.75)
        out_rgb = _read_pfm(out_pfm)
        if out_rgb.ndim == 2:
            out_u8 = _to_uint8(out_rgb)
            return out_u8 if was_gray else cv2.cvtColor(out_u8, cv2.COLOR_GRAY2BGR)

        out_u8 = _to_uint8(out_rgb)
        if was_gray:
            return cv2.cvtColor(out_u8, cv2.COLOR_RGB2GRAY)
        return cv2.cvtColor(out_u8, cv2.COLOR_RGB2BGR)


def denoise_opencv(
    bgr: np.ndarray,
    settings: DenoiseSettings,
    progress: ProgressCb = None,
) -> np.ndarray:
    preset = STRENGTH_PRESETS[settings.strength]
    is_gray = bgr.ndim == 2 or (
        bgr.ndim == 3
        and np.allclose(bgr[:, :, 0], bgr[:, :, 1])
        and np.allclose(bgr[:, :, 1], bgr[:, :, 2])
    )

    if bgr.ndim == 3 and (settings.color_mode == "gray" or (settings.color_mode == "auto" and is_gray)):
        work = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray_out = True
    elif bgr.ndim == 2:
        work = bgr
        gray_out = True
    else:
        work = bgr
        gray_out = False

    _emit(progress, "Non-Local Means pass 1…", 0.25)
    if gray_out:
        den = cv2.fastNlMeansDenoising(
            work,
            None,
            h=float(preset["nlm_h"]),
            templateWindowSize=7,
            searchWindowSize=int(preset["nlm_search"]),
        )
        if preset["nlm_h2"]:
            _emit(progress, "Non-Local Means pass 2…", 0.55)
            den = cv2.fastNlMeansDenoising(
                den,
                None,
                h=float(preset["nlm_h2"]),
                templateWindowSize=7,
                searchWindowSize=21,
            )
        _emit(progress, "Edge polish…", 0.75)
        return _guided_filter(
            den, den, radius=int(preset["guided_radius"]), eps=float(preset["guided_eps"]) ** 2
        )

    den = cv2.fastNlMeansDenoisingColored(
        work,
        None,
        h=float(preset["nlm_h"]),
        hColor=float(preset["nlm_h"]),
        templateWindowSize=7,
        searchWindowSize=int(preset["nlm_search"]),
    )
    if preset["nlm_h2"]:
        _emit(progress, "Non-Local Means pass 2…", 0.55)
        den = cv2.fastNlMeansDenoisingColored(
            den,
            None,
            h=float(preset["nlm_h2"]),
            hColor=float(preset["nlm_h2"]),
            templateWindowSize=7,
            searchWindowSize=21,
        )
    _emit(progress, "Edge polish…", 0.75)
    return _guided_filter(
        den, den, radius=int(preset["guided_radius"]), eps=float(preset["guided_eps"]) ** 2
    )


def apply_bake_mask(
    original: np.ndarray,
    denoised: np.ndarray,
    threshold: int,
) -> np.ndarray:
    if original.ndim == 3:
        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    else:
        gray = original
    mask = _island_mask(gray, threshold)
    mask3 = mask if denoised.ndim == 2 else cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    return np.where(mask3 > 0, denoised, np.zeros_like(denoised))


def denoise_image(
    image_bgr_or_gray: np.ndarray,
    settings: DenoiseSettings | None = None,
    progress: ProgressCb = None,
) -> tuple[np.ndarray, str]:
    """Returns ``(denoised_image, engine_name)`` — does not write disk."""
    settings = settings or DenoiseSettings()
    if settings.strength not in STRENGTH_PRESETS:
        settings.strength = "heavy"
    preset = STRENGTH_PRESETS[settings.strength]
    detail = (
        float(settings.restore_detail)
        if settings.restore_detail is not None
        else float(preset["detail"])
    )

    _emit(progress, "Starting denoise…", 0.05)
    engine = "opencv"
    result = None
    err = None

    if settings.prefer_oidn and oidn_available():
        try:
            result = denoise_oidn(image_bgr_or_gray, settings, progress)
            engine = "oidn"
        except Exception as e:
            err = str(e)
            _emit(progress, f"OIDN failed → OpenCV ({e})", 0.20)

    if result is None:
        result = denoise_opencv(image_bgr_or_gray, settings, progress)
        engine = "opencv" if err is None else "opencv-fallback"

    src = image_bgr_or_gray
    if src.ndim == 2 and result.ndim == 3:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    elif src.ndim == 3 and result.ndim == 2:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    if engine.startswith("oidn") and settings.strength in {"heavy", "nuclear"}:
        _emit(progress, "OIDN polish…", 0.82)
        radius = max(3, int(preset["guided_radius"]) - 2)
        eps = float(preset["guided_eps"]) * 0.7
        if result.ndim == 2:
            result = _guided_filter(result, result, radius=radius, eps=eps**2)
        else:
            guide = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            chans = [
                _guided_filter(guide, c, radius=radius, eps=eps**2) for c in cv2.split(result)
            ]
            result = cv2.merge(chans)

    if settings.preserve_black:
        _emit(progress, "Locking black UV padding…", 0.88)
        result = apply_bake_mask(src, result, settings.black_threshold)

    if detail > 0:
        _emit(progress, "Restoring detail…", 0.93)
        sharp = _unsharp(result, detail)
        result = (
            apply_bake_mask(src, sharp, settings.black_threshold)
            if settings.preserve_black
            else sharp
        )

    _emit(progress, "Done", 1.0)
    return result, engine


def load_bake_image(path: str | Path) -> tuple[np.ndarray, np.ndarray | None]:
    """Load bake image → ``(bgr_or_gray, alpha_or_None)``."""
    path = Path(path)
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot open: {path}")
    if img.ndim == 3 and img.shape[2] == 4:
        return img[:, :, :3].copy(), img[:, :, 3].copy()
    return img, None


def compose_with_alpha(bgr_or_gray: np.ndarray, alpha: np.ndarray | None) -> np.ndarray:
    """RGBA uint8 for preview / Trainz save."""
    if bgr_or_gray.ndim == 2:
        rgb = cv2.cvtColor(bgr_or_gray, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(bgr_or_gray, cv2.COLOR_BGR2RGB)
    a = alpha if alpha is not None else np.full(rgb.shape[:2], 255, dtype=np.uint8)
    return np.dstack([rgb, a]).astype(np.uint8)


def bgr_from_rgba(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split working RGBA → BGR + A for denoise engine."""
    rgb = np.asarray(rgba[..., :3], dtype=np.uint8)
    a = np.asarray(rgba[..., 3], dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), a
