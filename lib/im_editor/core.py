"""Trainz .im ATCH (attachment) read/write — same layout as IM-Editor / BlenderIMExporter."""
from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

IDENTITY_ORIENT = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

# trainz_studio/lib/im_editor → repo root (trs22/)
REPO_ROOT = Path(__file__).resolve().parents[3]
CAB_DEFAULT = (
    REPO_ROOT
    / "editing"
    / "kuid 1190880 100078 MSTN KIHA _ ______40"
    / "cab.im"
)


@dataclass
class Attachment:
    name: str
    orient: tuple[float, ...]  # 9 floats, row-major 3x3
    pos: tuple[float, float, float]

    def clone(self) -> Attachment:
        return Attachment(self.name, tuple(self.orient), tuple(self.pos))


def jet_decode(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8")


def jet_encode(name: str) -> bytes:
    enc = name.encode("utf-8")
    pad = (4 - len(enc) % 4) % 4
    body = enc + (b"\0" * pad)
    return struct.pack("<I", len(body)) + body


def parse_chunks(data: bytes) -> list[tuple[bytes, int, int]]:
    """[(tag, body_start, body_size), ...] inside IDXM."""
    if data[:4] != b"JIRF":
        raise ValueError("not a JIRF/.im file")
    jirf_size = struct.unpack_from("<I", data, 4)[0]
    if jirf_size != len(data) - 8:
        raise ValueError(f"JIRF size mismatch: header={jirf_size} file-8={len(data) - 8}")
    if data[8:12] != b"IDXM":
        raise ValueError("missing IDXM")
    out: list[tuple[bytes, int, int]] = []
    off = 12
    while off < len(data):
        tag = data[off : off + 4]
        size = struct.unpack_from("<I", data, off + 4)[0]
        body = off + 8
        out.append((tag, body, size))
        off = body + size
    if off != len(data):
        raise ValueError("chunk walk did not end at EOF")
    return out


def parse_attachments(data: bytes) -> list[Attachment]:
    atch = next((c for c in parse_chunks(data) if c[0] == b"ATCH"), None)
    if atch is None:
        raise ValueError("no ATCH chunk in this .im")
    _, body, size = atch
    ver, count = struct.unpack_from("<II", data, body)
    if ver != 100:
        raise ValueError(f"unsupported ATCH version {ver}")
    p = body + 8
    end = body + size
    atts: list[Attachment] = []
    for _ in range(count):
        nlen = struct.unpack_from("<I", data, p)[0]
        p += 4
        raw = data[p : p + nlen]
        p += nlen
        name = jet_decode(raw)
        orient = struct.unpack_from("<9f", data, p)
        p += 36
        pos = struct.unpack_from("<3f", data, p)
        p += 12
        atts.append(Attachment(name, orient, pos))
    if p != end:
        raise ValueError(f"ATCH parse overrun: {p} != {end}")
    return atts


def build_atch_payload(atts: list[Attachment]) -> bytes:
    payload = bytearray()
    payload += struct.pack("<II", 100, len(atts))
    for a in atts:
        payload += jet_encode(a.name)
        payload += struct.pack("<9f", *a.orient)
        payload += struct.pack("<3f", *a.pos)
    return bytes(payload)


def rebuild_im(base: bytes, atts: list[Attachment]) -> bytes:
    """Replace ATCH in base .im bytes; keep other chunks."""
    chunks = parse_chunks(base)
    atch = next((c for c in chunks if c[0] == b"ATCH"), None)
    if atch is None:
        raise ValueError("no ATCH chunk to replace")
    _, body, size = atch
    tag_off = body - 8
    payload = build_atch_payload(atts)
    out = bytearray()
    out += base[:tag_off]
    out += b"ATCH"
    out += struct.pack("<I", len(payload))
    out += payload
    out += base[body + size :]
    struct.pack_into("<I", out, 4, len(out) - 8)
    parse_attachments(bytes(out))  # validate
    return bytes(out)


def backup_once(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)
    return bak


def snapshot_atts(atts: list[Attachment]) -> list[Attachment]:
    return [a.clone() for a in atts]


class ImDocument:
    """In-memory .im with undo/redo over attachment list."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.base: bytes = b""
        self.opened_atts: list[Attachment] = []
        self.atts: list[Attachment] = []
        self._undo: list[list[Attachment]] = []
        self._redo: list[list[Attachment]] = []
        self.dirty = False

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def open(self, path: Path) -> None:
        data = path.read_bytes()
        atts = parse_attachments(data)
        self.path = path
        self.base = data
        self.opened_atts = snapshot_atts(atts)
        self.atts = snapshot_atts(atts)
        self._undo.clear()
        self._redo.clear()
        self.dirty = False

    def _push_undo(self) -> None:
        self._undo.append(snapshot_atts(self.atts))
        self._redo.clear()
        if len(self._undo) > 64:
            self._undo.pop(0)

    def apply_atts(self, new_atts: list[Attachment], *, record: bool = True) -> None:
        if record:
            self._push_undo()
        self.atts = snapshot_atts(new_atts)
        self.dirty = True

    def update_one(
        self,
        index: int,
        *,
        name: str | None = None,
        pos: tuple[float, float, float] | None = None,
        orient: tuple[float, ...] | None = None,
    ) -> None:
        if index < 0 or index >= len(self.atts):
            raise IndexError("attachment index out of range")
        self._push_undo()
        a = self.atts[index].clone()
        if name is not None:
            a.name = name
        if pos is not None:
            a.pos = pos
        if orient is not None:
            if len(orient) != 9:
                raise ValueError("orient needs 9 floats")
            a.orient = tuple(orient)
        self.atts[index] = a
        self.dirty = True

    def nudge(self, index: int, dx: float, dy: float, dz: float) -> None:
        a = self.atts[index]
        self.update_one(index, pos=(a.pos[0] + dx, a.pos[1] + dy, a.pos[2] + dz))

    def add(
        self,
        name: str,
        pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
        orient: tuple[float, ...] = IDENTITY_ORIENT,
    ) -> int:
        """Append attachment; returns new index. Name must be unique."""
        name = name.strip()
        if not name:
            raise ValueError("name cannot be empty")
        if any(a.name == name for a in self.atts):
            raise ValueError(f"name already used: {name}")
        if len(orient) != 9:
            raise ValueError("orient needs 9 floats")
        new_atts = snapshot_atts(self.atts)
        new_atts.append(Attachment(name, tuple(orient), pos))
        self.apply_atts(new_atts)
        return len(self.atts) - 1

    def remove(self, index: int) -> None:
        if index < 0 or index >= len(self.atts):
            raise IndexError("attachment index out of range")
        new_atts = snapshot_atts(self.atts)
        del new_atts[index]
        self.apply_atts(new_atts)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(snapshot_atts(self.atts))
        self.atts = self._undo.pop()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(snapshot_atts(self.atts))
        self.atts = self._redo.pop()
        self.dirty = True
        return True

    def revert_opened(self) -> None:
        """Back to state at last Open (or last successful Save baseline)."""
        self._push_undo()
        self.atts = snapshot_atts(self.opened_atts)
        self.dirty = False

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save")
        out = rebuild_im(self.base, self.atts)
        backup_once(target)
        target.write_bytes(out)
        self.path = target
        self.base = out
        self.opened_atts = snapshot_atts(self.atts)
        self.dirty = False
        return target


def selfcheck(path: Path | None = None) -> str:
    path = path or CAB_DEFAULT
    if not path.is_file():
        raise FileNotFoundError(f"missing .im: {path}")
    data = path.read_bytes()
    atts = parse_attachments(data)
    chunks = parse_chunks(data)
    _, body, size = next(c for c in chunks if c[0] == b"ATCH")
    payload = build_atch_payload(atts)
    if payload != data[body : body + size]:
        raise AssertionError("ATCH rewrite != original")
    rebuilt = rebuild_im(data, atts)
    if rebuilt != data:
        raise AssertionError("full rebuild != original")
    return f"ok: {path.name} ATCH count={len(atts)} roundtrip identical"
