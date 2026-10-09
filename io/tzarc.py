"""Trainz *.tzarc — v1 uncompressed + TRS22 v2 zlib chunks.

Outer header integers are big-endian (TZarchiver / ChumpLib).  
v2 adds an uncompressed-size + per-chunk size table, then zlib payloads
(``stored_size = table_u16 + 1``). Inner directory after inflate matches v1
layout (BE count / sizes).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"TZac"


@dataclass
class TzarcEntry:
    name: str
    size: int
    offset: int  # offset into decompressed (v2) or file (v1) payload blob
    data: bytes | None = None  # filled on extract / open when available


@dataclass
class TzarcIndex:
    path: Path
    version: int
    entries: list[TzarcEntry]
    # Full uncompressed archive body after directory pad (file bytes concatenated)
    _blob: bytes
    _payload_base: int


def _u32(data: bytes, off: int, be: bool) -> tuple[int, int]:
    fmt = ">I" if be else "<I"
    return struct.unpack_from(fmt, data, off)[0], off + 4


def _u64(data: bytes, off: int, be: bool) -> tuple[int, int]:
    fmt = ">Q" if be else "<Q"
    return struct.unpack_from(fmt, data, off)[0], off + 8


def _detect_endian_version(data: bytes) -> tuple[int, bool]:
    """Return (version, big_endian). Prefer BE (Trainz / TZarchiver)."""
    be = struct.unpack_from(">I", data, 4)[0]
    le = struct.unpack_from("<I", data, 4)[0]
    if be in (1, 2):
        return be, True
    if le in (1, 2):
        return le, False
    raise ValueError(f"tzarc version not supported (be={be} le={le})")


def _inflate_v2(data: bytes) -> bytes:
    """Decompress TRS22 tzarc v2 body → inner directory+payloads."""
    unc = struct.unpack_from("<Q", data, 8)[0]
    nchunk = struct.unpack_from("<I", data, 16)[0]
    if nchunk < 1 or nchunk > 1_000_000:
        raise ValueError(f"tzarc v2 bad chunk count: {nchunk}")
    off = 20
    sizes = [struct.unpack_from("<H", data, off + 2 * i)[0] for i in range(nchunk)]
    off = 20 + 2 * nchunk
    parts: list[bytes] = []
    for csize in sizes:
        # Table stores zlib_len - 1 (observed on TRS22 backups).
        take = csize + 1
        if off + take > len(data):
            raise ValueError("tzarc v2 truncated chunk")
        chunk = data[off : off + take]
        off += take
        try:
            parts.append(zlib.decompress(chunk))
        except zlib.error as exc:
            raise ValueError(f"tzarc v2 zlib error: {exc}") from exc
    inner = b"".join(parts)
    if len(inner) != unc:
        raise ValueError(f"tzarc v2 size {len(inner)} != header {unc}")
    return inner


def _parse_directory(blob: bytes, *, be: bool) -> tuple[list[TzarcEntry], int]:
    """Parse count + name/size table + 4-byte pad → entries, payload_base."""
    if len(blob) < 4:
        raise ValueError("tzarc directory truncated")
    count, off = _u32(blob, 0, be)
    if count > 1_000_000:
        raise ValueError(f"tzarc file count ridiculous: {count}")
    names_sizes: list[tuple[str, int]] = []
    for _ in range(count):
        if off >= len(blob):
            raise ValueError("truncated tzarc directory")
        nlen = blob[off]
        off += 1
        name = blob[off : off + nlen].decode("utf-8", errors="replace")
        off += nlen
        size, off = _u64(blob, off, be)
        names_sizes.append((name, int(size)))
    if off + 4 > len(blob):
        raise ValueError("truncated tzarc pad")
    off += 4  # random/time pad
    entries: list[TzarcEntry] = []
    cursor = off
    for name, size in names_sizes:
        entries.append(TzarcEntry(name=name, size=size, offset=cursor))
        cursor += size
    if cursor > len(blob):
        raise ValueError("tzarc payloads overrun blob")
    return entries, off


def open_tzarc(path: Path) -> TzarcIndex:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != MAGIC:
        raise ValueError(f"not a tzarc: {path.name}")
    version, be = _detect_endian_version(data)

    if version == 1:
        # Directory starts at byte 8 (after magic+version); count is first field.
        # Full file bytes from offset 8 form the directory+payload stream.
        blob = data[8:]
        entries, payload_base = _parse_directory(blob, be=be)
        # Remap offsets to absolute file offsets for v1 convenience
        abs_entries = [
            TzarcEntry(name=e.name, size=e.size, offset=e.offset + 8) for e in entries
        ]
        return TzarcIndex(
            path=path,
            version=1,
            entries=abs_entries,
            _blob=data,
            _payload_base=payload_base + 8,
        )

    if version == 2:
        inner = _inflate_v2(data)
        # Inner always BE in TRS22 samples (even if outer version was BE).
        entries, payload_base = _parse_directory(inner, be=True)
        return TzarcIndex(
            path=path,
            version=2,
            entries=entries,
            _blob=inner,
            _payload_base=payload_base,
        )

    raise ValueError(f"tzarc version {version} not supported")


def _parse_directory_head(blob: bytes, *, be: bool) -> tuple[list[TzarcEntry], int] | None:
    """Name table only. Payloads may still be missing, so a short buffer returns None."""
    if len(blob) < 4:
        return None
    count, off = _u32(blob, 0, be)
    if count > 1_000_000:
        return None
    entries: list[TzarcEntry] = []
    cursor_sizes: list[tuple[str, int]] = []
    for _ in range(count):
        if off >= len(blob):
            return None
        nlen = blob[off]
        off += 1
        if off + nlen + 8 > len(blob):
            return None
        name = blob[off : off + nlen].decode("utf-8", errors="replace")
        off += nlen
        size, off = _u64(blob, off, be)
        cursor_sizes.append((name, int(size)))
    if off + 4 > len(blob):
        return None
    off += 4
    cursor = off
    for name, size in cursor_sizes:
        entries.append(TzarcEntry(name=name, size=size, offset=cursor))
        cursor += size
    return entries, off


def _config_entry(entries: list[TzarcEntry]) -> TzarcEntry | None:
    ranked: list[tuple[int, TzarcEntry]] = []
    for ent in entries:
        base = ent.name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        if base == "config.txt":
            ranked.append((0, ent))
        elif base == "config.chump":
            ranked.append((1, ent))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _named_entry(entries: list[TzarcEntry], names: tuple[str, ...]) -> TzarcEntry | None:
    """First archive file that matches a requested name. Earlier names win."""
    wanted = [name.replace("\\", "/").lstrip("/").casefold() for name in names]
    best: tuple[int, TzarcEntry] | None = None
    for ent in entries:
        full = ent.name.replace("\\", "/").lstrip("/").casefold()
        base = full.rsplit("/", 1)[-1]
        for rank, name in enumerate(wanted):
            if full == name or base == name:
                if best is None or rank < best[0]:
                    best = (rank, ent)
                break
    return None if best is None else best[1]


def read_tzarc_named(path: Path, names: tuple[str, ...]) -> bytes:
    """One named file, stopping once that entry is in hand.

    Same early-out as the config reader: a screenshot near the front does not
    pull the texture payloads behind it.
    """
    path = Path(path)
    with path.open("rb") as fh:
        head = fh.read(8)
        if len(head) < 8 or head[:4] != MAGIC:
            raise ValueError(f"not a tzarc: {path.name}")
        version, be = _detect_endian_version(head)
        if version == 1:
            window = bytearray()
            while True:
                block = fh.read(65536)
                window.extend(block)
                parsed = _parse_directory_head(window, be=be)
                if parsed is None:
                    if not block:
                        return b""
                    continue
                hit = _named_entry(parsed[0], names)
                if hit is None:
                    return b""
                fh.seek(8 + hit.offset)
                return fh.read(hit.size)
        if version != 2:
            raise ValueError(f"tzarc version {version} not supported")
        counts = fh.read(12)
        if len(counts) < 12:
            raise ValueError("tzarc v2 header truncated")
        nchunk = struct.unpack_from("<I", counts, 8)[0]
        if nchunk < 1 or nchunk > 1_000_000:
            raise ValueError(f"tzarc v2 bad chunk count: {nchunk}")
        table = fh.read(2 * nchunk)
        if len(table) < 2 * nchunk:
            raise ValueError("tzarc v2 truncated chunk table")
        sizes = [struct.unpack_from("<H", table, 2 * i)[0] for i in range(nchunk)]
        got = bytearray()
        hit: TzarcEntry | None = None
        need = 0
        for csize in sizes:
            left = csize + 1
            dec = zlib.decompressobj()
            try:
                while left > 0:
                    piece = fh.read(min(65536, left))
                    if not piece:
                        raise ValueError("tzarc v2 truncated chunk")
                    left -= len(piece)
                    got.extend(dec.decompress(piece))
                    if hit is None:
                        parsed = _parse_directory_head(got, be=True)
                        if parsed is not None:
                            hit = _named_entry(parsed[0], names)
                            if hit is None:
                                return b""
                            need = hit.offset + hit.size
                    if hit is not None and len(got) >= need:
                        return bytes(got[hit.offset : hit.offset + hit.size])
                got.extend(dec.flush())
            except zlib.error as exc:
                raise ValueError(f"tzarc v2 zlib error: {exc}") from exc
        return b""


def read_tzarc_config(path: Path) -> bytes:
    """config.txt or config.chump bytes, stopping once that entry is in hand.

    TRS22 stores the config at the front of most archives, so this does not
    inflate the texture payloads behind it.
    """
    path = Path(path)
    with path.open("rb") as fh:
        head = fh.read(8)
        if len(head) < 8 or head[:4] != MAGIC:
            raise ValueError(f"not a tzarc: {path.name}")
        version, be = _detect_endian_version(head)
        if version == 1:
            window = bytearray()
            while True:
                block = fh.read(65536)
                window.extend(block)
                parsed = _parse_directory_head(window, be=be)
                if parsed is None:
                    if not block:
                        return b""
                    continue
                cfg = _config_entry(parsed[0])
                if cfg is None:
                    return b""
                fh.seek(8 + cfg.offset)
                return fh.read(cfg.size)
        if version != 2:
            raise ValueError(f"tzarc version {version} not supported")
        counts = fh.read(12)
        if len(counts) < 12:
            raise ValueError("tzarc v2 header truncated")
        nchunk = struct.unpack_from("<I", counts, 8)[0]
        if nchunk < 1 or nchunk > 1_000_000:
            raise ValueError(f"tzarc v2 bad chunk count: {nchunk}")
        table = fh.read(2 * nchunk)
        if len(table) < 2 * nchunk:
            raise ValueError("tzarc v2 truncated chunk table")
        sizes = [struct.unpack_from("<H", table, 2 * i)[0] for i in range(nchunk)]
        got = bytearray()
        cfg: TzarcEntry | None = None
        need = 0
        for csize in sizes:
            left = csize + 1
            dec = zlib.decompressobj()
            try:
                while left > 0:
                    piece = fh.read(min(65536, left))
                    if not piece:
                        raise ValueError("tzarc v2 truncated chunk")
                    left -= len(piece)
                    got.extend(dec.decompress(piece))
                    if cfg is None:
                        parsed = _parse_directory_head(got, be=True)
                        if parsed is not None:
                            cfg = _config_entry(parsed[0])
                            if cfg is None:
                                return b""
                            need = cfg.offset + cfg.size
                    if cfg is not None and len(got) >= need:
                        return bytes(got[cfg.offset : cfg.offset + cfg.size])
                got.extend(dec.flush())
            except zlib.error as exc:
                raise ValueError(f"tzarc v2 zlib error: {exc}") from exc
        return b""


def list_tzarc(path: Path) -> list[str]:
    return [e.name for e in open_tzarc(path).entries]


def extract_tzarc(path: Path, dest: Path) -> list[Path]:
    """Extract all files into dest (keeps relative names / subfolders)."""
    idx = open_tzarc(path)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    blob = idx._blob
    for ent in idx.entries:
        # Normalize Trainz '/' separators for Windows paths
        rel = ent.name.replace("\\", "/").lstrip("/")
        out = dest.joinpath(*rel.split("/")) if rel else dest / "_empty"
        out.parent.mkdir(parents=True, exist_ok=True)
        piece = blob[ent.offset : ent.offset + ent.size]
        if len(piece) != ent.size:
            raise ValueError(f"truncated payload for {ent.name}")
        out.write_bytes(piece)
        written.append(out)
    return written
