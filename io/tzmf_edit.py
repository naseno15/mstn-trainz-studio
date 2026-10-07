"""tzMF (.trainzmesh) material + attachment patch helpers.

Clean-room layout from live TRS19 dumps (MeshEditor-compatible):

Material block (after mesh indices):
  le_str(type) le_str(name)
  u32=0, u8=1, 4×BE float RGBA (material color), BE u32 tex_count
  (le_str(key) le_str(value)) × tex_count
  u32=3
  le_str(\"matEmissive\")  u32=7,u16=1, 4×LE float RGBA
  le_str(\"matSpecular\")  u32=7,u16=1, 4×LE float RGBA
  le_str(\"specPower\")    8 zero-ish bytes + LE float

Attachment record:
  u8 name_len, ascii name, 7×BE float32 (pos Z-up + quat xyzw)
"""
from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ATT_NAME_RE = re.compile(rb"^a\.[A-Za-z0-9_./+-]+$")
_MAT_TYPES = (
    b"pbrmetal",
    b"pbrmetalmasked",
    b"pbrmetaldetail",
    b"pbrmetalspec",
    b"stdonetex",
    b"glass",
    b"clutter",
    b"foliage",
)

# Same basis change as loaders.parse_trainzmesh_attachments
_ZUP_TO_YUP_R = np.asarray(
    ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)), dtype=np.float64
)
_YUP_TO_ZUP_R = _ZUP_TO_YUP_R.T


def _read_le_str(data: bytes | bytearray, pos: int) -> tuple[str | None, int]:
    if pos + 4 > len(data):
        return None, pos
    n = struct.unpack_from("<I", data, pos)[0]
    if not (1 <= n <= 512) or pos + 4 + n > len(data):
        return None, pos
    raw = bytes(data[pos + 4 : pos + 4 + n])
    if not raw.endswith(b"\x00"):
        return None, pos
    body = raw[:-1]
    if not body or not all(32 <= b < 127 for b in body):
        return None, pos
    return body.decode("ascii"), pos + 4 + n


def _le_str_bytes(text: str) -> bytes:
    raw = text.encode("ascii") + b"\x00"
    return struct.pack("<I", len(raw)) + raw


def _quat_to_mat3(x: float, y: float, z: float, w: float) -> np.ndarray:
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.asarray(
        (
            (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)),
            (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)),
            (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)),
        ),
        dtype=np.float64,
    )


def _mat3_to_quat(m: np.ndarray) -> tuple[float, float, float, float]:
    """Row-major 3×3 → unit quaternion (xyzw)."""
    m = np.asarray(m, dtype=np.float64).reshape(3, 3)
    tr = float(m[0, 0] + m[1, 1] + m[2, 2])
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.asarray((x, y, z, w), dtype=np.float64)
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    q /= n
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def yup_pos_to_zup(pos: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = pos
    return (float(x), float(-z), float(y))


def zup_pos_to_yup(pos: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = pos
    return (float(x), float(z), float(-y))


def yup_orient_to_zup_quat(
    orient: tuple[float, ...]
) -> tuple[float, float, float, float]:
    m_yup = np.asarray(orient, dtype=np.float64).reshape(3, 3)
    m_zup = _YUP_TO_ZUP_R @ m_yup
    return _mat3_to_quat(m_zup)


def zup_quat_to_yup_orient(
    qx: float, qy: float, qz: float, qw: float
) -> tuple[float, ...]:
    m_yup = _ZUP_TO_YUP_R @ _quat_to_mat3(qx, qy, qz, qw)
    return tuple(float(v) for v in m_yup.reshape(-1))


@dataclass
class TexSlot:
    key: str
    value: str
    key_off: int
    value_off: int


@dataclass
class MatBlock:
    type_name: str
    name: str
    type_off: int
    name_off: int
    color_off: int
    color: tuple[float, float, float, float]
    textures: list[TexSlot] = field(default_factory=list)
    emissive_off: int = -1
    emissive: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    specular_off: int = -1
    specular: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
    spec_power_off: int = -1
    spec_power: float = 25.0
    end_off: int = 0
    vertex_format: str = ""


@dataclass
class AttRecord:
    name: str
    name_off: int
    floats_off: int
    pos_zup: tuple[float, float, float]
    quat_zup: tuple[float, float, float, float]

    @property
    def pos_yup(self) -> tuple[float, float, float]:
        return zup_pos_to_yup(self.pos_zup)

    @property
    def orient_yup(self) -> tuple[float, ...]:
        qx, qy, qz, qw = self.quat_zup
        return zup_quat_to_yup_orient(qx, qy, qz, qw)


def materials_by_tail(mats: list[MatBlock]) -> dict[int, MatBlock]:
    """Map chunk-tail offset → material. The block starts at the geometry tail (gap 0).

    List index is not chunk index: unnamed chunks sit between named ones, so
    ``mats[i]`` is often the next piece of geometry.
    """
    return {int(m.type_off): m for m in mats}


def parse_materials(data: bytes | bytearray) -> list[MatBlock]:
    """Locate MeshEditor-style material blocks by type + ``*.m.*`` name."""
    out: list[MatBlock] = []
    pos = 0
    while True:
        found: tuple[int, bytes] | None = None
        for t in _MAT_TYPES:
            rec = struct.pack("<I", len(t) + 1) + t + b"\x00"
            i = data.find(rec, pos)
            if i >= 0 and (found is None or i < found[0]):
                found = (i, t)
        if found is None:
            break
        i, _t = found
        mat_type, after_type = _read_le_str(data, i)
        name_off = after_type
        mat_name, p = _read_le_str(data, name_off)
        if not mat_type or not mat_name or ".m." not in mat_name:
            pos = i + 1
            continue
        if p + 25 > len(data) or data[p : p + 4] != b"\x00\x00\x00\x00" or data[p + 4] != 1:
            pos = i + 1
            continue
        color = struct.unpack_from(">4f", data, p + 5)
        count = struct.unpack_from(">I", data, p + 21)[0]
        if not (0 < count <= 32):
            pos = i + 1
            continue
        color_off = p + 5
        p = p + 25
        textures: list[TexSlot] = []
        ok = True
        for _ in range(count):
            k_off = p
            key, p = _read_le_str(data, p)
            v_off = p
            val, p = _read_le_str(data, p)
            if key is None or val is None:
                ok = False
                break
            textures.append(TexSlot(key=key, value=val, key_off=k_off, value_off=v_off))
        if not ok:
            pos = i + 1
            continue
        # color props trailer: u32=3 then named props
        emissive_off = specular_off = spec_power_off = -1
        emissive = (0.0, 0.0, 0.0, 1.0)
        specular = (0.8, 0.8, 0.8, 1.0)
        spec_power = 25.0
        # BE u32=3 then named color props (LE strings + LE floats)
        if p + 4 <= len(data) and struct.unpack_from(">I", data, p)[0] == 3:
            p += 4
            for _ in range(4):
                key, p2 = _read_le_str(data, p)
                if key is None:
                    break
                if key in ("matEmissive", "matSpecular") and data[p2 : p2 + 6] == b"\x07\x00\x00\x00\x00\x01":
                    rgba = struct.unpack_from("<4f", data, p2 + 6)
                    if key == "matEmissive":
                        emissive_off = p2 + 6
                        emissive = rgba
                    else:
                        specular_off = p2 + 6
                        specular = rgba
                    p = p2 + 22
                elif key == "specPower" and data[p2 : p2 + 6] == b"\x00\x00\x00\x00\x00\x01":
                    # same 6-byte tag as color props; LE float follows
                    spec_power = struct.unpack_from("<f", data, p2 + 6)[0]
                    spec_power_off = p2 + 6
                    p = p2 + 10
                    break
                else:
                    break
        # Vertex Format: S0_* lives in the geometry chunk before this material
        vfmt = ""
        # memoryview — avoid copying up to 2MB per material
        window = memoryview(data)[max(0, i - 2_000_000) : i]
        for m in re.finditer(rb"S\d+_[A-Za-z0-9_]+", window):
            text = m.group(0).decode("ascii", errors="ignore")
            if "P3f" in text:
                vfmt = text
        out.append(
            MatBlock(
                type_name=mat_type,
                name=mat_name,
                type_off=i,
                name_off=name_off,
                color_off=color_off,
                color=color,
                textures=textures,
                emissive_off=emissive_off,
                emissive=emissive,
                specular_off=specular_off,
                specular=specular,
                spec_power_off=spec_power_off,
                spec_power=float(spec_power),
                end_off=p,
                vertex_format=vfmt,
            )
        )
        pos = i + 1
    return out


def parse_attachment_records(data: bytes | bytearray) -> list[AttRecord]:
    out: list[AttRecord] = []
    n = len(data)
    # Jump via b"a." (same fast path as loaders.parse_trainzmesh_attachments).
    needle = b"a."
    j = 0
    while True:
        j = data.find(needle, j)
        if j < 1 or j + 1 + 28 > n:
            break
        name_len = data[j - 1]
        if not (3 <= name_len <= 64) or j - 1 + 1 + name_len + 28 > n:
            j += 1
            continue
        raw = bytes(data[j : j + name_len])
        if not _ATT_NAME_RE.match(raw):
            j += 1
            continue
        after = j + name_len
        vals = struct.unpack_from(">7f", data, after)
        if not all(math.isfinite(v) for v in vals):
            j += 1
            continue
        px, py, pz, qx, qy, qz, qw = vals
        out.append(
            AttRecord(
                name=raw.decode("ascii"),
                name_off=j - 1,
                floats_off=after,
                pos_zup=(float(px), float(py), float(pz)),
                quat_zup=(float(qx), float(qy), float(qz), float(qw)),
            )
        )
        j = after + 28
        for k in range(j, min(j + 24, n - 2)):
            L2 = data[k]
            if (
                3 <= L2 <= 64
                and k + 1 + L2 <= n
                and data[k + 1 : k + 3] == b"a."
                and _ATT_NAME_RE.match(bytes(data[k + 1 : k + 1 + L2]))
            ):
                j = k
                break
    return out


def _splice(data: bytearray, start: int, end: int, replacement: bytes) -> bytearray:
    return bytearray(data[:start] + replacement + data[end:])


def replace_le_string(data: bytearray, str_off: int, new_text: str) -> bytearray:
    """Replace a length-prefixed LE string at ``str_off`` (may change file size)."""
    old, end = _read_le_str(data, str_off)
    if old is None:
        raise ValueError(f"no LE string at {str_off}")
    return _splice(data, str_off, end, _le_str_bytes(new_text))


def set_be_rgba(data: bytearray, off: int, rgba: tuple[float, float, float, float]) -> None:
    struct.pack_into(">4f", data, off, *[float(c) for c in rgba])


def set_le_rgba(data: bytearray, off: int, rgba: tuple[float, float, float, float]) -> None:
    struct.pack_into("<4f", data, off, *[float(c) for c in rgba])


def set_le_float(data: bytearray, off: int, value: float) -> None:
    struct.pack_into("<f", data, off, float(value))


def zup_quat_to_orient(
    qx: float, qy: float, qz: float, qw: float
) -> tuple[float, ...]:
    """File/Z-up quaternion → 3×3 row-major orient (viewport Z-up)."""
    return tuple(float(v) for v in _quat_to_mat3(qx, qy, qz, qw).reshape(-1))


def set_attachment_yup(
    data: bytearray,
    rec: AttRecord,
    *,
    pos_yup: tuple[float, float, float] | None = None,
    pos_zup: tuple[float, float, float] | None = None,
    quat_yup: tuple[float, float, float, float] | None = None,
    orient_yup: tuple[float, ...] | None = None,
) -> None:
    """Patch 7×BE floats for one attachment (name length unchanged)."""
    px, py, pz = rec.pos_zup
    qx, qy, qz, qw = rec.quat_zup
    if pos_zup is not None:
        px, py, pz = (float(pos_zup[0]), float(pos_zup[1]), float(pos_zup[2]))
    elif pos_yup is not None:
        px, py, pz = yup_pos_to_zup(pos_yup)
    if quat_yup is not None:
        # MeshEditor / Scene show file Z-up quat values directly.
        qx, qy, qz, qw = quat_yup
    if orient_yup is not None:
        qx, qy, qz, qw = yup_orient_to_zup_quat(orient_yup)
    struct.pack_into(">7f", data, rec.floats_off, px, py, pz, qx, qy, qz, qw)


def rename_attachment(data: bytearray, rec: AttRecord, new_name: str) -> bytearray:
    """Rename attachment; rebuilds the u8-len + name prefix (may shift file)."""
    if not new_name.startswith("a.") or not re.match(r"^a\.[A-Za-z0-9_./+-]+$", new_name):
        raise ValueError(f"invalid attachment name: {new_name}")
    old_end = rec.floats_off  # name region is [name_off, floats_off)
    new_raw = new_name.encode("ascii")
    if len(new_raw) > 64:
        raise ValueError("attachment name too long")
    replacement = bytes([len(new_raw)]) + new_raw
    return _splice(data, rec.name_off, old_end, replacement)


def apply_material_edits(
    data: bytearray,
    mat: MatBlock,
    *,
    type_name: str | None = None,
    name: str | None = None,
    color: tuple[float, float, float, float] | None = None,
    emissive: tuple[float, float, float, float] | None = None,
    specular: tuple[float, float, float, float] | None = None,
    spec_power: float | None = None,
    textures: dict[str, str] | None = None,
) -> bytearray:
    """Apply material field edits. String renames applied high→low offset."""
    # floats first (stable offsets)
    if color is not None:
        set_be_rgba(data, mat.color_off, color)
    if emissive is not None and mat.emissive_off >= 0:
        set_le_rgba(data, mat.emissive_off, emissive)
    if specular is not None and mat.specular_off >= 0:
        set_le_rgba(data, mat.specular_off, specular)
    if spec_power is not None and mat.spec_power_off >= 0:
        set_le_float(data, mat.spec_power_off, spec_power)

    # string patches from the end so earlier offsets stay valid
    patches: list[tuple[int, str]] = []
    if textures:
        for slot in mat.textures:
            if slot.key in textures and textures[slot.key] != slot.value:
                patches.append((slot.value_off, textures[slot.key]))
    if name is not None and name != mat.name:
        patches.append((mat.name_off, name))
    if type_name is not None and type_name != mat.type_name:
        patches.append((mat.type_off, type_name))
    patches.sort(key=lambda x: x[0], reverse=True)
    for off, text in patches:
        data = replace_le_string(data, off, text)
    return data


def write_trainzmesh(
    path: Path,
    data: bytes | bytearray,
    *,
    backup: bool = True,
) -> Path:
    path = Path(path)
    if backup and path.is_file():
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.is_file():
            bak.write_bytes(path.read_bytes())
    path.write_bytes(bytes(data))
    return path


def rgba01_to_bytes255(rgba: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(max(0, min(255, int(round(c * 255.0)))) for c in rgba)  # type: ignore[return-value]


def bytes255_to_rgba01(rgba: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    return tuple(max(0.0, min(1.0, c / 255.0)) for c in rgba)  # type: ignore[return-value]
