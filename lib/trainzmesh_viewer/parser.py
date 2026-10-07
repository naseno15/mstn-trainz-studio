"""tzMF (.trainzmesh) parser — fast path anchored by S0_* format strings."""

from __future__ import annotations

import math
import os
import re
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.lib.stride_tricks import as_strided

# Positions/normals/uvs may be list[tuple] (legacy) or float32 ndarray.
FloatArr = Union[np.ndarray, List[Tuple[float, ...]]]
IndexArr = Union[np.ndarray, List[int]]


@dataclass
class VertexFormat:
    raw: str
    stride: int = 0
    position_offset: int = 0
    normal_offset: int = -1
    uv_offset: int = -1
    tangent_offset: int = -1


@dataclass
class SubMesh:
    name: str
    format: str
    positions: FloatArr
    normals: FloatArr
    uvs: FloatArr
    indices: IndexArr
    albedo: str = ""
    normal_map: str = ""
    parameter_map: str = ""
    material_type: str = ""
    warnings: List[str] = field(default_factory=list)
    # Byte offset where this chunk's material block starts (0 gap in tzMF).
    tail_off: int = -1


@dataclass
class TrainzMesh:
    path: str
    version: int
    submeshes: List[SubMesh]
    warnings: List[str] = field(default_factory=list)

    @property
    def directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.path))


def parse_vertex_format(fmt: str, declared_stride: int = 0) -> VertexFormat:
    result = VertexFormat(raw=fmt)
    payload = fmt.split("_", 1)[1] if "_" in fmt else fmt
    i = 0
    offset = 0
    prefixes = ("BWg", "Tg", "Wi", "T0", "T1", "T2", "T3", "P", "N", "C")

    while i < len(payload):
        prefix = next((p for p in prefixes if payload.startswith(p, i)), "")
        if not prefix:
            break
        j = i + len(prefix)
        digits: List[str] = []
        while j < len(payload) and payload[j].isdigit():
            digits.append(payload[j])
            j += 1
        count = int("".join(digits)) if digits else 1
        typ = ""
        if prefix != "Wi" and j < len(payload) and payload[j] in "fdiIhHsSbB":
            typ = payload[j]
            j += 1

        if typ in {"f", "d"}:
            size = count * (8 if typ == "d" else 4)
        elif prefix == "Wi" and typ == "":
            size = count
        elif typ in {"b", "B"}:
            size = count
        elif typ in {"h", "H", "s", "S"}:
            size = count * 2
        elif typ in {"i", "I"}:
            size = count * 4
        else:
            size = count * 4

        if prefix == "P":
            result.position_offset = offset
        elif prefix == "N" and result.normal_offset < 0:
            result.normal_offset = offset
        elif prefix == "Tg" and result.tangent_offset < 0:
            result.tangent_offset = offset
        elif prefix.startswith("T") and prefix != "Tg" and result.uv_offset < 0:
            result.uv_offset = offset

        offset += size
        i = j

    result.stride = declared_stride or offset
    if declared_stride == 64 and "Wi4" in fmt and "BWg4f" in fmt:
        result.position_offset = 0
        result.normal_offset = 32
        result.tangent_offset = 44
        result.uv_offset = 56
        result.stride = 64
    return result


def find_format_strings(data: bytes) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    seen = set()
    for match in re.finditer(rb"S\d+_[A-Za-z0-9_]+", data):
        start = match.start()
        if start in seen:
            continue
        seen.add(start)
        text = match.group(0).decode("ascii", errors="ignore")
        if "P3f" not in text:
            continue
        out.append((start, match.end(), text))
    return out


def _finite3(v: Tuple[float, float, float]) -> bool:
    return all(math.isfinite(c) and abs(c) < 1e7 for c in v)


def _sample_ok(data: bytes, offset: int, count: int, stride: int, vfmt: VertexFormat) -> bool:
    """Cheap validation using a few vertices only."""
    if count < 3:
        return False
    sample_idx = [0, 1, 2, count // 2, count - 1]
    positions = []
    for i in sample_idx:
        base = offset + i * stride
        if base + stride > len(data):
            return False
        p = struct.unpack_from("<3f", data, base + vfmt.position_offset)
        if not _finite3(p):
            return False
        positions.append(p)
        if vfmt.normal_offset >= 0:
            n = struct.unpack_from("<3f", data, base + vfmt.normal_offset)
            if not _finite3(n):
                return False
        if vfmt.uv_offset >= 0:
            u, v = struct.unpack_from("<2f", data, base + vfmt.uv_offset)
            # Tiled Trainz UVs go well past ±1 (int meshes ~±50). A ±32 clamp
            # dropped the whole chunk, then every later material sat on the
            # wrong geometry. 1e5 still rejects garbage bit patterns.
            if not (math.isfinite(u) and math.isfinite(v) and abs(u) < 1e5 and abs(v) < 1e5):
                return False
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return extent < 1e6


def _indices_ok(data: bytes, offset: int, count: int, size: int, vc: int) -> bool:
    nbytes = count * size
    if offset + nbytes > len(data) or count < 3 or count % 3:
        return False
    fmt = f"<{count}H" if size == 2 else f"<{count}I"
    try:
        indices = struct.unpack_from(fmt, data, offset)
    except struct.error:
        return False
    # spot-check instead of full scan when large
    step = max(1, len(indices) // 2048)
    for i in range(0, len(indices), step):
        if indices[i] >= vc:
            return False
    # always check last triangle
    if max(indices[-3:]) >= vc:
        return False
    return True


def _strided_f32(
    data: bytes, offset: int, count: int, stride: int, field_off: int, ncomp: int
) -> np.ndarray:
    """Copy (count, ncomp) float32 field out of an interleaved vertex buffer."""
    start = offset + field_off
    # last float of last vertex must be inside buffer
    need = (count - 1) * stride + ncomp * 4
    if start < 0 or start + need > len(data) or stride < ncomp * 4:
        raise ValueError("vertex field out of range")
    # frombuffer view starting at field; as_strided walks by byte stride
    total = ((count - 1) * stride + ncomp * 4) // 4
    base = np.frombuffer(data, dtype="<f4", offset=start, count=total)
    return np.ascontiguousarray(as_strided(base, shape=(count, ncomp), strides=(stride, 4)))


def _decode_vertices(
    data: bytes, offset: int, count: int, stride: int, fmt: VertexFormat
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized vertex decode → float32 arrays (uv V flipped for Mac viewer)."""
    positions = _strided_f32(data, offset, count, stride, fmt.position_offset, 3)
    if fmt.normal_offset >= 0:
        normals = _strided_f32(data, offset, count, stride, fmt.normal_offset, 3)
    else:
        normals = np.zeros((count, 3), dtype=np.float32)
        normals[:, 1] = 1.0
    if fmt.uv_offset >= 0:
        uvs = _strided_f32(data, offset, count, stride, fmt.uv_offset, 2)
        uvs[:, 1] = 1.0 - uvs[:, 1]
    else:
        uvs = np.zeros((count, 2), dtype=np.float32)
    return positions, normals, uvs


def _decode_indices(data: bytes, offset: int, count: int, size: int) -> np.ndarray:
    dt = np.dtype("<u2") if size == 2 else np.dtype("<u4")
    return np.frombuffer(data, dtype=dt, count=count, offset=offset).astype(np.uint32, copy=True)


def _extract_le_strings(data: bytes, start: int, end: int) -> List[str]:
    records: List[str] = []
    pos = start
    while pos + 5 <= end:
        n = struct.unpack_from("<I", data, pos)[0]
        if 1 <= n <= 512 and pos + 4 + n <= end:
            raw = data[pos + 4 : pos + 4 + n]
            visible = raw.rstrip(b"\x00")
            if visible and all(32 <= b < 127 for b in visible):
                text = visible.decode("ascii", errors="ignore").strip()
                if text:
                    records.append(text)
                    pos += 4 + n
                    continue
        pos += 1
    return records


_ENV = ("$pbr-env", "txenv", "radiance", "irradiance", "envbrdf")


def _is_env(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _ENV)


def _pick_textures(strings: Sequence[str]) -> Tuple[str, str, str, str]:
    material_type = ""
    albedo = ""
    normal = ""
    parameter = ""
    types = {"stdonetex", "pbrmetal", "pbrmetalmasked", "pbrmetaldetail", "pbrmetalspec"}
    param_labels = {
        "txparameters",
        "txparameter",
        "parameters",
        "parameter",
        "param",
        "txparam",
        "pbrparameter",
        "pbrparameters",
    }
    for i, text in enumerate(strings):
        low = text.lower()
        if low.startswith("m.") or ".m." in low or low in types:
            if not material_type:
                material_type = text
        nxt = strings[i + 1] if i + 1 < len(strings) else ""
        if _is_env(text) or _is_env(nxt):
            continue
        if low in {"txalbedo", "albedo", "txdiffuse", "diffuse", "texture0"} and nxt and not albedo:
            albedo = nxt
        elif low in {"txnormal", "normal", "normalmap"} and nxt and not normal:
            normal = nxt
        elif low in param_labels and nxt and not parameter:
            parameter = nxt
        elif text.endswith((".texture", ".tga", ".png", ".jpg")):
            if "normal" in low or low.endswith("_n.texture") or "_n." in low:
                if not normal:
                    normal = text
            elif (
                "parameter" in low
                or low.endswith("_p.texture")
                or "_p." in low
                or low.endswith("-p.texture")
            ):
                if not parameter and not _is_env(text):
                    parameter = text
            elif not albedo and not _is_env(text):
                albedo = text
    return material_type, albedo, normal, parameter


def _try_decode_chunk(data: bytes, fmt_end: int, fmt_text: str) -> Optional[Tuple[float, SubMesh, int, int]]:
    nominal = fmt_end + 1 if fmt_end < len(data) and data[fmt_end] == 0 else fmt_end
    token_stride = parse_vertex_format(fmt_text).stride
    # Prefer exact + 4-byte aligned offsets; skip wide brute force unless needed.
    count_offsets = list(dict.fromkeys([nominal, (nominal + 3) & ~3, nominal + 4]))

    # Score without decoding verts; decode the winner once at the end.
    best: Optional[dict] = None
    done = False

    for cofs in count_offsets:
        if done or cofs + 12 > len(data):
            continue
        # Structural counts are big-endian in known TRS19 dumps.
        for endian in (">", "<"):
            if done:
                break
            vc, ic_raw, stride = struct.unpack_from(endian + "III", data, cofs)
            if not (3 <= vc <= 2_000_000):
                continue
            if not (12 <= stride <= 512 and stride % 4 == 0):
                continue
            if token_stride and token_stride > stride:
                continue
            vfmt = parse_vertex_format(fmt_text, stride)
            if vfmt.position_offset + 12 > stride:
                continue
            if vfmt.uv_offset >= 0 and vfmt.uv_offset + 8 > stride:
                continue
            if vfmt.normal_offset >= 0 and vfmt.normal_offset + 12 > stride:
                continue

            vertex_offset = cofs + 12
            vertex_bytes = vc * stride
            if vertex_offset + vertex_bytes > len(data):
                continue
            if not _sample_ok(data, vertex_offset, vc, stride, vfmt):
                continue

            base_index = vertex_offset + vertex_bytes
            candidates = [ic_raw]
            if 0 < ic_raw * 3 <= 6_000_000:
                candidates.append(ic_raw * 3)

            for index_count in candidates:
                if done or index_count < 3 or index_count % 3:
                    continue
                for index_size in (2, 4):
                    if index_size == 2 and vc > 65535:
                        continue
                    iofs = base_index
                    if not _indices_ok(data, iofs, index_count, index_size, vc):
                        iofs2 = (base_index + 3) & ~3
                        if iofs2 == iofs or not _indices_ok(data, iofs2, index_count, index_size, vc):
                            continue
                        iofs = iofs2

                    score = 20.0
                    if endian == ">":
                        score += 15.0
                    if token_stride and stride == token_stride:
                        score += 10.0
                    if index_size == 2:
                        score += 3.0

                    tail_start = iofs + index_count * index_size
                    strings = _extract_le_strings(data, tail_start, min(len(data), tail_start + 4096))
                    mat_type, albedo, normal, parameter = _pick_textures(strings)
                    if albedo or mat_type:
                        score += 12.0

                    if best is None or score > best["score"]:
                        best = {
                            "score": score,
                            "vertex_offset": vertex_offset,
                            "vc": vc,
                            "stride": stride,
                            "vfmt": vfmt,
                            "iofs": iofs,
                            "index_count": index_count,
                            "index_size": index_size,
                            "endian": endian,
                            "tail_start": tail_start,
                            "mat_type": mat_type,
                            "albedo": albedo,
                            "normal": normal,
                            "parameter": parameter,
                        }

                    # First strong BE + matching stride hit is good enough.
                    if endian == ">" and token_stride == stride and score >= 45:
                        done = True
                        break

    if best is None:
        return None

    positions, normals, uvs = _decode_vertices(
        data, best["vertex_offset"], best["vc"], best["stride"], best["vfmt"]
    )
    indices = _decode_indices(data, best["iofs"], best["index_count"], best["index_size"])
    mesh = SubMesh(
        name="mesh",
        format=fmt_text,
        positions=positions,
        normals=normals,
        uvs=uvs,
        indices=indices,
        albedo=best["albedo"],
        normal_map=best["normal"],
        parameter_map=best["parameter"],
        material_type=best["mat_type"],
        warnings=[
            f"format={fmt_text} verts={best['vc']} indices={best['index_count']} "
            f"stride={best['stride']} endian={best['endian']} score={best['score']:.1f}"
        ],
    )
    return (best["score"], mesh, best["vertex_offset"], best["tail_start"])


def parse_trainzmesh(path: str, data: Optional[bytes] = None) -> TrainzMesh:
    if data is None:
        with open(path, "rb") as f:
            data = f.read()
    if len(data) < 20 or data[:4] != b"tzMF":
        raise ValueError(f"Not a tzMF .trainzmesh file: {path}")

    version = struct.unpack_from(">I", data, 4)[0]
    f1, f2, f3 = struct.unpack_from(">III", data, 8)
    warnings = [f"tzMF version={version} fields=({f1},{f2},{f3})"]

    format_records = find_format_strings(data)
    if not format_records:
        raise ValueError("No S0_* vertex-format strings found in file")

    # field3 is usually mesh/submesh count; field1 is often attachment/node related.
    limit = f3 if 0 < f3 < 10_000 else (f1 if 0 < f1 < 10_000 else 0)
    submeshes: List[SubMesh] = []
    seen: List[Tuple[int, int]] = []

    for _fmt_start, fmt_end, fmt_text in format_records:
        decoded = _try_decode_chunk(data, fmt_end, fmt_text)
        if not decoded:
            continue
        _score, mesh, start, end = decoded
        if any(not (end <= a or start >= b) for a, b in seen):
            continue
        seen.append((start, end))
        mesh.name = f"mesh_{len(submeshes)}"
        mesh.tail_off = end
        submeshes.append(mesh)
        if limit and len(submeshes) >= limit:
            break

    if not submeshes:
        raise ValueError("Failed to decode any tzMF vertex/index buffers")
    if limit and len(submeshes) != limit:
        warnings.append(f"Declared ~{limit} submesh(es), decoded {len(submeshes)}")

    return TrainzMesh(path=path, version=version, submeshes=submeshes, warnings=warnings)
