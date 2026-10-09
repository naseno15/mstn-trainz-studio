"""Solid-mesh decode for Trainz JIRF .im (GEOM chunks). Fast preview only.

Layout matches indexed-mesh exporters (GEOM 101–201): header, then
position+UV vertices, uint16 indices, vertex normals. Textures and a.*
are left to Mesh Studio.
"""
from __future__ import annotations

import struct

import numpy as np

from ..lib.im_editor.core import parse_chunks
from .scene import MeshPart

_VERTS_OK = {12, 20, 28, 36}  # pos, +1..3 uv sets


def _u32(data: bytes, p: int) -> tuple[int, int]:
    return struct.unpack_from("<I", data, p)[0], p + 4


def _f32(data: bytes, p: int) -> tuple[float, int]:
    return struct.unpack_from("<f", data, p)[0], p + 4


def _skip_jet(data: bytes, p: int, end: int) -> int:
    n, p = _u32(data, p)
    if n > 1_048_576 or p + n > end:
        raise ValueError("jet string overruns chunk")
    return p + n


def _jet_name(data: bytes, p: int, end: int) -> tuple[str, int]:
    n, p = _u32(data, p)
    if n > 4096 or p + n > end:
        raise ValueError("material name overruns chunk")
    raw = data[p : p + n]
    name = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    return name, p + n


def _iter_chunks(data: bytes, start: int, end: int):
    off = start
    while off + 8 <= end:
        tag = data[off : off + 4]
        if not tag.isalnum():
            break
        size = struct.unpack_from("<I", data, off + 4)[0]
        body = off + 8
        if body + size > end:
            break
        yield tag, body, size
        off = body + size


def _mat_name(data: bytes, body: int, size: int) -> str:
    end = body + size
    if size < 8:
        return ""
    ver, p = _u32(data, body)
    if ver < 102 or p + 4 > end:
        return ""
    try:
        name, _p = _jet_name(data, p, end)
    except ValueError:
        return ""
    return name


def _fit_vertex_block(
    remaining: int,
    nverts: int,
    nidx: int,
    nface: int,
    want_tangents: bool,
) -> tuple[int, int]:
    """(bytes per vertex, index width). Prefer 16-bit indices."""
    if nverts <= 0:
        raise ValueError("GEOM has no vertices")
    tangent_opts = (True, False) if want_tangents else (False,)
    face_opts = (nface, 0) if nface else (0,)
    for idx_w in (2, 4):
        for faces in face_opts:
            for tangents in tangent_opts:
                tail = nidx * idx_w + nverts * 12 + faces * 12
                if tangents:
                    tail += nverts * 12
                room = remaining - tail
                if room < nverts * 12 or room % nverts != 0:
                    continue
                stride = room // nverts
                if stride in _VERTS_OK:
                    return stride, idx_w
    raise ValueError("GEOM vertex block does not match header counts")


def _parse_geom(data: bytes, body: int, size: int, name: str) -> MeshPart:
    end = body + size
    ver, p = _u32(data, body)
    if ver < 100 or ver > 201:
        raise ValueError(f"unsupported GEOM version {ver}")
    flags = 4
    use_tangents = 0
    if ver >= 101:
        flags, p = _u32(data, p)
    if ver >= 201:
        use_tangents, p = _u32(data, p)
    _area, p = _f32(data, p)
    nverts, p = _u32(data, p)
    nprims, p = _u32(data, p)
    nidx = nprims * (2 if flags == 2 else 3)
    nface = 0
    if ver >= 101:
        nidx, p = _u32(data, p)
        nface, p = _u32(data, p)
    if ver in (103, 104):
        _sets, p = _u32(data, p)
    if ver >= 102:
        _max_inf, p = _u32(data, p)
    if ver >= 200:
        p = _skip_jet(data, p, end)
    if flags not in (0, 4):
        raise ValueError(f"GEOM primitive flags {flags} are not triangles")
    if nverts > 2_000_000 or nidx > 6_000_000 or nidx % 3 != 0:
        raise ValueError("GEOM counts out of range")
    stride, idx_w = _fit_vertex_block(
        end - p, nverts, nidx, nface, bool(use_tangents)
    )
    vert_bytes = nverts * stride
    raw = np.frombuffer(data[p : p + vert_bytes], dtype=np.float32)
    comps = stride // 4
    grid = raw.reshape(nverts, comps)
    positions = np.ascontiguousarray(grid[:, :3])
    p += vert_bytes
    idx_bytes = nidx * idx_w
    if idx_w == 2:
        indices = np.frombuffer(data[p : p + idx_bytes], dtype="<u2").astype(np.uint32)
    else:
        indices = np.frombuffer(data[p : p + idx_bytes], dtype="<u4").copy()
    p += idx_bytes
    if int(indices.max(initial=0)) >= nverts:
        raise ValueError("GEOM index out of range")
    normals = np.zeros((nverts, 3), dtype=np.float32)
    if p + nverts * 12 <= end:
        normals = np.frombuffer(data[p : p + nverts * 12], dtype=np.float32).reshape(nverts, 3).copy()
    return MeshPart(
        name=name or "mesh",
        vertices=positions,
        indices=indices,
        normals=normals,
        uvs=np.zeros((nverts, 2), dtype=np.float32),
    )


def parse_im_parts(data: bytes) -> list[MeshPart]:
    """Triangle parts from every GEOM chunk. Raises if none decode."""
    parts: list[MeshPart] = []
    errors: list[str] = []
    for tag, body, size in parse_chunks(data):
        if tag != b"CHNK":
            continue
        nested_at = body + 8 if size >= 8 else body
        mat = ""
        for ntag, nbody, nsize in _iter_chunks(data, nested_at, body + size):
            if ntag == b"MATL":
                mat = _mat_name(data, nbody, nsize) or mat
            elif ntag == b"GEOM":
                try:
                    parts.append(_parse_geom(data, nbody, nsize, mat or f"chunk_{len(parts)}"))
                except ValueError as exc:
                    errors.append(str(exc))
    if parts:
        return parts
    if errors:
        raise ValueError(errors[0])
    raise ValueError("no GEOM chunk in this .im")
