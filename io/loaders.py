"""Load FBX via assimp CLI; decode trainzmesh via lib.trainzmesh_viewer; .im GEOM/ATCH."""
from __future__ import annotations

import math
import re
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from .anim import scan_kin_files
from .scene import Attachment, MeshPart, Scene
from .tzmf_edit import attachment_floats_ok

# Trainzmesh magic from Naito fixtures (not a public format — detect only).
TRAINZMESH_MAGIC = b"tzMF"


def find_assimp() -> str | None:
    return shutil.which("assimp")


def _has_assimp_dll() -> bool:
    from .assimp_dll import find_assimp_dll

    return find_assimp_dll() is not None


def _mat4_from_text(text: str) -> np.ndarray:
    vals = [float(x) for x in text.split() if x]
    if len(vals) != 16:
        return np.eye(4, dtype=np.float64)
    # assimp dump writes row-major 4x4
    return np.asarray(vals, dtype=np.float64).reshape(4, 4)


def _walk_nodes(
    node: ET.Element,
    parent: np.ndarray,
    attachments: list[Attachment],
) -> None:
    name = node.get("name") or ""
    mat_el = node.find("Matrix4")
    local = _mat4_from_text(mat_el.text or "") if mat_el is not None and mat_el.text else np.eye(4)
    world = parent @ local
    mesh_refs = node.find("MeshRefs")
    has_mesh = mesh_refs is not None and (mesh_refs.get("num") not in (None, "0"))
    # Trainz attachment empties: a.* and no mesh
    if name.startswith("a.") and not has_mesh:
        pos = (float(world[0, 3]), float(world[1, 3]), float(world[2, 3]))
        r = world[:3, :3]
        orient = tuple(float(x) for x in r.reshape(-1))
        attachments.append(Attachment(name=name, pos=pos, orient=orient))
    for child in node.findall("Node"):
        _walk_nodes(child, world, attachments)
    # Nested under NodeList
    for nest in node.findall("NodeList"):
        for child in nest.findall("Node"):
            _walk_nodes(child, world, attachments)


def load_attachments_from_dump(dump_path: Path) -> list[Attachment]:
    tree = ET.parse(dump_path)
    root = tree.getroot()
    scene = root.find("Scene")
    if scene is None:
        return []
    node = scene.find("Node")
    if node is None:
        return []
    out: list[Attachment] = []
    _walk_nodes(node, np.eye(4), out)
    return out


_OBJ_V = re.compile(r"^v\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)")
_OBJ_VT = re.compile(r"^vt\s+([-\d.eE+]+)\s+([-\d.eE+]+)")
_OBJ_VN = re.compile(r"^vn\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)")
_OBJ_F = re.compile(r"^f\s+(.+)$")
_OBJ_O = re.compile(r"^(?:o|g)\s+(.+)$")


def _parse_face_corner(tok: str) -> tuple[int, int | None, int | None]:
    # OBJ is 1-based; missing vt/vn -> None
    parts = tok.split("/")
    vi = int(parts[0]) - 1
    vti = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else None
    vni = int(parts[2]) - 1 if len(parts) > 2 and parts[2] else None
    return vi, vti, vni


def parse_obj(path: Path) -> list[MeshPart]:
    """OBJ reader (v/vt/vn + triangulated f). Groups by o/g. Expands unique corners."""
    positions: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    normals: list[tuple[float, float, float]] = []
    # group -> list of corner triples
    groups: dict[str, list[tuple[int, int | None, int | None]]] = {}
    current = "mesh"
    groups[current] = []

    for line in path.read_text(errors="ignore").splitlines():
        m = _OBJ_V.match(line)
        if m:
            positions.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
            continue
        m = _OBJ_VT.match(line)
        if m:
            texcoords.append((float(m.group(1)), float(m.group(2))))
            continue
        m = _OBJ_VN.match(line)
        if m:
            normals.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
            continue
        m = _OBJ_O.match(line)
        if m:
            current = m.group(1).strip() or "mesh"
            groups.setdefault(current, [])
            continue
        m = _OBJ_F.match(line)
        if not m:
            continue
        toks = m.group(1).split()
        corners = [_parse_face_corner(t) for t in toks]
        if len(corners) < 3:
            continue
        # fan triangulate
        for i in range(1, len(corners) - 1):
            groups[current].extend([corners[0], corners[i], corners[i + 1]])

    palette = [
        (0.72, 0.74, 0.78),
        (0.55, 0.62, 0.70),
        (0.78, 0.70, 0.58),
        (0.58, 0.70, 0.62),
        (0.70, 0.58, 0.66),
    ]
    parts: list[MeshPart] = []
    for i, (name, corners) in enumerate(groups.items()):
        if not corners:
            continue
        # unique (vi,vti,vni) -> compact buffer
        remap: dict[tuple[int, int | None, int | None], int] = {}
        local_v: list[tuple[float, float, float]] = []
        local_uv: list[tuple[float, float]] = []
        local_n: list[tuple[float, float, float]] = []
        idxs: list[int] = []
        for c in corners:
            if c not in remap:
                remap[c] = len(local_v)
                vi, vti, vni = c
                local_v.append(positions[vi])
                if vti is not None and 0 <= vti < len(texcoords):
                    local_uv.append(texcoords[vti])
                else:
                    local_uv.append((0.0, 0.0))
                if vni is not None and 0 <= vni < len(normals):
                    local_n.append(normals[vni])
                else:
                    local_n.append((0.0, 1.0, 0.0))
            idxs.append(remap[c])
        parts.append(
            MeshPart(
                name=name,
                vertices=np.asarray(local_v, dtype=np.float32),
                indices=np.asarray(idxs, dtype=np.uint32),
                normals=np.asarray(local_n, dtype=np.float32),
                uvs=np.asarray(local_uv, dtype=np.float32),
                color=palette[i % len(palette)],
            )
        )
    return parts


def _assimp_export(fbx: Path, out_obj: Path, dump_xml: Path) -> None:
    assimp = find_assimp()
    if not assimp:
        raise RuntimeError(
            "assimp CLI not found on PATH. Install Assimp "
            "(macOS: brew install assimp · Windows: add assimp to PATH)."
        )
    # Export geometry
    r = subprocess.run(
        [assimp, "export", str(fbx), str(out_obj), "-fobj", "-tri"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not out_obj.is_file():
        raise RuntimeError(f"assimp export failed:\n{r.stderr or r.stdout}")
    # Node dump for attachment empties
    r2 = subprocess.run(
        [assimp, "dump", str(fbx), str(dump_xml)],
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0 or not dump_xml.is_file():
        raise RuntimeError(f"assimp dump failed:\n{r2.stderr or r2.stdout}")


def _attach_anims(scene: Scene, mesh_path: Path) -> None:
    anims = scan_kin_files(mesh_path.parent)
    if not anims:
        anims = scan_kin_files(mesh_path.parent.parent)
    scene.anims = anims


def load_fbx(path: Path, *, preview_fast: bool = False) -> Scene:
    path = path.resolve()
    # Prefer bundled Assimp DLL (no PATH). Fall back to assimp CLI.
    if _has_assimp_dll():
        from .assimp_dll import import_fbx_via_dll

        parts, atts = import_fbx_via_dll(path, parse_obj)
    elif find_assimp():
        with tempfile.TemporaryDirectory(prefix="trainz_studio_") as tmp:
            tmp_p = Path(tmp)
            obj = tmp_p / "mesh.obj"
            dump = tmp_p / "dump.xml"
            _assimp_export(path, obj, dump)
            parts = parse_obj(obj)
            atts = load_attachments_from_dump(dump)
    else:
        raise RuntimeError(
            "Assimp not available. Bundled DLL missing and assimp CLI not on PATH.\n"
            "Re-download vendor/assimp (windows-x64 release) or install Assimp CLI."
        )
    if preview_fast:
        atts = []
    # Assimp is Y-up — convert into Trainz Z-up viewport space
    for part in parts:
        part.vertices = _yup_to_zup(part.vertices)
        if part.normals is not None and len(part.normals):
            part.normals = _yup_to_zup(part.normals)
    zup_atts: list[Attachment] = []
    for a in atts:
        px, py, pz = (float(a.pos[0]), float(a.pos[1]), float(a.pos[2]))
        pos = (px, float(-pz), py)
        m = _YUP_TO_ZUP_R @ np.asarray(a.orient, dtype=np.float64).reshape(3, 3)
        zup_atts.append(
            Attachment(name=a.name, pos=pos, orient=tuple(float(v) for v in m.reshape(-1)))
        )
    scene = Scene(
        source=str(path),
        kind="fbx",
        parts=parts,
        attachments=zup_atts,
        note=(
            f"{len(parts)} parts (fast preview)"
            if preview_fast
            else f"{len(parts)} parts, {len(zup_atts)} attachments (a.*)"
        ),
    )
    if not preview_fast:
        _attach_anims(scene, path)
    return scene


def _zup_to_yup(arr) -> np.ndarray:
    """Trainz Z-up → OpenGL Y-up. Kept for tests / HDRI basis helpers."""
    a = np.asarray(arr, dtype=np.float32)
    if a.size == 0:
        return a.reshape(0, 3)
    if a.ndim == 1:
        a = a.reshape(-1, 3)
    return np.column_stack((a[:, 0], a[:, 2], -a[:, 1])).astype(np.float32, copy=False)


def _yup_to_zup(arr) -> np.ndarray:
    """OpenGL/Assimp Y-up → Trainz Z-up (viewport is Z-up)."""
    a = np.asarray(arr, dtype=np.float32)
    if a.size == 0:
        return a.reshape(0, 3)
    if a.ndim == 1:
        a = a.reshape(-1, 3)
    return np.column_stack((a[:, 0], -a[:, 2], a[:, 1])).astype(np.float32, copy=False)


# Assimp/FBX Y-up → Trainz Z-up for attachment bases.
_YUP_TO_ZUP_R = np.asarray(
    ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)), dtype=np.float64
)
_ATT_NAME_RE = re.compile(rb"^a\.[A-Za-z0-9_]+$")


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


def parse_trainzmesh_attachments(data: bytes) -> list[Attachment]:
    """tzMF attachment table: ``u8 len`` + ``a.name`` + 7× BE float32 (pos + quat).

    Positions/orient stay Trainz Z-up (viewport matches PAY / Trainz).
    """
    out: list[Attachment] = []
    n = len(data)
    # Jump via b"a." — byte-walk of multi-MB tzMF was ~1.5s+ with 0 hits.
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
        raw = data[j : j + name_len]
        if not _ATT_NAME_RE.match(raw):
            j += 1
            continue
        after = j + name_len
        px, py, pz, qx, qy, qz, qw = struct.unpack_from(">7f", data, after)
        if not all(math.isfinite(v) for v in (px, py, pz, qx, qy, qz, qw)):
            j += 1
            continue
        if not attachment_floats_ok(px, py, pz, qx, qy, qz, qw):
            j += 1
            continue
        pos = (float(px), float(py), float(pz))
        orient = tuple(float(v) for v in _quat_to_mat3(qx, qy, qz, qw).reshape(-1))
        out.append(Attachment(name=raw.decode("ascii"), pos=pos, orient=orient))
        j = after + 28
        # hop to next length-prefixed a.* within a short pad window
        for k in range(j, min(j + 24, n - 2)):
            L2 = data[k]
            if (
                3 <= L2 <= 64
                and k + 1 + L2 <= n
                and data[k + 1 : k + 3] == b"a."
                and _ATT_NAME_RE.match(data[k + 1 : k + 1 + L2])
            ):
                j = k
                break
    return out


def load_trainzmesh(path: Path, progress=None, *, preview_fast: bool = False) -> Scene:
    path = path.resolve()

    def _p(msg: str, pct: int | None = None) -> None:
        if progress is not None:
            progress(msg, pct)

    _p("Reading header…", 5)
    raw = path.read_bytes()
    head = raw[:4]
    if head != TRAINZMESH_MAGIC:
        return Scene(
            source=str(path),
            kind="trainzmesh",
            note=f"Unrecognized header {head!r}; not a tzMF file.",
        )

    try:
        from ..lib.trainzmesh_viewer.parser import parse_trainzmesh
        from ..lib.trainzmesh_viewer.textures import resolve_texture_path
    except ImportError as e:
        raise RuntimeError(
            f"trainzmesh viewer package missing under trainz_studio.lib:\n{e}"
        ) from e

    _p("Parsing trainzmesh…", 15)
    # Reuse bytes — avoid a second multi-MB disk read inside the parser.
    mesh = parse_trainzmesh(str(path), data=raw)
    from .tzmf_edit import materials_by_tail, parse_materials

    mat_blocks = [] if preview_fast else parse_materials(raw)
    mats_at = materials_by_tail(mat_blocks)
    n_sub = max(len(mesh.submeshes), 1)
    parts: list[MeshPart] = []
    for i, sub in enumerate(mesh.submeshes):
        tail = int(getattr(sub, "tail_off", -1))
        mat = mats_at.get(tail)
        part_name = mat.name if mat is not None else (sub.name or f"mesh_{i}")
        _p(f"Submesh {i + 1}/{n_sub}: {part_name}…", 20 + int(55 * i / n_sub))
        # Keep Trainz Z-up — viewport / axes / Face Orientation match PAY viewer
        pos = np.asarray(sub.positions, dtype=np.float32)
        if pos.ndim == 1:
            pos = pos.reshape(-1, 3)
        has_n = sub.normals is not None and len(sub.normals) > 0
        nrm = (
            np.asarray(sub.normals, dtype=np.float32).reshape(-1, 3)
            if has_n
            else np.zeros_like(pos)
        )
        if preview_fast:
            # solid shade — skip UV/material resolve
            uvs = np.zeros((len(pos), 2), dtype=np.float32)
            parts.append(
                MeshPart(
                    name=part_name,
                    vertices=pos,
                    indices=np.asarray(sub.indices, dtype=np.uint32),
                    normals=nrm,
                    uvs=uvs,
                    chunk_tail=tail,
                )
            )
            continue
        has_uv = sub.uvs is not None and len(sub.uvs) > 0
        uvs = (
            np.asarray(sub.uvs, dtype=np.float32)
            if has_uv
            else np.zeros((len(pos), 2), dtype=np.float32)
        )
        # Parser stores (u, 1-v) for Mac viewer. Undo → Trainz/D3D raw V
        if uvs.size:
            uvs = np.ascontiguousarray(uvs)
            uvs[:, 1] = 1.0 - uvs[:, 1]
        idx = np.asarray(sub.indices, dtype=np.uint32)
        albedo_ref = sub.albedo or ""
        normal_ref = sub.normal_map or ""
        parameter_ref = sub.parameter_map or ""
        mat_type = sub.material_type or ""
        if mat is not None:
            mat_type = mat.type_name or mat_type
            for slot in mat.textures:
                k = slot.key.lower()
                if k == "txalbedo":
                    albedo_ref = slot.value
                elif k == "txnormal":
                    normal_ref = slot.value
                elif k == "txparameters":
                    parameter_ref = slot.value
        albedo = resolve_texture_path(mesh.directory, albedo_ref) if albedo_ref else None
        normal = resolve_texture_path(mesh.directory, normal_ref) if normal_ref else None
        parameter = (
            resolve_texture_path(mesh.directory, parameter_ref) if parameter_ref else None
        )
        parts.append(
            MeshPart(
                name=part_name,
                vertices=pos,
                indices=idx,
                normals=nrm,
                uvs=uvs,
                albedo_path=albedo,
                albedo_ref=albedo_ref,
                normal_path=normal,
                normal_ref=normal_ref,
                parameter_path=parameter,
                parameter_ref=parameter_ref,
                material_type=mat_type,
                chunk_tail=tail,
            )
        )
    if preview_fast:
        note = f"{len(parts)} submeshes (fast preview — mesh only)"
        _p("Geometry ready", 90)
        return Scene(
            source=str(path),
            kind="trainzmesh",
            parts=parts,
            attachments=[],
            note=note,
        )
    _p("Reading a.* attachments…", 78)
    atts = parse_trainzmesh_attachments(raw)
    _p("Scanning animations…", 82)
    warns = "; ".join(mesh.warnings[:2]) if mesh.warnings else ""
    note = f"{len(parts)} submeshes, {len(atts)} attachments (tzMF decode)"
    if warns:
        note = f"{note} — {warns}"
    scene = Scene(
        source=str(path),
        kind="trainzmesh",
        parts=parts,
        attachments=atts,
        note=note,
        source_bytes=raw,
    )
    _attach_anims(scene, path)
    _p("Geometry ready", 90)
    return scene


def load_im_fast(path: Path) -> Scene:
    """Solid mesh for Finder fast preview. No GEOM → a.* gizmos only."""
    from ..lib.im_editor.core import parse_attachments
    from .im_geom import parse_im_parts

    data = path.read_bytes()
    try:
        parts = parse_im_parts(data)
    except ValueError:
        parts = []
    if parts:
        return Scene(
            source=str(path),
            kind="im",
            parts=parts,
            note=f"{len(parts)} chunks (fast preview — mesh only)",
        )
    try:
        atts_raw = parse_attachments(data)
    except ValueError:
        atts_raw = []
    atts = [
        Attachment(name=a.name, pos=tuple(a.pos), orient=tuple(a.orient))  # type: ignore[arg-type]
        for a in atts_raw
    ]
    if not atts:
        raise ValueError("no GEOM or ATCH in this .im")
    return Scene(
        source=str(path),
        kind="im",
        attachments=atts,
        note=f"{len(atts)} attachments (no mesh)",
    )


def load_im_attachments(path: Path) -> Scene:
    """Attachment-only preview for .im (reuses lib.im_editor)."""
    from ..lib.im_editor.core import parse_attachments

    data = path.read_bytes()
    atts_raw = parse_attachments(data)
    atts = [
        Attachment(name=a.name, pos=tuple(a.pos), orient=tuple(a.orient))  # type: ignore[arg-type]
        for a in atts_raw
    ]
    return Scene(
        source=str(path),
        kind="im",
        attachments=atts,
        note=f".im ATCH only — {len(atts)} attachments (mesh geometry not loaded yet)",
    )


def load_any(path: Path, progress=None, *, preview_fast: bool = False) -> Scene:
    path = Path(path)
    suf = path.suffix.lower()

    def _p(msg: str, pct: int | None = None) -> None:
        if progress is not None:
            progress(msg, pct)

    if suf == ".fbx":
        _p("Loading FBX via Assimp…", 20)
        sc = load_fbx(path, preview_fast=preview_fast)
        _p("FBX ready", 90)
        return sc
    if suf == ".trainzmesh":
        return load_trainzmesh(path, progress=progress, preview_fast=preview_fast)
    if suf == ".im":
        if preview_fast:
            _p("Reading .im geometry…", 40)
            sc = load_im_fast(path)
            _p(".im ready", 90)
            return sc
        _p("Reading .im attachments…", 40)
        sc = load_im_attachments(path)
        _p(".im ready", 90)
        return sc
    raise ValueError(f"unsupported extension: {suf}")
