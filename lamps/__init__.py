"""Cabin / onetex lamp simulation — one cast light per bulb part + surface glow."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from ..io.scene import MeshPart, Scene
from ..io.texture import texture_stem

# fluorescent orange default (warm tube)
DEFAULT_LAMP_COLOR: tuple[float, float, float] = (1.0, 0.62, 0.22)
MAX_LAMPS = 64


def glow_key(mesh_key: str, stem: str) -> str:
    """Surface glow id — shared by all parts using the same texture stem."""
    return f"{mesh_key}::{stem}" if mesh_key else stem


def lamp_uid(mesh_key: str, part_id: str) -> str:
    return f"{mesh_key}||{part_id}" if mesh_key else part_id


# name hints when material_type is missing
_LAMP_NAME_HINTS = (
    "light",
    "lamp",
    "lumen",
    "cabin_l",
    "cab_l",
    "interior_l",
    "illum",
    "emiss",
    "bulb",
    "neon",
    "kuay",  # lightkuay family
)


@dataclass
class Lamp:
    """One cast light at a bulb island — glow still keyed by texture stem."""

    stem: str
    label: str = ""
    enabled: bool = False  # off until user enables (no glow/cast at load)
    color: tuple[float, float, float] = DEFAULT_LAMP_COLOR
    brightness: float = 0.5
    mode: str = "omni"  # omni | spot | wide
    cone_deg: float = 40.0
    range_m: float = 0.3
    pos: tuple[float, float, float] = (0.0, 1.0, 0.0)
    dir: tuple[float, float, float] = (0.0, -1.0, 0.0)
    auto: bool = True
    mesh_key: str = ""
    part_id: str = ""  # unique per bulb island

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.part_id or self.stem
        if not self.part_id:
            self.part_id = self.stem


def is_onetex_type(material_type: str) -> bool:
    mt = (material_type or "").lower()
    return "onetex" in mt or "stdonetex" in mt


def looks_like_lamp_stem(stem: str) -> bool:
    s = (stem or "").lower()
    return any(h in s for h in _LAMP_NAME_HINTS)


def part_is_lamp(part: MeshPart, stem: str) -> str | None:
    """Only real light textures — not every StdOneTex (status/sticker/etc)."""
    name = part.name or ""
    if not (looks_like_lamp_stem(stem) or looks_like_lamp_stem(name)):
        return None
    if is_onetex_type(part.material_type):
        return "onetex"
    return "hint"


def part_centroid(part: MeshPart) -> tuple[float, float, float]:
    anchors = island_light_positions(part)
    return anchors[0] if anchors else (0.0, 1.0, 0.0)


def _under_island(
    part: MeshPart,
    vert_ids: np.ndarray,
) -> np.ndarray:
    """Cast point under the island: XZ at center, Y at lowest verts (+ slight drop)."""
    pts = part.vertices[vert_ids].astype(np.float64, copy=False)
    c = pts.mean(axis=0)
    y_bot = float(pts[:, 1].min())
    # ponytail: 3 cm under mesh so fill reads as ceiling lamp, not side glow
    return np.array([c[0], y_bot - 0.03, c[2]], dtype=np.float64)


def island_light_positions(part: MeshPart) -> list[tuple[float, float, float]]:
    """One cast point per face-disconnected island, under that island.

    Face-connected tris only — never spatially merge separate islands.
    Position = island XZ center at lowest Y (slightly below the mesh).
    """
    v = part.vertices
    if v is None or v.size == 0 or part.indices.size < 3:
        return [(0.0, 1.0, 0.0)]
    v = v.astype(np.float64, copy=False)
    idx = part.indices.astype(np.int64, copy=False).reshape(-1, 3)
    n_tris = int(idx.shape[0])
    if n_tris <= 0:
        c = np.mean(v, axis=0)
        return [(float(c[0]), float(c[1] - 0.03), float(c[2]))]
    # Single triangle: one cast (still run island math for under-point).
    if n_tris == 1:
        vids = np.unique(idx.reshape(-1))
        c = _under_island(part, vids)
        return [(float(c[0]), float(c[1]), float(c[2]))]

    # Vectorized edge keys → union-find (pure-Python edge dict was open-time jank).
    a = idx[:, 0]
    b = idx[:, 1]
    c = idx[:, 2]
    e0 = np.minimum(a, b)
    e1 = np.maximum(a, b)
    e2 = np.minimum(b, c)
    e3 = np.maximum(b, c)
    e4 = np.minimum(c, a)
    e5 = np.maximum(c, a)
    # pack edge (u,v) into uint64; tri index pairs for adjacency
    vmax = int(v.shape[0]) + 1
    pack = (e0.astype(np.int64) * vmax + e1).astype(np.int64)
    pack2 = (e2.astype(np.int64) * vmax + e3).astype(np.int64)
    pack3 = (e4.astype(np.int64) * vmax + e5).astype(np.int64)
    all_pack = np.concatenate([pack, pack2, pack3])
    all_tri = np.concatenate(
        [
            np.arange(n_tris, dtype=np.int64),
            np.arange(n_tris, dtype=np.int64),
            np.arange(n_tris, dtype=np.int64),
        ]
    )
    order = np.argsort(all_pack, kind="mergesort")
    all_pack = all_pack[order]
    all_tri = all_tri[order]

    parent = np.arange(n_tris, dtype=np.int64)

    def find(x: int) -> int:
        # path compression iterative
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = int(parent[x])
        return x

    def union(ra: int, rb: int) -> None:
        if ra != rb:
            parent[rb] = ra

    # Same packed edge → adjacent tris share a face edge
    i = 0
    n_e = int(all_pack.shape[0])
    while i < n_e:
        j = i + 1
        key = all_pack[i]
        while j < n_e and all_pack[j] == key:
            j += 1
        if j - i >= 2:
            root = find(int(all_tri[i]))
            for k in range(i + 1, j):
                union(root, find(int(all_tri[k])))
                root = find(root)
        i = j

    roots = np.empty(n_tris, dtype=np.int64)
    for ti in range(n_tris):
        roots[ti] = find(ti)

    out: list[tuple[float, float, float]] = []
    for root in np.unique(roots):
        tri_list = np.nonzero(roots == root)[0]
        tris = idx[tri_list]
        vids = np.unique(tris.reshape(-1))
        c = _under_island(part, vids)
        out.append((float(c[0]), float(c[1]), float(c[2])))

    out.sort(key=lambda p: (p[2], p[0], p[1]))
    return out


def sample_albedo_rgb(path: str | None) -> tuple[float, float, float] | None:
    """Average albedo color biased to bright pixels (for cast tint)."""
    if not path:
        return None
    pp = Path(path)
    if not pp.is_file():
        return None
    try:
        from PIL import Image

        im = Image.open(pp).convert("RGB").resize((12, 12), Image.Resampling.BILINEAR)
        arr = np.asarray(im, dtype=np.float32) / 255.0
        lum = arr.mean(axis=2)
        w = np.clip(lum * lum, 0.02, None)
        c = (arr * w[..., None]).sum(axis=(0, 1)) / float(w.sum())
        c = np.clip(c * 1.15, 0.15, 1.0)
        return (float(c[0]), float(c[1]), float(c[2]))
    except Exception:
        return None


def _make_part_id(part: MeshPart, index: int, stem: str) -> str:
    base = (part.name or stem or "lamp").strip() or "lamp"
    return f"{index}:{base}"


def discover_lamps(scene: Scene) -> list[Lamp]:
    """One cast light per disconnected bulb island (not one average for the texture)."""
    lamps: list[Lamp] = []
    for i, part in enumerate(scene.parts):
        ref = part.albedo_ref or part.name or ""
        stem = texture_stem(ref) or texture_stem(part.name) or part.name or "part"
        if not stem:
            continue
        kind = part_is_lamp(part, stem)
        if not kind:
            continue
        mk = part.mesh_key or ""
        tint = DEFAULT_LAMP_COLOR
        base = _make_part_id(part, i, stem)
        anchors = island_light_positions(part)
        for j, pos in enumerate(anchors):
            if len(lamps) >= MAX_LAMPS:
                break
            part_id = base if len(anchors) == 1 else f"{base}#{j}"
            label = part.name or stem
            if len(anchors) > 1:
                label = f"{label} [{j + 1}/{len(anchors)}]"
            if mk:
                label = f"{label} @ {mk}"
            lamps.append(
                Lamp(
                    stem=stem,
                    mesh_key=mk,
                    part_id=part_id,
                    label=label,
                    enabled=False,
                    color=tint,
                    pos=pos,
                    auto=True,
                    brightness=0.5,
                    mode="omni",
                    range_m=0.3,
                )
            )
        if len(lamps) >= MAX_LAMPS:
            break
    lamps.sort(key=lambda L: (L.mesh_key.lower(), L.part_id.lower()))
    return lamps[:MAX_LAMPS]


def merge_lamps(existing: list[Lamp], discovered: list[Lamp]) -> list[Lamp]:
    """Keep user edits; refresh positions; drop vanished auto lamps."""
    by = {lamp_uid(L.mesh_key, L.part_id): L for L in existing}
    out: list[Lamp] = []
    seen: set[str] = set()
    for d in discovered:
        key = lamp_uid(d.mesh_key, d.part_id)
        seen.add(key)
        if key in by:
            old = by[key]
            old.pos = d.pos
            old.label = d.label or old.label
            old.mesh_key = d.mesh_key
            old.stem = d.stem or old.stem
            old.part_id = d.part_id
            # keep user color / brightness / range
            out.append(old)
        else:
            out.append(d)
    for key, old in by.items():
        if key in seen:
            continue
        if not old.auto:
            out.append(old)
    return out[:MAX_LAMPS]


def lamps_from_stem(
    stem: str,
    scene: Scene,
    *,
    color: tuple[float, float, float] = DEFAULT_LAMP_COLOR,
    mesh_key: str = "",
) -> list[Lamp]:
    """Create one lamp per island of each matching part."""
    out: list[Lamp] = []
    for i, part in enumerate(scene.parts):
        if mesh_key and (part.mesh_key or "") != mesh_key:
            continue
        ref = part.albedo_ref or part.name or ""
        pstem = texture_stem(ref) or texture_stem(part.name) or ""
        if pstem != stem and texture_stem(part.name) != stem:
            continue
        mk = part.mesh_key or mesh_key
        tint = color
        base = _make_part_id(part, i, stem)
        anchors = island_light_positions(part)
        for j, pos in enumerate(anchors):
            if len(out) >= MAX_LAMPS:
                break
            part_id = base if len(anchors) == 1 else f"{base}#{j}"
            label = part.name or stem
            if len(anchors) > 1:
                label = f"{label} [{j + 1}/{len(anchors)}]"
            if mk:
                label = f"{label} @ {mk}"
            out.append(
                Lamp(
                    stem=stem,
                    mesh_key=mk,
                    part_id=part_id,
                    label=label,
                    enabled=False,
                    color=tint,
                    pos=pos,
                    auto=False,
                    brightness=0.5,
                    mode="omni",
                    range_m=0.3,
                )
            )
    if not out:
        out.append(
            Lamp(
                stem=stem,
                mesh_key=mesh_key,
                part_id=f"manual:{stem}",
                label=stem + (f" @ {mesh_key}" if mesh_key else ""),
                enabled=False,
                color=color,
                auto=False,
                brightness=0.5,
                mode="omni",
                range_m=0.3,
            )
        )
    return out[:MAX_LAMPS]


def lamp_from_stem(
    stem: str,
    scene: Scene,
    *,
    color: tuple[float, float, float] = DEFAULT_LAMP_COLOR,
    mesh_key: str = "",
) -> Lamp:
    """Back-compat: first lamp from lamps_from_stem."""
    return lamps_from_stem(stem, scene, color=color, mesh_key=mesh_key)[0]


def pack_for_gpu(lamps: Iterable[Lamp], *, cast: bool = True) -> dict:
    """Glow by texture stem; cast = one omni per lamp part position."""
    pos = np.zeros((MAX_LAMPS, 3), dtype=np.float32)
    col = np.zeros((MAX_LAMPS, 3), dtype=np.float32)
    power = np.zeros(MAX_LAMPS, dtype=np.float32)
    range_m = np.zeros(MAX_LAMPS, dtype=np.float32)
    mode = np.zeros(MAX_LAMPS, dtype=np.float32)
    direction = np.zeros((MAX_LAMPS, 3), dtype=np.float32)
    cone = np.zeros(MAX_LAMPS, dtype=np.float32)
    glow: dict[str, float] = {}

    n = 0
    for L in lamps:
        if not L.enabled or L.brightness <= 1e-4:
            continue
        # surface glow (texture self-illum) — stronger so tubes look lit, not only cast dots
        g = glow_key(L.mesh_key, L.stem)
        glow[g] = max(glow.get(g, 0.0), min(8.0, float(L.brightness) * 3.5 + 0.35))
        if not cast:
            continue
        if n >= MAX_LAMPS:
            break
        pos[n] = L.pos
        col[n] = L.color
        mul = 1.5 if L.mode == "wide" else 1.0
        power[n] = float(L.brightness) * mul * 2.2
        range_m[n] = max(0.05, float(L.range_m)) * (1.35 if L.mode == "wide" else 1.0)
        mode[n] = 2.0 if L.mode == "spot" else 1.0
        d = np.asarray(L.dir, dtype=np.float64)
        dn = float(np.linalg.norm(d)) or 1.0
        direction[n] = (d / dn).astype(np.float32)
        half = max(5.0, min(80.0, float(L.cone_deg))) * 0.5
        cone[n] = float(np.cos(np.radians(half)))
        n += 1

    return {
        "count": n,
        "pos": pos,
        "col": col,
        "power": power,
        "range": range_m,
        "mode": mode,
        "dir": direction,
        "cone": cone,
        "glow": glow,
    }


def empty_lamp_pack() -> dict:
    return pack_for_gpu([])


def merge_lamp_packs(base: dict, extra: dict, *, max_n: int = MAX_LAMPS) -> dict:
    """Append extra cast lights + glow onto base (Mat pick preview, etc.)."""
    out = {
        "pos": np.array(base["pos"], copy=True),
        "col": np.array(base["col"], copy=True),
        "power": np.array(base["power"], copy=True),
        "range": np.array(base["range"], copy=True),
        "mode": np.array(base["mode"], copy=True),
        "dir": np.array(base["dir"], copy=True),
        "cone": np.array(base["cone"], copy=True),
        "glow": dict(base.get("glow") or {}),
    }
    n = int(base.get("count", 0))
    en = int(extra.get("count", 0))
    for i in range(en):
        if n >= max_n:
            break
        out["pos"][n] = extra["pos"][i]
        out["col"][n] = extra["col"][i]
        out["power"][n] = extra["power"][i]
        out["range"][n] = extra["range"][i]
        out["mode"][n] = extra["mode"][i]
        out["dir"][n] = extra["dir"][i]
        out["cone"][n] = extra["cone"][i]
        n += 1
    for k, v in (extra.get("glow") or {}).items():
        out["glow"][k] = max(float(out["glow"].get(k, 0.0)), float(v))
    out["count"] = n
    return out


def lamps_to_json(lamps: list[Lamp]) -> list[dict]:
    return [asdict(L) for L in lamps]
