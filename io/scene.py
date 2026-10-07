"""Scene model: meshes + Trainz attachment points (a.*) + companion .kin clips."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Attachment:
    name: str
    # world-space position (metres, after assimp bake)
    pos: tuple[float, float, float]
    # world-space 3x3 orientation, row-major (identity if unknown)
    orient: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    def axes_end(self, length: float = 0.25) -> tuple[Any, Any, Any]:
        import numpy as np

        m = np.asarray(self.orient, dtype=np.float64).reshape(3, 3)
        o = np.asarray(self.pos, dtype=np.float64)
        return o + m[0] * length, o + m[1] * length, o + m[2] * length


@dataclass
class AnimClip:
    path: Path
    name: str = ""
    frame_count: int = 0
    bone_names: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class MeshPart:
    name: str
    vertices: Any  # (N, 3) float32 ndarray
    indices: Any  # (M,) uint32 triangles flattened
    # optional flat RGB for whole part (used when no albedo)
    color: tuple[float, float, float] = (0.72, 0.74, 0.78)
    normals: Any | None = None  # (N, 3) float32
    uvs: Any | None = None  # (N, 2) float32
    albedo_path: str | None = None  # resolved image path
    albedo_ref: str = ""  # original Trainz / material ref
    normal_path: str | None = None
    normal_ref: str = ""
    parameter_path: str | None = None
    parameter_ref: str = ""
    material_type: str = ""
    mesh_key: str = ""  # owning file name when multiple meshes in one preview
    # Trainz mesh-meta ``two-sided`` — default False; only on when mesh.txt says so.
    two_sided: bool = False
    # tzMF: file offset of the material block that follows this chunk (-1 = none).
    chunk_tail: int = -1


@dataclass
class Scene:
    source: str = ""
    kind: str = ""  # fbx | im | trainzmesh | unknown
    parts: list[MeshPart] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    anims: list[AnimClip] = field(default_factory=list)
    note: str = ""
    # Optional raw .trainzmesh bytes from load — Editor reuses (no third disk read).
    source_bytes: bytes | None = None

    @property
    def vertex_count(self) -> int:
        return int(sum(p.vertices.shape[0] for p in self.parts))

    @property
    def face_count(self) -> int:
        return int(sum(p.indices.shape[0] // 3 for p in self.parts))

    def bounds(self) -> tuple[Any, Any] | None:
        if not self.parts:
            return None
        import numpy as np

        mins = np.min(np.vstack([p.vertices for p in self.parts]), axis=0)
        maxs = np.max(np.vstack([p.vertices for p in self.parts]), axis=0)
        return mins, maxs
