"""Unlimited undo/redo for Mesh Studio edit buffers (tzMF / attachments)."""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field


@dataclass
class EditSnapshot:
    """One restore point. tzmf bytes are zlib-compressed to keep RAM sane."""

    label: str
    tzmf_z: bytes | None  # zlib(bytes) or None
    tzmf_dirty: bool
    atts: list[tuple[str, tuple[float, float, float], tuple[float, ...]]]
    # part preview fields: name, material_type, albedo/normal/parameter refs, color
    parts: list[
        tuple[str, str, str, str, str, tuple[float, float, float]]
    ] = field(default_factory=list)

    @staticmethod
    def pack_tzmf(data: bytes | bytearray | None) -> bytes | None:
        if data is None:
            return None
        return zlib.compress(bytes(data), 6)

    def unpack_tzmf(self) -> bytearray | None:
        if self.tzmf_z is None:
            return None
        return bytearray(zlib.decompress(self.tzmf_z))


class UndoStack:
    """Unlimited undo/redo. Coalesce keeps one baseline per label burst."""

    def __init__(self) -> None:
        self._undo: list[EditSnapshot] = []
        self._redo: list[EditSnapshot] = []

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def push(self, snap: EditSnapshot, *, coalesce: bool = False) -> None:
        if (
            coalesce
            and self._undo
            and not self._redo
            and self._undo[-1].label == snap.label
        ):
            return
        self._undo.append(snap)
        self._redo.clear()

    def undo(self, current: EditSnapshot) -> EditSnapshot | None:
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current: EditSnapshot) -> EditSnapshot | None:
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()

    def depth(self) -> tuple[int, int]:
        return len(self._undo), len(self._redo)
