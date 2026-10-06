"""KUID extract / normalize / hash (Assets Studio)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...io import kuid_bin

_KUID_RE = re.compile(
    r"<\s*(kuid2?)\s*:\s*(-?\d+)\s*:\s*(-?\d+)(?:\s*:\s*(-?\d+))?\s*>",
    re.IGNORECASE,
)
_BARE_RE = re.compile(
    r"\b(kuid2?)\s*:\s*(-?\d+)\s*:\s*(-?\d+)(?:\s*:\s*(-?\d+))?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Kuid:
    kind: str  # kuid | kuid2
    creator: int
    content: int
    version: int | None = None

    def format(self, *, angle: bool = True) -> str:
        if self.kind == "kuid2" and self.version is not None:
            body = f"kuid2:{self.creator}:{self.content}:{self.version}"
        else:
            body = f"kuid:{self.creator}:{self.content}"
        return f"<{body}>" if angle else body

    def key(self) -> tuple[str, int, int, int | None]:
        return (self.kind, self.creator, self.content, self.version)

    def to_bytes(self) -> bytes:
        return kuid_bin.pack_kuid(self.creator, self.content, self.version)

    def hex(self, *, reversed_: bool = False) -> str:
        raw = self.to_bytes()
        if reversed_:
            raw = kuid_bin.reverse_uuvv_nnnn(raw)
        return kuid_bin.bytes_to_hex(raw)

    def hash_folder(self) -> str:
        return kuid_bin.hash_folder(self.to_bytes())


def _from_groups(kind: str, a: str, b: str, c: str | None) -> Kuid | None:
    kind_l = kind.lower()
    try:
        creator = int(a)
        content = int(b)
        version = int(c) if c is not None and c != "" else None
    except ValueError:
        return None
    if kind_l == "kuid2":
        if version is None:
            return None
        return Kuid("kuid2", creator, content, version)
    return Kuid("kuid", creator, content, None)


def extract_kuids(text: str) -> list[Kuid]:
    found: list[Kuid] = []
    seen: set[tuple[str, int, int, int | None]] = set()

    def _add(k: Kuid | None) -> None:
        if k is None:
            return
        key = k.key()
        if key in seen:
            return
        seen.add(key)
        found.append(k)

    for m in _KUID_RE.finditer(text or ""):
        _add(_from_groups(m.group(1), m.group(2), m.group(3), m.group(4)))
    for m in _BARE_RE.finditer(text or ""):
        start, end = m.span()
        window = (text or "")[max(0, start - 1) : min(len(text or ""), end + 1)]
        if "<" in window and ">" in window:
            continue
        _add(_from_groups(m.group(1), m.group(2), m.group(3), m.group(4)))
    return found


def normalize_list(text: str, *, angle: bool = True) -> str:
    return "\n".join(k.format(angle=angle) for k in extract_kuids(text))


def count_kuids(text: str) -> int:
    return len(extract_kuids(text))


def describe_kuid(text: str) -> str:
    """One KUID → hex + hash folder (Kuid2Hash / Chump expander)."""
    ks = extract_kuids(text)
    if not ks:
        raw = kuid_bin.parse_kuid_string(text.strip())
        if raw is None:
            # try bare hex
            try:
                raw = kuid_bin.hex_to_bytes(text)
                return (
                    f"{kuid_bin.bytes_to_kuid(raw)}\n"
                    f"hex:  {kuid_bin.bytes_to_hex(raw)}\n"
                    f"map:  {kuid_bin.bytes_to_hex(kuid_bin.reverse_uuvv_nnnn(raw))}\n"
                    f"{kuid_bin.hash_folder(raw)}"
                )
            except ValueError:
                return "No KUID found"
        return (
            f"{kuid_bin.bytes_to_kuid(raw)}\n"
            f"hex:  {kuid_bin.bytes_to_hex(raw)}\n"
            f"map:  {kuid_bin.bytes_to_hex(kuid_bin.reverse_uuvv_nnnn(raw))}\n"
            f"{kuid_bin.hash_folder(raw)}"
        )
    lines: list[str] = []
    for k in ks:
        lines.append(k.format())
        lines.append(f"  hex:  {k.hex()}")
        lines.append(f"  map:  {k.hex(reversed_=True)}")
        lines.append(f"  {k.hash_folder()}")
    return "\n".join(lines)
