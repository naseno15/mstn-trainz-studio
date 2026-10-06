"""Load Assimp shared library (bundled vendor DLL) for FBX without CLI."""
from __future__ import annotations

import ctypes
import os
import tempfile
from ctypes import POINTER, Structure, byref, c_char_p, c_float, c_uint, c_void_p
from pathlib import Path

import numpy as np

from .scene import Attachment, MeshPart

AI_MAXLEN = 1024
AI_PROCESS_JOIN = 0x2
AI_PROCESS_TRIANGULATE = 0x8
AI_PROCESS_GEN_SMOOTH_NORMALS = 0x40

from .. import PKG_ROOT

_VENDOR = PKG_ROOT / "vendor" / "assimp"
_DLL_CANDIDATES = (
    _VENDOR / "Release" / "assimp-vc143-mt.dll",
    _VENDOR / "assimp-vc143-mt.dll",
    _VENDOR / "assimp.dll",
)

_lib: ctypes.CDLL | None = None


class aiString(Structure):
    _fields_ = [("length", c_uint), ("data", ctypes.c_char * AI_MAXLEN)]


class aiMatrix4x4(Structure):
    _fields_ = [(f"a{r}{c}", c_float) for r in range(1, 5) for c in range(1, 5)]


class aiNode(Structure):
    pass


aiNode._fields_ = [
    ("mName", aiString),
    ("mTransformation", aiMatrix4x4),
    ("mParent", POINTER(aiNode)),
    ("mNumChildren", c_uint),
    ("_pad0", c_uint),  # align pointer on win64 / MSVC
    ("mChildren", POINTER(POINTER(aiNode))),
    ("mNumMeshes", c_uint),
    ("_pad1", c_uint),
    ("mMeshes", POINTER(c_uint)),
    ("mMetaData", c_void_p),
]


class aiScene(Structure):
    _fields_ = [
        ("mFlags", c_uint),
        ("_pad0", c_uint),
        ("mRootNode", POINTER(aiNode)),
        ("mNumMeshes", c_uint),
        # remainder unused — we only need root + export
    ]


def find_assimp_dll() -> Path | None:
    for p in _DLL_CANDIDATES:
        if p.is_file():
            return p
    return None


def _load_lib() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    path = find_assimp_dll()
    if path is None:
        raise RuntimeError(
            "Assimp DLL not found. Expected under trainz_studio/vendor/assimp/."
        )
    os.add_dll_directory(str(path.parent))
    lib = ctypes.CDLL(str(path))
    lib.aiImportFile.argtypes = [c_char_p, c_uint]
    lib.aiImportFile.restype = POINTER(aiScene)
    lib.aiReleaseImport.argtypes = [POINTER(aiScene)]
    lib.aiReleaseImport.restype = None
    lib.aiGetErrorString.argtypes = []
    lib.aiGetErrorString.restype = c_char_p
    lib.aiExportScene.argtypes = [POINTER(aiScene), c_char_p, c_char_p, c_uint]
    lib.aiExportScene.restype = c_uint  # aiReturn
    _lib = lib
    return lib


def _mat4_from_ai(m: aiMatrix4x4) -> np.ndarray:
    # Assimp stores row-major a1..d4
    return np.array(
        [
            [m.a11, m.a12, m.a13, m.a14],
            [m.a21, m.a22, m.a23, m.a24],
            [m.a31, m.a32, m.a33, m.a34],
            [m.a41, m.a42, m.a43, m.a44],
        ],
        dtype=np.float64,
    )


def _node_name(node: aiNode) -> str:
    n = node.mName.length
    raw = bytes(node.mName.data[:n])
    return raw.decode("utf-8", errors="replace")


def _walk_attachments(
    node_ptr: ctypes._Pointer,
    parent: np.ndarray,
    out: list[Attachment],
) -> None:
    if not node_ptr:
        return
    node = node_ptr.contents
    local = _mat4_from_ai(node.mTransformation)
    world = parent @ local
    name = _node_name(node)
    if name.startswith("a.") and node.mNumMeshes == 0:
        pos = (float(world[0, 3]), float(world[1, 3]), float(world[2, 3]))
        r = world[:3, :3]
        orient = tuple(float(x) for x in r.reshape(-1))
        out.append(Attachment(name=name, pos=pos, orient=orient))
    for i in range(node.mNumChildren):
        child = node.mChildren[i]
        _walk_attachments(child, world, out)


def import_fbx_via_dll(path: Path, parse_obj) -> tuple[list[MeshPart], list[Attachment]]:
    """Import FBX with bundled Assimp DLL → OBJ parts + a.* attachments."""
    lib = _load_lib()
    flags = AI_PROCESS_TRIANGULATE | AI_PROCESS_GEN_SMOOTH_NORMALS | AI_PROCESS_JOIN
    scene = lib.aiImportFile(str(path).encode("utf-8"), flags)
    if not scene:
        err = lib.aiGetErrorString() or b"unknown"
        raise RuntimeError(f"assimp import failed: {err.decode(errors='replace')}")
    try:
        atts: list[Attachment] = []
        root = scene.contents.mRootNode
        if root:
            _walk_attachments(root, np.eye(4, dtype=np.float64), atts)
        with tempfile.TemporaryDirectory(prefix="trainz_studio_fbx_") as tmp:
            obj = Path(tmp) / "mesh.obj"
            rc = lib.aiExportScene(scene, b"obj", str(obj).encode("utf-8"), 0)
            if rc != 0 or not obj.is_file():
                err = lib.aiGetErrorString() or b"export failed"
                raise RuntimeError(
                    f"assimp export failed ({rc}): {err.decode(errors='replace')}"
                )
            parts = parse_obj(obj)
        return parts, atts
    finally:
        lib.aiReleaseImport(scene)
