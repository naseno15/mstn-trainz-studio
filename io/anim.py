"""Companion .kin listing — JIRF peek (frames + bone names); no transform decode."""
from __future__ import annotations

import struct
from pathlib import Path

from .scene import AnimClip

# Observed layout (Trainz .kin / JIRF):
#   0  JIRF + pad
#   8  ANIMINFO + pad
#  20  version / flags …
#  28  u32 frame_count
#  32  u32 tick (often 60)
# then tagged chunks: EVNT, SKEL, BONE, FRAM…
# BONE: "BONE" + pad + u32(0x64) + u32 name_len + ASCII name


def scan_kin_files(folder: Path) -> list[AnimClip]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [peek_kin(p) for p in sorted(folder.glob("*.kin")) if p.is_file()]


def peek_kin(path: Path) -> AnimClip:
    path = Path(path)
    clip = AnimClip(path=path, name=path.name)
    try:
        data = path.read_bytes()
    except OSError as e:
        clip.note = f"unreadable: {e}"
        return clip

    if len(data) < 36 or data[:4] != b"JIRF":
        clip.note = "not a JIRF .kin"
        return clip

    frames = _animinfo_frame_count(data)
    if frames <= 0:
        frames = _count_tag(data, b"FRAM")
    clip.frame_count = frames
    clip.bone_names = _bone_names(data)
    tick = struct.unpack_from("<I", data, 32)[0] if len(data) >= 36 else 0
    bits = [f"{frames} frames", f"{len(clip.bone_names)} bones"]
    if 1 <= tick <= 240:
        bits.append(f"tick={tick}")
    bits.append("transforms not decoded")
    clip.note = "; ".join(bits)
    return clip


def _animinfo_frame_count(data: bytes) -> int:
    # ANIMINFO chunk starts at offset 8 in known samples
    if data[8:16] != b"ANIMINFO":
        idx = data.find(b"ANIMINFO")
        if idx < 0 or idx + 28 > len(data):
            return 0
        # frame_count is 20 bytes after tag start (tag 8 + pad 4 + ver 4 + flags 4)
        base = idx + 20
    else:
        base = 28  # absolute offset in file for frame_count
    n = struct.unpack_from("<I", data, base)[0]
    return n if 1 <= n <= 100_000 else 0


def _count_tag(data: bytes, tag: bytes) -> int:
    count = 0
    i = 0
    while True:
        j = data.find(tag, i)
        if j < 0:
            break
        count += 1
        i = j + len(tag)
    return count


def _bone_names(data: bytes) -> list[str]:
    """BONE + 4 zero pad + u32 type(0x64) + u32 len + ASCII."""
    names: list[str] = []
    seen: set[str] = set()
    i = 0
    while True:
        j = data.find(b"BONE", i)
        if j < 0 or j + 16 > len(data):
            break
        # expect pad zeros then 0x64
        pad = struct.unpack_from("<I", data, j + 4)[0]
        kind = struct.unpack_from("<I", data, j + 8)[0]
        if pad != 0 or kind != 0x64:
            i = j + 4
            continue
        namelen = struct.unpack_from("<I", data, j + 12)[0]
        start = j + 16
        if not (1 <= namelen <= 256) or start + namelen > len(data):
            i = j + 4
            continue
        raw = data[start : start + namelen]
        if not all(32 <= b < 127 for b in raw):
            i = j + 4
            continue
        name = raw.decode("ascii")
        if name not in seen:
            seen.add(name)
            names.append(name)
        i = start + namelen
    return names
