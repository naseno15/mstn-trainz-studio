"""Trainz config.chump ↔ text — ACS$ tag soup (CDPExplorer + ChumpLib MIT).

A ``.chump`` is a packed config (same tag layout as CDP without the archive
wrapper). Round-trip: binary ↔ config-like text for editing.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from . import kuid_bin

MAGIC = b"ACS$"
TYPE_SOUP = 0
TYPE_INT = 1
TYPE_FLOAT = 2
TYPE_TEXT = 3
TYPE_RAW = 4
TYPE_NULL = 5
TYPE_KUID = 13

Value = Union[
    "ChumpSoup",
    list[int],
    list[float],
    str,
    bytes,  # raw / kuid raw
    None,
]


@dataclass
class ChumpTag:
    name: str
    type: int
    value: Value = None

    @staticmethod
    def soup(name: str, children: list[ChumpTag] | None = None) -> ChumpTag:
        return ChumpTag(name, TYPE_SOUP, ChumpSoup(children or []))

    @staticmethod
    def text(name: str, value: str) -> ChumpTag:
        return ChumpTag(name, TYPE_TEXT, value)

    @staticmethod
    def integer(name: str, *values: int) -> ChumpTag:
        return ChumpTag(name, TYPE_INT, list(values))

    @staticmethod
    def floating(name: str, *values: float) -> ChumpTag:
        return ChumpTag(name, TYPE_FLOAT, list(values))

    @staticmethod
    def kuid(name: str, raw: bytes) -> ChumpTag:
        return ChumpTag(name, TYPE_KUID, bytes(raw[:8]))

    @staticmethod
    def null(name: str) -> ChumpTag:
        return ChumpTag(name, TYPE_NULL, None)


@dataclass
class ChumpSoup:
    children: list[ChumpTag] = field(default_factory=list)


@dataclass
class ChumpFile:
    version: int = 1
    reserved: int = 0
    root: list[ChumpTag] = field(default_factory=list)


# ── binary read / write ─────────────────────────────────────────────────────


def read_chump(path: Path | bytes) -> ChumpFile:
    data = path if isinstance(path, (bytes, bytearray, memoryview)) else Path(path).read_bytes()
    data = memoryview(bytes(data))
    if len(data) < 16 or bytes(data[:4]) != MAGIC:
        raise ValueError("not a chump (missing ACS$)")
    version = struct.unpack_from("<I", data, 4)[0]
    reserved = struct.unpack_from("<I", data, 8)[0]
    length = struct.unpack_from("<I", data, 12)[0]
    start, end = 16, min(16 + length, len(data))
    root: list[ChumpTag] = []
    pos = start
    while pos < end:
        tag, pos = _read_tag(data, pos, end)
        root.append(tag)
    return ChumpFile(version=version, reserved=reserved, root=root)


def encode_chump(chump: ChumpFile) -> bytes:
    body = bytearray()
    for tag in chump.root:
        body.extend(_encode_tag(tag))
    out = bytearray()
    out.extend(MAGIC)
    out.extend(struct.pack("<II", chump.version, chump.reserved))
    out.extend(struct.pack("<I", len(body)))
    out.extend(body)
    return bytes(out)


def write_chump(path: Path, chump: ChumpFile) -> Path:
    path = Path(path)
    path.write_bytes(encode_chump(chump))
    return path


def _read_tag(data: memoryview, pos: int, limit: int) -> tuple[ChumpTag, int]:
    if pos + 5 > limit:
        raise ValueError("truncated chump tag")
    pair_len = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    pair_end = min(pos + pair_len, limit)
    name_size = int(data[pos])
    pos += 1
    if name_size < 1 or pos + name_size > pair_end:
        raise ValueError("bad chump tag name")
    name = bytes(data[pos : pos + name_size - 1]).decode("utf-8", errors="replace")
    pos += name_size
    if pos >= pair_end:
        return ChumpTag(name, TYPE_NULL, None), pair_end
    ttype = int(data[pos])
    pos += 1
    payload = bytes(data[pos:pair_end])

    if ttype == TYPE_SOUP:
        children: list[ChumpTag] = []
        cpos = 0
        view = memoryview(payload)
        while cpos < len(payload):
            child, cpos = _read_tag(view, cpos, len(payload))
            children.append(child)
        return ChumpTag(name, TYPE_SOUP, ChumpSoup(children)), pair_end
    if ttype == TYPE_INT:
        vals = [
            struct.unpack_from("<i", payload, i)[0]
            for i in range(0, len(payload) - len(payload) % 4, 4)
        ]
        return ChumpTag(name, TYPE_INT, vals), pair_end
    if ttype == TYPE_FLOAT:
        vals_f = [
            struct.unpack_from("<f", payload, i)[0]
            for i in range(0, len(payload) - len(payload) % 4, 4)
        ]
        return ChumpTag(name, TYPE_FLOAT, vals_f), pair_end
    if ttype == TYPE_TEXT:
        text = payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return ChumpTag(name, TYPE_TEXT, text), pair_end
    if ttype == TYPE_NULL:
        return ChumpTag(name, TYPE_NULL, None), pair_end
    if ttype == TYPE_KUID:
        if len(payload) < 8:
            raise ValueError(f"kuid tag {name!r} too short")
        return ChumpTag(name, TYPE_KUID, payload[:8]), pair_end
    # raw / unknown — keep bytes
    return ChumpTag(name, ttype, payload), pair_end


def _encode_tag(tag: ChumpTag) -> bytes:
    name_b = tag.name.encode("utf-8") + b"\x00"
    name_size = len(name_b)  # includes null
    if name_size > 255:
        raise ValueError(f"tag name too long: {tag.name!r}")

    if tag.type == TYPE_SOUP:
        assert isinstance(tag.value, ChumpSoup)
        payload = bytearray()
        for child in tag.value.children:
            payload.extend(_encode_tag(child))
        payload_b = bytes(payload)
    elif tag.type == TYPE_INT:
        assert isinstance(tag.value, list)
        payload_b = b"".join(struct.pack("<i", int(v)) for v in tag.value)
    elif tag.type == TYPE_FLOAT:
        assert isinstance(tag.value, list)
        payload_b = b"".join(struct.pack("<f", float(v)) for v in tag.value)
    elif tag.type == TYPE_TEXT:
        assert isinstance(tag.value, str)
        payload_b = tag.value.encode("utf-8") + b"\x00"
    elif tag.type == TYPE_NULL:
        payload_b = b""
    elif tag.type == TYPE_KUID:
        assert isinstance(tag.value, (bytes, bytearray))
        payload_b = bytes(tag.value[:8])
    else:
        assert isinstance(tag.value, (bytes, bytearray))
        payload_b = bytes(tag.value)

    # pairLength covers: nameSize byte + name+null + type + payload
    # ChumpLib: chunkName.size()+2 + 1 + data  (== name_size + 2 + len(payload))
    pair_len = name_size + 2 + len(payload_b)
    out = bytearray()
    out.extend(struct.pack("<I", pair_len))
    out.append(name_size)
    out.extend(name_b)
    out.append(tag.type & 0xFF)
    out.extend(payload_b)
    return bytes(out)


# ── text export / parse (ChumpLib exportTXT / parseTXT style) ───────────────


def chump_to_text(chump: ChumpFile) -> str:
    lines: list[str] = []
    for i, tag in enumerate(chump.root):
        if tag.type == TYPE_SOUP and i > 0:
            lines.append("")
        _write_text_tag(lines, tag, 0)
    return "\n".join(lines).rstrip() + "\n"


def _pad_name(indent: str, name: str) -> str:
    left = indent + name
    spaces = 40 - len(left)
    if spaces < 2:
        return left + "  "
    return left + (" " * spaces)


def _write_text_tag(lines: list[str], tag: ChumpTag, depth: int) -> None:
    indent = "  " * depth
    if tag.type in (TYPE_NULL, TYPE_RAW):
        return
    if tag.type == TYPE_SOUP:
        assert isinstance(tag.value, ChumpSoup)
        lines.append(indent + tag.name)
        lines.append(indent + "{")
        for child in tag.value.children:
            _write_text_tag(lines, child, depth + 1)
        lines.append(indent + "}")
        return
    prefix = _pad_name(indent, tag.name)
    if tag.type == TYPE_TEXT:
        assert isinstance(tag.value, str)
        lines.append(f'{prefix}"{tag.value}"')
    elif tag.type == TYPE_INT:
        assert isinstance(tag.value, list)
        lines.append(prefix + ",".join(str(int(v)) for v in tag.value))
    elif tag.type == TYPE_FLOAT:
        assert isinstance(tag.value, list)
        parts = []
        for v in tag.value:
            s = f"{float(v):g}"
            if "." not in s and "e" not in s.lower():
                s += ".0"
            parts.append(s)
        lines.append(prefix + ",".join(parts))
    elif tag.type == TYPE_KUID:
        assert isinstance(tag.value, (bytes, bytearray))
        lines.append(prefix + kuid_bin.bytes_to_kuid(bytes(tag.value)))
    else:
        # raw as hex comment — not re-parsed; skip on export for edit safety
        return


_TOKEN_RE = re.compile(
    r'(?:\s*([\w.\-]+)\s+(?:([\w_,.<>:-]+)|"([^"]*)"|(\{))|(\}))(?:$|\n)',
    re.MULTILINE,
)
_INT_RE = re.compile(r"^[-+]?\d+$")
# whole-token float only — do not use `"e" in word` (breaks kind enginespec)
_FLOAT_RE = re.compile(r"^[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$")


def text_to_chump(text: str) -> ChumpFile:
    """Parse ChumpLib-style / config-like text into a ChumpFile."""
    root: list[ChumpTag] = []
    stack: list[list[ChumpTag]] = [root]

    for m in _TOKEN_RE.finditer(text or ""):
        name, bare, quoted, open_brace, close_brace = m.groups()
        if close_brace == "}":
            if len(stack) <= 1:
                raise ValueError("extra '}' in chump text")
            stack.pop()
            continue
        if not name:
            continue
        if open_brace == "{":
            soup = ChumpSoup()
            tag = ChumpTag(name, TYPE_SOUP, soup)
            stack[-1].append(tag)
            stack.append(soup.children)
            continue
        if quoted is not None:
            stack[-1].append(ChumpTag.text(name, quoted))
            continue
        assert bare is not None
        value = bare.strip()
        if value.lower().startswith("<kuid"):
            raw = kuid_bin.parse_kuid_string(value)
            if raw is None:
                raise ValueError(f"bad kuid: {value}")
            stack[-1].append(ChumpTag.kuid(name, raw))
        elif "," in value:
            parts = [p.strip() for p in value.split(",") if p.strip()]
            if all(_INT_RE.match(p) for p in parts):
                stack[-1].append(ChumpTag.integer(name, *(int(p) for p in parts)))
            elif all(_FLOAT_RE.match(p) for p in parts):
                stack[-1].append(ChumpTag.floating(name, *(float(p) for p in parts)))
            else:
                stack[-1].append(ChumpTag.text(name, value))
        elif _FLOAT_RE.match(value):
            stack[-1].append(ChumpTag.floating(name, float(value)))
        elif _INT_RE.match(value):
            stack[-1].append(ChumpTag.integer(name, int(value)))
        else:
            # bare word → text (unquoted)
            stack[-1].append(ChumpTag.text(name, value))

    if len(stack) != 1:
        raise ValueError("unclosed '{' in chump text")
    return ChumpFile(root=root)


def chump_to_config_txt(chump: ChumpFile) -> str:
    """Alias — exported text is editable like config.txt."""
    return chump_to_text(chump)


def convert_config_txt_to_chump(text: str) -> ChumpFile:
    return text_to_chump(text)


def expand_chump_file(path: Path) -> str:
    return chump_to_text(read_chump(path))


def pack_text_to_chump_file(text: str, dest: Path) -> Path:
    return write_chump(dest, text_to_chump(text))
