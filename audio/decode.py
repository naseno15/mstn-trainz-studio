"""Load audio to mono PCM16 (WAV native; other formats via ffmpeg if present)."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .classify import AUDIO_EXTS, VIDEO_EXTS
from .ffmpeg_cfg import get_ffmpeg_path

DST_RATE = 44100


def find_ffmpeg() -> str | None:
    return get_ffmpeg_path()


def _read_wav_pcm16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) << 8
    elif sw == 2:
        data = np.frombuffer(raw, dtype="<i2").copy()
    elif sw == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        v = (
            a[:, 0].astype(np.int32)
            | (a[:, 1].astype(np.int32) << 8)
            | (a[:, 2].astype(np.int32) << 16)
        )
        v = np.where(v & 0x800000, v - 0x1000000, v)
        data = (v >> 8).astype(np.int16)
    elif sw == 4:
        data = (np.frombuffer(raw, dtype="<i4") >> 16).astype(np.int16)
    else:
        raise ValueError(f"unsupported sample width {sw}: {path}")
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return data, int(sr)


def resample_linear(mono: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or mono.size == 0:
        return mono
    n_out = max(1, int(round(mono.shape[0] * dst_rate / src_rate)))
    x_old = np.linspace(0.0, 1.0, num=mono.shape[0], endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, mono.astype(np.float64)).astype(np.int16)


def ffmpeg_to_wav(src: Path, dst: Path, *, sample_rate: int = DST_RATE) -> None:
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError(
            "ffmpeg not found — click Sounds → ffmpeg… to set path, or install ffmpeg on PATH"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff,
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-sample_fmt",
        "s16",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0 or not dst.is_file():
        err = (r.stderr or r.stdout or "ffmpeg failed").strip().splitlines()[-8:]
        raise RuntimeError("ffmpeg convert failed:\n" + "\n".join(err))


def load_mono_pcm16(
    path: Path,
    *,
    sample_rate: int = DST_RATE,
    work_dir: Path | None = None,
) -> tuple[np.ndarray, int, Path]:
    """Return (mono int16, sample_rate, source_or_converted_path)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suf = path.suffix.lower()
    if suf == ".wav":
        mono, sr = _read_wav_pcm16(path)
        if sr != sample_rate:
            mono = resample_linear(mono, sr, sample_rate)
            sr = sample_rate
        return mono, sr, path

    if suf not in AUDIO_EXTS | VIDEO_EXTS:
        raise ValueError(f"unsupported media: {path.name}")

    base = work_dir or (Path.home() / ".cache" / "trainz_studio" / "import")
    base.mkdir(parents=True, exist_ok=True)
    dst = base / f"{path.stem}_{path.stat().st_mtime_ns}_{sample_rate}.wav"
    if not dst.is_file() or dst.stat().st_mtime < path.stat().st_mtime:
        ffmpeg_to_wav(path, dst, sample_rate=sample_rate)
    mono, sr = _read_wav_pcm16(dst)
    if sr != sample_rate:
        mono = resample_linear(mono, sr, sample_rate)
        sr = sample_rate
    return mono, sr, dst
