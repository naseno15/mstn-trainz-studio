"""KUID ↔ 8-byte UUUVNNNN + hash bucket — CDPExplorer/Kuid2Hash (public RE)."""
from __future__ import annotations

import re
import struct

_KUID_RE = re.compile(
    r"<\s*(kuid2?)\s*:\s*(-?\d+)\s*:\s*(-?\d+)(?:\s*:\s*(-?\d+))?\s*>",
    re.IGNORECASE,
)


def pack_kuid(creator: int, content: int, version: int | None = None) -> bytes:
    """Pack to little-endian 8 bytes (UUUV + NNNN)."""
    user = struct.pack("<i", int(creator))
    cont = struct.pack("<i", int(content))
    ub = bytearray(user)
    if version is not None and 0 < int(version) < 128 and creator >= 0:
        ub[3] = (ub[3] & 1) | ((int(version) & 0x7F) << 1)
    return bytes(ub) + cont


def unpack_kuid(raw: bytes) -> tuple[int, int, int]:
    """Return (creator, content, version)."""
    if len(raw) < 8:
        raise ValueError("kuid needs 8 bytes")
    ub = bytearray(raw[:4])
    version = ub[3] >> 1
    sign = ub[3] & 1
    ub[3] = 0xFF if sign else 0
    creator = struct.unpack("<i", bytes(ub))[0]
    content = struct.unpack("<i", raw[4:8])[0]
    return creator, content, version


def format_kuid(creator: int, content: int, version: int | None) -> str:
    if version is not None and version > 0 and creator >= 0:
        return f"<kuid2:{creator}:{content}:{version}>"
    if version == 0 and creator < 0:
        return f"<kuid2:{creator}:{content}:{version}>"
    return f"<kuid:{creator}:{content}>"


def bytes_to_kuid(raw: bytes) -> str:
    c, n, v = unpack_kuid(raw)
    # Match CDPExplorer display: kuid2 when version>0 and user>0, or version==0 and user<0
    if (v > 0 and c > 0) or (v == 0 and c < 0):
        return f"<kuid2:{c}:{n}:{v}>"
    return f"<kuid:{c}:{n}>"


def parse_kuid_string(text: str) -> bytes | None:
    m = _KUID_RE.search(text or "")
    if not m:
        return None
    kind = m.group(1).lower()
    creator = int(m.group(2))
    content = int(m.group(3))
    ver_s = m.group(4)
    if kind == "kuid2":
        version = int(ver_s) if ver_s is not None else 127
        return pack_kuid(creator, content, version)
    return pack_kuid(creator, content, None)


def kuid_hash(raw: bytes) -> int:
    """0–255 bucket (hash-XX). Version bits ignored when user id is positive."""
    if len(raw) < 8:
        raise ValueError("kuid needs 8 bytes")
    h = 0
    for b in raw[:8]:
        h ^= b
    if (raw[3] & 1) == 0:
        h ^= raw[3]
    return h & 0xFF


def hash_folder(raw: bytes) -> str:
    return f"hash-{kuid_hash(raw):02X}"


def bytes_to_hex(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw[:8])


def hex_to_bytes(text: str) -> bytes:
    parts = re.split(r"[\s\-:,]+", (text or "").strip())
    parts = [p for p in parts if p]
    out = bytearray(8)
    for i, p in enumerate(parts[:8]):
        out[i] = int(p, 16)
    return bytes(out)


def reverse_uuvv_nnnn(raw: bytes) -> bytes:
    """Map-file order: NNNN + UUUV."""
    if len(raw) < 8:
        raise ValueError("kuid needs 8 bytes")
    return raw[4:8] + raw[:4]
