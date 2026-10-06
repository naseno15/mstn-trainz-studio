"""Path-traced cabin lamp bake → albedo + parameter (CUDA via CuPy when available).

Not Blender Cycles — NEE soft lamps + short diffuse GI + contact AO (all meshes
occlude each other in one BVH) + A-Trous denoise.
Writes sidecars under ``<mesh_dir>/baked_lamps/`` (never overwrites sources).
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import Lamp, glow_key, pack_for_gpu, part_is_lamp
from ..io.scene import MeshPart, Scene
from ..io.texture import material_family, texture_stem

ProgressCb = Callable[[str, int, int, float], None]  # stage, done, total, eta_sec


QUALITY = {
    "draft": dict(
        spp_direct=24, spp_gi=6, bounces=1, max_res=512, lamp_radius=0.05,
        ao_spp=12, ao_radius=0.40, ao_strength=0.55,
    ),
    "high": dict(
        spp_direct=96, spp_gi=24, bounces=2, max_res=1024, lamp_radius=0.032,
        ao_spp=32, ao_radius=0.65, ao_strength=0.75,
    ),
    "production": dict(
        spp_direct=192, spp_gi=48, bounces=2, max_res=2048, lamp_radius=0.022,
        ao_spp=64, ao_radius=0.85, ao_strength=0.85,
    ),
}


@dataclass
class BakeSettings:
    quality: str = "high"
    spp_direct: int = 96
    spp_gi: int = 24
    bounces: int = 2
    max_res: int = 1024
    lamp_radius: float = 0.032
    ambient: float = 0.08
    albedo_scale: float = 1.12
    emissive_scale: float = 0.90
    denoise: bool = True
    prefer_cuda: bool = True
    # contact / grounding — all meshes in BVH occlude each other
    ao_spp: int = 32
    ao_radius: float = 0.65
    ao_strength: float = 0.75

    @classmethod
    def from_quality(cls, name: str, **overrides) -> BakeSettings:
        q = QUALITY.get(name, QUALITY["high"])
        return cls(quality=name, **{**q, **overrides})


@dataclass
class BakeIssue:
    level: str  # error | warn | info
    message: str


@dataclass
class BakeResult:
    out_dir: Path
    written: list[Path] = field(default_factory=list)
    issues: list[BakeIssue] = field(default_factory=list)
    backend: str = "cpu"
    seconds: float = 0.0
    cancelled: bool = False


def cuda_available() -> bool:
    try:
        import cupy as cp  # noqa: F401

        return bool(cp.cuda.is_available())
    except Exception:
        return False


def _load_rgba_f32(path: str | None, tw: int, th: int) -> np.ndarray:
    """RGBA float32 HxWx4; missing → mid-grey opaque."""
    from PIL import Image

    if path and Path(path).is_file():
        im = Image.open(path).convert("RGBA")
        if im.size != (tw, th):
            im = im.resize((tw, th), Image.Resampling.BILINEAR)
        arr = np.asarray(im, dtype=np.float32) / 255.0
        return arr
    out = np.full((th, tw, 4), 0.72, dtype=np.float32)
    out[..., 3] = 1.0
    return out


def _save_rgba(path: Path, rgba: np.ndarray) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    u8 = np.clip(np.round(rgba * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(u8, "RGBA").save(path)


def _write_texture_txt(path: Path, primary: str, usage: str) -> None:
    path.write_text(
        f"Primary={primary}\n"
        f"AlphaHint=opaque\n"
        f"Tile=st\n"
        f"UsageHint={usage}\n"
        f"Compression=dxt5\n",
        encoding="utf-8",
    )


# ── triangle soup + BVH ──────────────────────────────────────


@dataclass
class WorldMesh:
    v0: np.ndarray  # (T,3) f32
    v1: np.ndarray
    v2: np.ndarray
    n0: np.ndarray
    n1: np.ndarray
    n2: np.ndarray
    albedo: np.ndarray  # (T,3) average part albedo (for GI)
    emissive: np.ndarray  # (T,) lamp surface strength


def _part_face_arrays(part: MeshPart) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    v = part.vertices
    if v is None or v.size == 0 or part.indices.size < 3:
        return None
    idx = part.indices.astype(np.int64).reshape(-1, 3)
    v0 = v[idx[:, 0]].astype(np.float32)
    v1 = v[idx[:, 1]].astype(np.float32)
    v2 = v[idx[:, 2]].astype(np.float32)
    if part.normals is not None and part.normals.shape[0] == v.shape[0]:
        n = part.normals.astype(np.float32)
        n0, n1, n2 = n[idx[:, 0]], n[idx[:, 1]], n[idx[:, 2]]
    else:
        e1 = v1 - v0
        e2 = v2 - v0
        fn = np.cross(e1, e2)
        ln = np.linalg.norm(fn, axis=1, keepdims=True)
        fn = np.where(ln > 1e-12, fn / np.maximum(ln, 1e-12), np.array([[0, 1, 0]], dtype=np.float32))
        n0 = n1 = n2 = fn.astype(np.float32)
    return v0, v1, v2, (n0, n1, n2)


def build_world(scene: Scene, lamps: list[Lamp]) -> WorldMesh:
    glow = pack_for_gpu(lamps, cast=True)["glow"]
    chunks: list[tuple] = []
    for part in scene.parts:
        got = _part_face_arrays(part)
        if got is None:
            continue
        v0, v1, v2, (n0, n1, n2) = got
        t = v0.shape[0]
        col = np.array(part.color, dtype=np.float32)
        alb = np.broadcast_to(col, (t, 3)).copy()
        stem = texture_stem(part.albedo_ref or part.name or "") or ""
        gk = glow_key(part.mesh_key, stem)
        em = float(glow.get(gk, 0.0))
        if part_is_lamp(part, stem):
            em = max(em, 1.5)
        chunks.append((v0, v1, v2, n0, n1, n2, alb, np.full(t, em, dtype=np.float32)))
    if not chunks:
        z = np.zeros((0, 3), dtype=np.float32)
        return WorldMesh(z, z, z, z, z, z, z, np.zeros(0, dtype=np.float32))
    return WorldMesh(
        v0=np.concatenate([c[0] for c in chunks]),
        v1=np.concatenate([c[1] for c in chunks]),
        v2=np.concatenate([c[2] for c in chunks]),
        n0=np.concatenate([c[3] for c in chunks]),
        n1=np.concatenate([c[4] for c in chunks]),
        n2=np.concatenate([c[5] for c in chunks]),
        albedo=np.concatenate([c[6] for c in chunks]),
        emissive=np.concatenate([c[7] for c in chunks]),
    )


@dataclass
class BVH:
    """Flat BVH: node = bmin(3), bmax(3), left, right  (right<0 ⇒ leaf, -right-1=count, left=tri0)."""

    nodes: np.ndarray  # (N, 8) f32 — last two stored as float bit-cast of int32
    tri_order: np.ndarray  # (T,) i32


def _bbox_tris(v0, v1, v2, order: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = v0[order]
    b = v1[order]
    c = v2[order]
    bmin = np.minimum(np.minimum(a, b), c).min(axis=0)
    bmax = np.maximum(np.maximum(a, b), c).max(axis=0)
    return bmin.astype(np.float32), bmax.astype(np.float32)


def build_bvh(world: WorldMesh, leaf_size: int = 8) -> BVH:
    t = int(world.v0.shape[0])
    if t == 0:
        return BVH(np.zeros((0, 8), dtype=np.float32), np.zeros(0, dtype=np.int32))
    order = np.arange(t, dtype=np.int32)
    centroids = ((world.v0 + world.v1 + world.v2) / 3.0).astype(np.float32)
    nodes: list[np.ndarray] = []
    leaf_tris: list[tuple[int, np.ndarray]] = []

    def pack(bmin, bmax, left: int, right: int) -> np.ndarray:
        row = np.zeros(8, dtype=np.float32)
        row[0:3] = bmin
        row[3:6] = bmax
        row[6] = np.array([left], dtype=np.int32).view(np.float32)[0]
        row[7] = np.array([right], dtype=np.int32).view(np.float32)[0]
        return row

    def recurse(idx: np.ndarray) -> int:
        bmin, bmax = _bbox_tris(world.v0, world.v1, world.v2, idx)
        node_i = len(nodes)
        nodes.append(np.zeros(8, dtype=np.float32))
        if idx.size <= leaf_size:
            leaf_tris.append((node_i, idx.copy()))
            nodes[node_i] = pack(bmin, bmax, -1, -int(idx.size) - 1)
            return node_i
        extent = bmax - bmin
        axis = int(np.argmax(extent))
        vals = centroids[idx, axis]
        mid = max(1, idx.size // 2)
        part = np.argpartition(vals, mid - 1)
        left_idx = idx[part[:mid]]
        right_idx = idx[part[mid:]]
        if left_idx.size == 0 or right_idx.size == 0:
            leaf_tris.append((node_i, idx.copy()))
            nodes[node_i] = pack(bmin, bmax, -1, -int(idx.size) - 1)
            return node_i
        li = recurse(left_idx)
        ri = recurse(right_idx)
        nodes[node_i] = pack(bmin, bmax, li, ri)
        return node_i

    recurse(order)
    tri_order_list: list[int] = []
    for node_i, idxs in leaf_tris:
        start = len(tri_order_list)
        tri_order_list.extend(int(x) for x in idxs)
        bmin = nodes[node_i][0:3].copy()
        bmax = nodes[node_i][3:6].copy()
        nodes[node_i] = pack(bmin, bmax, start, -len(idxs) - 1)
    return BVH(np.stack(nodes, axis=0), np.asarray(tri_order_list, dtype=np.int32))

def _as_int(x: np.float32) -> int:
    return int(np.asarray(x, dtype=np.float32).view(np.int32))


def _ray_tri(orig, dir, v0, v1, v2) -> tuple[float, float, float]:
    """Möller–Trumbore → (t, u, v) or t=inf."""
    eps = 1e-7
    e1 = v1 - v0
    e2 = v2 - v0
    pvec = np.cross(dir, e2)
    det = float(np.dot(e1, pvec))
    if abs(det) < eps:
        return math.inf, 0.0, 0.0
    inv = 1.0 / det
    tvec = orig - v0
    u = float(np.dot(tvec, pvec)) * inv
    if u < 0.0 or u > 1.0:
        return math.inf, 0.0, 0.0
    qvec = np.cross(tvec, e1)
    v = float(np.dot(dir, qvec)) * inv
    if v < 0.0 or u + v > 1.0:
        return math.inf, 0.0, 0.0
    t = float(np.dot(e2, qvec)) * inv
    if t <= eps:
        return math.inf, 0.0, 0.0
    return t, u, v


def _ray_aabb(orig, inv_dir, bmin, bmax) -> bool:
    t0 = (bmin - orig) * inv_dir
    t1 = (bmax - orig) * inv_dir
    tmin = np.minimum(t0, t1)
    tmax = np.maximum(t0, t1)
    t_enter = float(np.max(tmin))
    t_exit = float(np.min(tmax))
    return t_exit >= max(t_enter, 0.0)


def closest_hit(
    orig: np.ndarray,
    dir: np.ndarray,
    world: WorldMesh,
    bvh: BVH,
    t_max: float = 1e30,
) -> tuple[float, int, float, float]:
    """Return (t, tri, u, v) or (inf, -1, 0, 0)."""
    if bvh.nodes.size == 0:
        return math.inf, -1, 0.0, 0.0
    inv = 1.0 / np.where(np.abs(dir) < 1e-12, np.copysign(1e-12, dir), dir)
    stack = [0]
    best_t = t_max
    best_i = -1
    best_u = 0.0
    best_v = 0.0
    nodes = bvh.nodes
    order = bvh.tri_order
    while stack:
        ni = stack.pop()
        node = nodes[ni]
        if not _ray_aabb(orig, inv, node[0:3], node[3:6]):
            continue
        left = _as_int(node[6])
        right = _as_int(node[7])
        if right < 0:
            count = -right - 1
            for k in range(count):
                ti = int(order[left + k])
                t, u, v = _ray_tri(orig, dir, world.v0[ti], world.v1[ti], world.v2[ti])
                if t < best_t:
                    best_t, best_i, best_u, best_v = t, ti, u, v
        else:
            stack.append(right)
            stack.append(left)
    return best_t, best_i, best_u, best_v


def any_hit(
    orig: np.ndarray,
    dir: np.ndarray,
    world: WorldMesh,
    bvh: BVH,
    t_max: float,
) -> bool:
    t, _, _, _ = closest_hit(orig, dir, world, bvh, t_max=t_max)
    return t < t_max


# ── sampling helpers ─────────────────────────────────────────


def _ortho_basis(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if abs(float(n[1])) < 0.9:
        a = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    else:
        a = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    t = np.cross(a, n)
    t /= max(np.linalg.norm(t), 1e-12)
    b = np.cross(n, t)
    return t, b


def _cosine_hemisphere(n: np.ndarray, r1: float, r2: float) -> np.ndarray:
    phi = 2.0 * math.pi * r1
    r = math.sqrt(max(r2, 0.0))
    x = r * math.cos(phi)
    y = r * math.sin(phi)
    z = math.sqrt(max(1.0 - r2, 0.0))
    t, b = _ortho_basis(n)
    d = t * x + b * y + n * z
    return d / max(np.linalg.norm(d), 1e-12)


def _hash2(ix: int, iy: int, s: int) -> tuple[float, float]:
    """Deterministic stratified-ish [0,1) pair — stable across runs (low discrepancy-ish)."""
    n = (ix * 73856093) ^ (iy * 19349663) ^ (s * 83492791)
    n = (n ^ (n >> 13)) * 1274126177
    u = ((n >> 0) & 0xFFFF) / 65536.0
    v = ((n >> 16) & 0xFFFF) / 65536.0
    return u, v


# ── UV raster ────────────────────────────────────────────────


@dataclass
class SurfMap:
    tw: int
    th: int
    pos: np.ndarray  # HxWx3
    nrm: np.ndarray
    mask: np.ndarray  # HxW bool
    overlap: int = 0


def rasterize_part_uv(part: MeshPart, tw: int, th: int) -> SurfMap | None:
    if part.uvs is None or part.uvs.size == 0 or part.indices.size < 3:
        return None
    v = part.vertices.astype(np.float64)
    uv = part.uvs.astype(np.float64)
    idx = part.indices.astype(np.int64).reshape(-1, 3)
    if part.normals is not None and part.normals.shape[0] == v.shape[0]:
        nrm_v = part.normals.astype(np.float64)
    else:
        nrm_v = None

    pos = np.zeros((th, tw, 3), dtype=np.float32)
    nrm = np.zeros((th, tw, 3), dtype=np.float32)
    depth = np.full((th, tw), -1.0, dtype=np.float32)
    mask = np.zeros((th, tw), dtype=bool)
    overlap = 0

    for tri in idx:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        uv0, uv1, uv2 = uv[i0], uv[i1], uv[i2]
        # Trainz V=0 at top → image row 0
        p0 = np.array([uv0[0] * tw, uv0[1] * th], dtype=np.float64)
        p1 = np.array([uv1[0] * tw, uv1[1] * th], dtype=np.float64)
        p2 = np.array([uv2[0] * tw, uv2[1] * th], dtype=np.float64)
        minx = max(0, int(math.floor(min(p0[0], p1[0], p2[0]))))
        maxx = min(tw - 1, int(math.ceil(max(p0[0], p1[0], p2[0]))))
        miny = max(0, int(math.floor(min(p0[1], p1[1], p2[1]))))
        maxy = min(th - 1, int(math.ceil(max(p0[1], p1[1], p2[1]))))
        if minx > maxx or miny > maxy:
            continue
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(area) < 1e-10:
            continue
        inv_area = 1.0 / area
        wpos = v[[i0, i1, i2]]
        if nrm_v is not None:
            wn = nrm_v[[i0, i1, i2]]
        else:
            fn = np.cross(wpos[1] - wpos[0], wpos[2] - wpos[0])
            ln = np.linalg.norm(fn) or 1.0
            wn = np.vstack([fn / ln] * 3)

        for y in range(miny, maxy + 1):
            py = y + 0.5
            for x in range(minx, maxx + 1):
                px = x + 0.5
                w0 = ((p1[0] - px) * (p2[1] - py) - (p2[0] - px) * (p1[1] - py)) * inv_area
                w1 = ((p2[0] - px) * (p0[1] - py) - (p0[0] - px) * (p2[1] - py)) * inv_area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-5 or w1 < -1e-5 or w2 < -1e-5:
                    continue
                if mask[y, x]:
                    overlap += 1
                p = w0 * wpos[0] + w1 * wpos[1] + w2 * wpos[2]
                n = w0 * wn[0] + w1 * wn[1] + w2 * wn[2]
                nn = np.linalg.norm(n)
                n = n / nn if nn > 1e-12 else np.array([0.0, 1.0, 0.0])
                # prefer facing-up / first write; still count overlap
                pos[y, x] = p.astype(np.float32)
                nrm[y, x] = n.astype(np.float32)
                mask[y, x] = True
                depth[y, x] = 1.0

    if not mask.any():
        return None
    return SurfMap(tw, th, pos, nrm, mask, overlap=overlap)


# ── path trace (CPU) ─────────────────────────────────────────


def _trace_texel_cpu(
    p: np.ndarray,
    n: np.ndarray,
    lamps_pack: dict,
    world: WorldMesh,
    bvh: BVH,
    settings: BakeSettings,
    ix: int,
    iy: int,
    *,
    do_direct: bool = True,
    do_gi: bool = True,
) -> np.ndarray:
    n = n.astype(np.float64)
    nn = np.linalg.norm(n)
    if nn < 1e-8:
        return np.zeros(3, dtype=np.float64)
    n = n / nn
    # ponytail: 5e-4 bias — tight contact shadows (1e-3 left floats)
    p = p.astype(np.float64) + n * 5e-4
    irr = np.zeros(3, dtype=np.float64)
    count = lamps_pack["count"]
    spp_d = max(1, settings.spp_direct)
    spp_g = max(0, settings.spp_gi)

    # Direct NEE with soft lamp disk + shadow ray (all scene meshes occlude)
    if do_direct:
        for li in range(count):
            power = float(lamps_pack["power"][li])
            if power < 1e-5:
                continue
            lpos = lamps_pack["pos"][li].astype(np.float64)
            lcol = lamps_pack["col"][li].astype(np.float64)
            lrange = float(lamps_pack["range"][li])
            mode = float(lamps_pack["mode"][li])
            ldir = lamps_pack["dir"][li].astype(np.float64)
            cone = float(lamps_pack["cone"][li])
            acc = np.zeros(3, dtype=np.float64)
            for s in range(spp_d):
                u, v = _hash2(ix, iy, li * 1024 + s)
                ang = 2.0 * math.pi * u
                rad = settings.lamp_radius * math.sqrt(v)
                to_p = p - lpos
                dn = np.linalg.norm(to_p)
                axis = to_p / dn if dn > 1e-8 else np.array([0.0, -1.0, 0.0])
                t, b = _ortho_basis(axis)
                sample_pos = lpos + t * (rad * math.cos(ang)) + b * (rad * math.sin(ang))
                to_l = sample_pos - p
                dist = float(np.linalg.norm(to_l))
                if dist < 1e-5 or dist > lrange:
                    continue
                L = to_l / dist
                ndotl = float(np.dot(n, L))
                if ndotl <= 0.0:
                    continue
                atten = power * max(0.0, 1.0 - dist / lrange)
                atten *= atten
                if mode > 1.5:
                    cd = float(np.dot(-L, ldir / (np.linalg.norm(ldir) or 1.0)))
                    edge = cone
                    spot = np.clip((cd - edge) / max(1e-4, 0.12), 0.0, 1.0)
                    atten *= float(spot * spot * (3 - 2 * spot))
                if atten < 1e-6:
                    continue
                # tighter tmax → less light leak under chairs
                if any_hit(p, L, world, bvh, t_max=dist * 0.999):
                    continue
                acc += lcol * atten * 5.0 * ndotl / math.pi
            if spp_d:
                irr += acc / spp_d

    # Short diffuse GI (hits any mesh in BVH)
    if do_gi and spp_g > 0 and settings.bounces > 0:
        gi = np.zeros(3, dtype=np.float64)
        for s in range(spp_g):
            thr = 1.0
            col = np.zeros(3, dtype=np.float64)
            ro = p.copy()
            rd_n = n.copy()
            for bounce in range(settings.bounces):
                u, v = _hash2(ix, iy, 50000 + s * 17 + bounce * 3)
                rd = _cosine_hemisphere(rd_n, u, v)
                t, ti, bu, bv = closest_hit(ro, rd, world, bvh, t_max=40.0)
                if ti < 0 or not math.isfinite(t):
                    break
                bw = 1.0 - bu - bv
                hit_n = bw * world.n0[ti] + bu * world.n1[ti] + bv * world.n2[ti]
                hit_n = hit_n.astype(np.float64)
                hn = np.linalg.norm(hit_n) or 1.0
                hit_n = hit_n / hn
                hit_p = (ro + rd * t) + hit_n * 5e-4
                alb = world.albedo[ti].astype(np.float64)
                em = float(world.emissive[ti])
                if em > 1e-4:
                    col += thr * alb * em * 0.35
                if count > 0:
                    u2, v2 = _hash2(ix, iy, 90000 + s * 13 + bounce)
                    li = int(u2 * count) % count
                    power = float(lamps_pack["power"][li])
                    lpos = lamps_pack["pos"][li].astype(np.float64)
                    lcol = lamps_pack["col"][li].astype(np.float64)
                    lrange = float(lamps_pack["range"][li])
                    to_l = lpos - hit_p
                    dist = float(np.linalg.norm(to_l))
                    if 1e-5 < dist <= lrange and power > 1e-5:
                        L = to_l / dist
                        nd = float(np.dot(hit_n, L))
                        if nd > 0 and not any_hit(hit_p, L, world, bvh, t_max=dist * 0.999):
                            atten = power * max(0.0, 1.0 - dist / lrange)
                            atten *= atten
                            col += thr * alb * lcol * atten * 5.0 * nd / math.pi
                thr *= 0.65
                ro = hit_p
                rd_n = hit_n
                if thr < 0.02:
                    break
            gi += col
        irr += gi / spp_g

    return irr.astype(np.float32)


def _ao_texel(
    p: np.ndarray,
    n: np.ndarray,
    world: WorldMesh,
    bvh: BVH,
    spp: int,
    radius: float,
    ix: int,
    iy: int,
) -> float:
    """Hemisphere contact AO — other meshes (and self) darken creases / floor contact."""
    n = n.astype(np.float64)
    nn = np.linalg.norm(n)
    if nn < 1e-8 or spp < 1 or radius <= 1e-5:
        return 1.0
    n = n / nn
    p = p.astype(np.float64) + n * 4e-4
    blocked = 0
    for s in range(spp):
        u, v = _hash2(ix, iy, 700_000 + s)
        rd = _cosine_hemisphere(n, u, v)
        if any_hit(p, rd, world, bvh, t_max=radius):
            blocked += 1
    ao = 1.0 - blocked / float(spp)
    # slight power → stronger grounding without crushing open floor
    return float(ao ** 1.35)


def _denoise_atrous(img: np.ndarray, mask: np.ndarray, nrm: np.ndarray, passes: int = 4) -> np.ndarray:
    """Fast edge-aware blur on irradiance (HxWx3) — normal-guided box passes."""
    out = img.astype(np.float32).copy()
    m = mask.astype(np.float32)[..., None]
    n = nrm.astype(np.float32)
    for p in range(passes):
        step = 1 << p
        acc = np.zeros_like(out)
        wsum = np.zeros(mask.shape + (1,), dtype=np.float32)
        for ky in (-2, -1, 0, 1, 2):
            for kx in (-2, -1, 0, 1, 2):
                wk = (1, 4, 6, 4, 1)[ky + 2] * (1, 4, 6, 4, 1)[kx + 2] / 256.0
                rolled = np.roll(np.roll(out, ky * step, axis=0), kx * step, axis=1)
                rn = np.roll(np.roll(n, ky * step, axis=0), kx * step, axis=1)
                rm = np.roll(np.roll(m, ky * step, axis=0), kx * step, axis=1)
                dn = np.clip((n * rn).sum(axis=-1, keepdims=True), 0.0, 1.0) ** 16
                wt = wk * dn * rm
                acc += rolled * wt
                wsum += wt
        out = np.where(wsum > 1e-8, acc / np.maximum(wsum, 1e-8), out)
        out = out * m  # keep uncovered black
    return out


# ── CUDA batch path (direct lighting heavy path) ─────────────

_CUDA_DIRECT_SRC = r"""
__device__ inline float3 bd_cross(float3 a, float3 b) {
    return make_float3(a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x);
}
__device__ inline float bd_dot(float3 a, float3 b) {
    return a.x*b.x + a.y*b.y + a.z*b.z;
}
__device__ inline float3 bd_norm(float3 a) {
    float l = sqrtf(bd_dot(a, a));
    if (l < 1e-12f) return make_float3(0.f, 1.f, 0.f);
    return make_float3(a.x/l, a.y/l, a.z/l);
}
__device__ inline int bd_ray_aabb(float ox, float oy, float oz,
    float idx, float idy, float idz, const float* bmin, const float* bmax) {
    float tmin = -1e30f, tmax = 1e30f;
    float o[3] = {ox, oy, oz};
    float id[3] = {idx, idy, idz};
    for (int a = 0; a < 3; a++) {
        float t0 = (bmin[a] - o[a]) * id[a];
        float t1 = (bmax[a] - o[a]) * id[a];
        float lo = fminf(t0, t1), hi = fmaxf(t0, t1);
        tmin = fmaxf(tmin, lo);
        tmax = fminf(tmax, hi);
    }
    return tmax >= fmaxf(tmin, 0.f);
}
__device__ inline int bd_ray_tri(float3 o, float3 d, float3 a, float3 b, float3 c, float* t_out) {
    float3 e1 = make_float3(b.x-a.x, b.y-a.y, b.z-a.z);
    float3 e2 = make_float3(c.x-a.x, c.y-a.y, c.z-a.z);
    float3 pvec = bd_cross(d, e2);
    float det = bd_dot(e1, pvec);
    if (fabsf(det) < 1e-7f) return 0;
    float inv = 1.f / det;
    float3 tvec = make_float3(o.x-a.x, o.y-a.y, o.z-a.z);
    float u = bd_dot(tvec, pvec) * inv;
    if (u < 0.f || u > 1.f) return 0;
    float3 qvec = bd_cross(tvec, e1);
    float v = bd_dot(d, qvec) * inv;
    if (v < 0.f || u + v > 1.f) return 0;
    float t = bd_dot(e2, qvec) * inv;
    if (t <= 1e-5f) return 0;
    *t_out = t;
    return 1;
}
__device__ int bd_any_hit(
    float3 o, float3 d, float tmax,
    const float* v0, const float* v1, const float* v2,
    const int* tri_order, const float* bvh_nodes, int n_nodes
) {
    float idx = 1.f / (fabsf(d.x) < 1e-12f ? copysignf(1e-12f, d.x) : d.x);
    float idy = 1.f / (fabsf(d.y) < 1e-12f ? copysignf(1e-12f, d.y) : d.y);
    float idz = 1.f / (fabsf(d.z) < 1e-12f ? copysignf(1e-12f, d.z) : d.z);
    int stack[64];
    int sp = 0;
    stack[sp++] = 0;
    while (sp > 0) {
        int ni = stack[--sp];
        if (ni < 0 || ni >= n_nodes) continue;
        const float* node = bvh_nodes + ni * 8;
        float bmin[3] = {node[0], node[1], node[2]};
        float bmax[3] = {node[3], node[4], node[5]};
        if (!bd_ray_aabb(o.x, o.y, o.z, idx, idy, idz, bmin, bmax)) continue;
        int left = __float_as_int(node[6]);
        int right = __float_as_int(node[7]);
        if (right < 0) {
            int count = -right - 1;
            for (int k = 0; k < count; k++) {
                int ti = tri_order[left + k];
                float3 a = make_float3(v0[ti*3], v0[ti*3+1], v0[ti*3+2]);
                float3 b = make_float3(v1[ti*3], v1[ti*3+1], v1[ti*3+2]);
                float3 c = make_float3(v2[ti*3], v2[ti*3+1], v2[ti*3+2]);
                float t;
                if (bd_ray_tri(o, d, a, b, c, &t) && t < tmax) return 1;
            }
        } else if (sp < 62) {
            stack[sp++] = right;
            stack[sp++] = left;
        }
    }
    return 0;
}

extern "C" __global__
void bake_direct_chunk(
    const float* pos, const float* nrm, const unsigned char* mask,
    const int* seed_idx,
    const float* lamp_pos, const float* lamp_col, const float* lamp_power,
    const float* lamp_range, const float* lamp_mode, const float* lamp_dir, const float* lamp_cone,
    const int lamp_count,
    const float* v0, const float* v1, const float* v2,
    const int* tri_order, const float* bvh_nodes, const int n_nodes,
    const int n_texels, const int spp, const float lamp_radius,
    float* out_irr
) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i >= n_texels) return;
    if (mask[i] == 0) {
        out_irr[i*3+0] = out_irr[i*3+1] = out_irr[i*3+2] = 0.f;
        return;
    }
    float3 p = make_float3(pos[i*3+0], pos[i*3+1], pos[i*3+2]);
    float3 n = make_float3(nrm[i*3+0], nrm[i*3+1], nrm[i*3+2]);
    float nn = sqrtf(n.x*n.x + n.y*n.y + n.z*n.z);
    if (nn < 1e-8f) {
        out_irr[i*3+0] = out_irr[i*3+1] = out_irr[i*3+2] = 0.f;
        return;
    }
    n.x /= nn; n.y /= nn; n.z /= nn;
    p.x += n.x * 5e-4f; p.y += n.y * 5e-4f; p.z += n.z * 5e-4f;
    float3 irr = make_float3(0.f, 0.f, 0.f);
    /* stable RNG across VRAM chunks via absolute texel index */
    unsigned int rng = (unsigned int)(seed_idx[i] * 747796405u + 2891336453u);

    for (int li = 0; li < lamp_count; li++) {
        float power = lamp_power[li];
        if (power < 1e-5f) continue;
        float3 lpos = make_float3(lamp_pos[li*3], lamp_pos[li*3+1], lamp_pos[li*3+2]);
        float3 lcol = make_float3(lamp_col[li*3], lamp_col[li*3+1], lamp_col[li*3+2]);
        float lrange = lamp_range[li];
        float mode = lamp_mode[li];
        float3 ldir = make_float3(lamp_dir[li*3], lamp_dir[li*3+1], lamp_dir[li*3+2]);
        float cone = lamp_cone[li];
        float3 acc = make_float3(0.f, 0.f, 0.f);
        for (int s = 0; s < spp; s++) {
            rng = rng * 1664525u + 1013904223u;
            float u = (rng & 0x00ffffffu) / 16777216.f;
            rng = rng * 1664525u + 1013904223u;
            float v = (rng & 0x00ffffffu) / 16777216.f;
            float ang = 6.2831853f * u;
            float rad = lamp_radius * sqrtf(v);
            float3 axis = bd_norm(make_float3(p.x-lpos.x, p.y-lpos.y, p.z-lpos.z));
            float3 tmp = (fabsf(axis.y) < 0.9f) ? make_float3(0.f,1.f,0.f) : make_float3(1.f,0.f,0.f);
            float3 t = bd_norm(bd_cross(tmp, axis));
            float3 b = bd_cross(axis, t);
            float ca = cosf(ang), sa = sinf(ang);
            float3 sample_pos = make_float3(
                lpos.x + t.x*rad*ca + b.x*rad*sa,
                lpos.y + t.y*rad*ca + b.y*rad*sa,
                lpos.z + t.z*rad*ca + b.z*rad*sa);
            float3 to_l = make_float3(sample_pos.x-p.x, sample_pos.y-p.y, sample_pos.z-p.z);
            float dist = sqrtf(bd_dot(to_l, to_l));
            if (dist < 1e-5f || dist > lrange) continue;
            float3 L = make_float3(to_l.x/dist, to_l.y/dist, to_l.z/dist);
            float ndotl = bd_dot(n, L);
            if (ndotl <= 0.f) continue;
            float atten = power * fmaxf(0.f, 1.f - dist / lrange);
            atten *= atten;
            if (mode > 1.5f) {
                float3 ld = bd_norm(ldir);
                float cd = bd_dot(make_float3(-L.x, -L.y, -L.z), ld);
                float spot = fminf(1.f, fmaxf(0.f, (cd - cone) / 0.12f));
                spot = spot * spot * (3.f - 2.f * spot);
                atten *= spot;
            }
            if (atten < 1e-6f) continue;
            if (bd_any_hit(p, L, dist * 0.999f, v0, v1, v2, tri_order, bvh_nodes, n_nodes))
                continue;
            float scale = atten * 5.f * ndotl * 0.318309886f;
            acc.x += lcol.x * scale;
            acc.y += lcol.y * scale;
            acc.z += lcol.z * scale;
        }
        irr.x += acc.x / (float)spp;
        irr.y += acc.y / (float)spp;
        irr.z += acc.z / (float)spp;
    }
    out_irr[i*3+0] = irr.x;
    out_irr[i*3+1] = irr.y;
    out_irr[i*3+2] = irr.z;
}
"""

# Bytes reserved so OpenGL preview / driver don't get squeezed during bake.
_VRAM_HEADROOM_FRAC = 0.22
_VRAM_HEADROOM_MIN = 768 * 1024 * 1024
# pos(12)+nrm(12)+mask(1)+out(12) + alignment slack
_BYTES_PER_SAMPLE = 64
_CHUNK_MIN = 2048
_CHUNK_MAX = 512 * 1024


def _vram_mem_info() -> tuple[int, int] | None:
    """Return (free_bytes, total_bytes) or None if CUDA unavailable."""
    try:
        import cupy as cp

        if not cp.cuda.is_available():
            return None
        free_b, total_b = cp.cuda.runtime.memGetInfo()
        return int(free_b), int(total_b)
    except Exception:
        return None


def _vram_headroom(total_b: int) -> int:
    return max(_VRAM_HEADROOM_MIN, int(total_b * _VRAM_HEADROOM_FRAC))


def cuda_texel_chunk_size(
    free_b: int,
    total_b: int,
    *,
    scene_bytes: int = 0,
    n_samples: int = 0,
) -> int:
    """How many covered texels to upload per CUDA chunk given free VRAM.

    Keeps ~22%/768MB headroom for the GL viewer. When free VRAM is tight,
    dips toward a 256MB floor but only in small drip chunks (never a flood).
    ``scene_bytes`` is reserved out of free (BVH/tris already on device).
    """
    free_b = max(0, int(free_b) - int(scene_bytes))
    head = _vram_headroom(total_b)
    emergency = 256 * 1024 * 1024
    budget = free_b - head
    drip = False
    if budget < _BYTES_PER_SAMPLE * _CHUNK_MIN:
        # Headroom can't be met — drip small chunks down to emergency floor
        budget = free_b - emergency
        drip = True
    if budget < _BYTES_PER_SAMPLE:
        return 0
    n = int(budget // _BYTES_PER_SAMPLE)
    if drip:
        n = min(n, _CHUNK_MIN)
    n = min(n, _CHUNK_MAX)
    if n_samples > 0:
        n = min(n, int(n_samples))
    if n >= 128:
        n = (n // 128) * 128
    return int(n)

def _bake_direct_cuda(
    pos: np.ndarray,
    nrm: np.ndarray,
    mask: np.ndarray,
    lamps_pack: dict,
    world: WorldMesh,
    bvh: BVH,
    spp: int,
    lamp_radius: float,
    on_progress: ProgressCb | None = None,
    progress_base: int = 0,
    progress_span: int = 20,
    cancel_flag: list[bool] | None = None,
    issues: list[BakeIssue] | None = None,
) -> np.ndarray | None:
    """CUDA direct bake in VRAM-aware chunks (compact covered texels only)."""
    try:
        import cupy as cp
    except Exception:
        return None
    if not cp.cuda.is_available() or bvh.nodes.size == 0:
        return None
    cancel_flag = cancel_flag or [False]
    th, tw = mask.shape
    out = np.zeros((th, tw, 3), dtype=np.float32)
    ys, xs = np.where(mask)
    n_cov = int(ys.size)
    if n_cov == 0:
        return out

    # Compact covered samples — never upload empty texels
    pos_c = pos[ys, xs].astype(np.float32, copy=False)
    nrm_c = nrm[ys, xs].astype(np.float32, copy=False)
    # absolute linear index for stable RNG across chunks
    abs_idx = (ys.astype(np.int32) * tw + xs.astype(np.int32))

    # Scene stays resident; texel chunks stream
    d_lp = cp.asarray(lamps_pack["pos"].astype(np.float32))
    d_lc = cp.asarray(lamps_pack["col"].astype(np.float32))
    d_pow = cp.asarray(lamps_pack["power"].astype(np.float32))
    d_rng = cp.asarray(lamps_pack["range"].astype(np.float32))
    d_mode = cp.asarray(lamps_pack["mode"].astype(np.float32))
    d_dir = cp.asarray(lamps_pack["dir"].astype(np.float32))
    d_cone = cp.asarray(lamps_pack["cone"].astype(np.float32))
    d_v0 = cp.asarray(world.v0.astype(np.float32))
    d_v1 = cp.asarray(world.v1.astype(np.float32))
    d_v2 = cp.asarray(world.v2.astype(np.float32))
    d_order = cp.asarray(bvh.tri_order.astype(np.int32))
    d_nodes = cp.asarray(bvh.nodes.astype(np.float32))
    scene_bytes = int(
        d_lp.nbytes + d_lc.nbytes + d_pow.nbytes + d_rng.nbytes
        + d_mode.nbytes + d_dir.nbytes + d_cone.nbytes
        + d_v0.nbytes + d_v1.nbytes + d_v2.nbytes
        + d_order.nbytes + d_nodes.nbytes
    )

    info = _vram_mem_info()
    if info is None:
        return None
    free0, total0 = info
    chunk0 = cuda_texel_chunk_size(free0, total0, scene_bytes=scene_bytes, n_samples=n_cov)
    if chunk0 <= 0:
        if issues is not None:
            issues.append(
                BakeIssue(
                    "warn",
                    f"VRAM too low for CUDA bake "
                    f"(free {free0/1e9:.2f} GB / {total0/1e9:.2f} GB); CPU fallback.",
                )
            )
        # drop scene before CPU path reuses host RAM
        del d_lp, d_lc, d_pow, d_rng, d_mode, d_dir, d_cone
        del d_v0, d_v1, d_v2, d_order, d_nodes
        try:
            cp.get_default_memory_pool().free_all_blocks()
        except Exception:
            pass
        return None

    if issues is not None and chunk0 < n_cov:
        issues.append(
            BakeIssue(
                "info",
                f"CUDA chunked bake: {chunk0} texels/chunk "
                f"(free VRAM {free0/1e9:.2f}/{total0/1e9:.2f} GB, "
                f"headroom {_vram_headroom(total0)/1e9:.2f} GB).",
            )
        )

    # Kernel: compact samples always "masked on"; pass seed via abs index in pos.w? 
    # Use mask buffer as unused ones; RNG uses (index_offset + i) via rewriting kernel
    # to take index_base. Patch: store abs_idx in a parallel int buffer — simpler to
    # keep mask=1 and pass index_base into kernel for RNG.
    kern = cp.RawKernel(_CUDA_DIRECT_SRC, "bake_direct_chunk")
    pool = cp.get_default_memory_pool()
    done = 0
    t0 = time.perf_counter()
    chunk = chunk0

    while done < n_cov:
        if cancel_flag[0]:
            break
        # Re-query free VRAM each chunk — shrink if viewer/driver ate memory
        info = _vram_mem_info()
        if info is not None:
            free_b, total_b = info
            adapt = cuda_texel_chunk_size(
                free_b, total_b, scene_bytes=scene_bytes, n_samples=n_cov - done
            )
            if adapt > 0:
                chunk = adapt
            elif free_b < _vram_headroom(total_b) * 0.5:
                # critically low — yield, free pool, retry smaller
                pool.free_all_blocks()
                cp.cuda.runtime.deviceSynchronize()
                info2 = _vram_mem_info()
                if info2 is not None:
                    adapt = cuda_texel_chunk_size(
                        info2[0], info2[1], scene_bytes=scene_bytes, n_samples=n_cov - done
                    )
                chunk = max(512, adapt) if adapt > 0 else 512
                if issues is not None:
                    issues.append(
                        BakeIssue(
                            "warn",
                            f"VRAM low during bake — shrinking chunk to {chunk} texels.",
                        )
                    )

        n_chunk = min(chunk, n_cov - done)
        sl = slice(done, done + n_chunk)
        ones = np.ones(n_chunk, dtype=np.uint8)

        d_pos = d_nrm = d_mask = d_seed = d_out = None
        try:
            d_pos = cp.asarray(pos_c[sl])
            d_nrm = cp.asarray(nrm_c[sl])
            d_mask = cp.asarray(ones)
            d_seed = cp.asarray(abs_idx[sl])
            d_out = cp.zeros((n_chunk, 3), dtype=cp.float32)
            block = 128
            grid = (n_chunk + block - 1) // block
            kern(
                (grid,),
                (block,),
                (
                    d_pos.ravel(),
                    d_nrm.ravel(),
                    d_mask.ravel(),
                    d_seed.ravel(),
                    d_lp.ravel(),
                    d_lc.ravel(),
                    d_pow.ravel(),
                    d_rng.ravel(),
                    d_mode.ravel(),
                    d_dir.ravel(),
                    d_cone.ravel(),
                    np.int32(lamps_pack["count"]),
                    d_v0.ravel(),
                    d_v1.ravel(),
                    d_v2.ravel(),
                    d_order.ravel(),
                    d_nodes.ravel(),
                    np.int32(bvh.nodes.shape[0]),
                    np.int32(n_chunk),
                    np.int32(spp),
                    np.float32(lamp_radius),
                    d_out.ravel(),
                ),
            )
            cp.cuda.Stream.null.synchronize()
            chunk_irr = cp.asnumpy(d_out)
        except Exception as exc:  # noqa: BLE001
            # OOM / launch fail — free, halve chunk, retry; tiny chunk => CPU fallback
            d_pos = d_nrm = d_mask = d_seed = d_out = None
            pool.free_all_blocks()
            if n_chunk <= 512:
                if issues is not None:
                    issues.append(
                        BakeIssue("warn", f"CUDA chunk failed ({exc}); CPU fallback.")
                    )
                d_lp = d_lc = d_pow = d_rng = d_mode = d_dir = d_cone = None
                d_v0 = d_v1 = d_v2 = d_order = d_nodes = None
                pool.free_all_blocks()
                # never return a partial CUDA image — CPU path rebakes cleanly
                return None
            chunk = max(512, n_chunk // 2)
            if issues is not None:
                issues.append(
                    BakeIssue(
                        "warn",
                        f"CUDA OOM/fail — retry with chunk {chunk} ({exc}).",
                    )
                )
            continue

        out[ys[sl], xs[sl]] = chunk_irr
        done += n_chunk
        d_pos = d_nrm = d_mask = d_seed = d_out = None
        info = _vram_mem_info()
        if info is not None and info[0] < _vram_headroom(info[1]):
            pool.free_all_blocks()

        if on_progress:
            elapsed = time.perf_counter() - t0
            rate = done / max(elapsed, 1e-6)
            eta = (n_cov - done) / max(rate, 1e-6)
            pct = progress_base + int(progress_span * done / max(n_cov, 1))
            on_progress(f"CUDA chunk {done}/{n_cov}", pct, 100, eta)

    d_lp = d_lc = d_pow = d_rng = d_mode = d_dir = d_cone = None
    d_v0 = d_v1 = d_v2 = d_order = d_nodes = None
    try:
        pool.free_all_blocks()
    except Exception:
        pass
    return out


def _bake_irradiance_cpu(
    surf: SurfMap,
    lamps_pack: dict,
    world: WorldMesh,
    bvh: BVH,
    settings: BakeSettings,
    on_progress: ProgressCb | None,
    progress_base: int,
    progress_span: int,
    cancel_flag: list[bool],
    *,
    do_direct: bool = True,
    do_gi: bool = True,
    stage: str = "Path-trace",
) -> np.ndarray:
    th, tw = surf.th, surf.tw
    irr = np.zeros((th, tw, 3), dtype=np.float32)
    ys, xs = np.where(surf.mask)
    total = int(ys.size)
    if total == 0:
        return irr

    def work_chunk(sl: slice) -> list[tuple[int, int, np.ndarray]]:
        out = []
        for k in range(sl.start, sl.stop):
            if cancel_flag[0]:
                break
            y, x = int(ys[k]), int(xs[k])
            c = _trace_texel_cpu(
                surf.pos[y, x],
                surf.nrm[y, x],
                lamps_pack,
                world,
                bvh,
                settings,
                x,
                y,
                do_direct=do_direct,
                do_gi=do_gi,
            )
            out.append((y, x, c))
        return out

    from ..util.hw import bake_workers

    n_workers = min(bake_workers(), max(1, (total + 511) // 512))
    chunk = max(32, total // (n_workers * 4) or 32)
    slices = [slice(i, min(i + chunk, total)) for i in range(0, total, chunk)]
    done = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = [ex.submit(work_chunk, sl) for sl in slices]
        for fut in as_completed(futs):
            if cancel_flag[0]:
                break
            for y, x, c in fut.result():
                irr[y, x] = c
            done += chunk
            done = min(done, total)
            elapsed = time.perf_counter() - t0
            rate = done / max(elapsed, 1e-6)
            remain = (total - done) / max(rate, 1e-6)
            if on_progress:
                pct = progress_base + int(progress_span * done / max(total, 1))
                on_progress(f"{stage} {done}/{total}", pct, 100, remain)
    return irr


def _bake_ao_cpu(
    surf: SurfMap,
    world: WorldMesh,
    bvh: BVH,
    settings: BakeSettings,
    on_progress: ProgressCb | None,
    progress_base: int,
    progress_span: int,
    cancel_flag: list[bool],
) -> np.ndarray:
    """Contact AO over full scene BVH (seats ground onto floor, etc.)."""
    th, tw = surf.th, surf.tw
    ao = np.ones((th, tw), dtype=np.float32)
    ys, xs = np.where(surf.mask)
    total = int(ys.size)
    spp = max(0, int(settings.ao_spp))
    radius = float(settings.ao_radius)
    if total == 0 or spp < 1 or radius <= 1e-5:
        return ao

    def work_chunk(sl: slice) -> list[tuple[int, int, float]]:
        out = []
        for k in range(sl.start, sl.stop):
            if cancel_flag[0]:
                break
            y, x = int(ys[k]), int(xs[k])
            v = _ao_texel(
                surf.pos[y, x],
                surf.nrm[y, x],
                world,
                bvh,
                spp,
                radius,
                x,
                y,
            )
            out.append((y, x, v))
        return out

    from ..util.hw import bake_workers

    n_workers = min(bake_workers(), max(1, (total + 511) // 512))
    chunk = max(32, total // (n_workers * 4) or 32)
    slices = [slice(i, min(i + chunk, total)) for i in range(0, total, chunk)]
    done = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = [ex.submit(work_chunk, sl) for sl in slices]
        for fut in as_completed(futs):
            if cancel_flag[0]:
                break
            for y, x, v in fut.result():
                ao[y, x] = v
            done += chunk
            done = min(done, total)
            elapsed = time.perf_counter() - t0
            rate = done / max(elapsed, 1e-6)
            remain = (total - done) / max(rate, 1e-6)
            if on_progress:
                pct = progress_base + int(progress_span * done / max(total, 1))
                on_progress(f"Contact AO {done}/{total}", pct, 100, remain)
    return ao


# ── public bake ──────────────────────────────────────────────


def _target_groups(scene: Scene) -> list[tuple[str, str, list[MeshPart], str | None, str | None]]:
    """Group parts by (mesh_key, material family) → parts, albedo_path, parameter_path."""
    groups: dict[tuple[str, str], list[MeshPart]] = {}
    for part in scene.parts:
        if part.uvs is None or part.uvs.size == 0:
            continue
        raw = texture_stem(part.albedo_ref or part.name or "") or part.name or "part"
        fam, _role = material_family(raw)
        key = (part.mesh_key or "", fam or raw)
        groups.setdefault(key, []).append(part)
    out = []
    for (mk, stem), parts in sorted(groups.items()):
        alb = next((p.albedo_path for p in parts if p.albedo_path), None)
        prm = next((p.parameter_path for p in parts if p.parameter_path), None)
        out.append((mk, stem, parts, alb, prm))
    return out


def _resolve_res(alb_path: str | None, max_res: int) -> tuple[int, int]:
    from PIL import Image

    if alb_path and Path(alb_path).is_file():
        with Image.open(alb_path) as im:
            w, h = im.size
        scale = min(1.0, max_res / max(w, h))
        return max(16, int(round(w * scale))), max(16, int(round(h * scale)))
    return min(1024, max_res), min(1024, max_res)


def bake_lamps_to_textures(
    scene: Scene,
    lamps: list[Lamp],
    out_dir: Path,
    settings: BakeSettings | None = None,
    on_progress: ProgressCb | None = None,
    cancel_flag: list[bool] | None = None,
) -> BakeResult:
    settings = settings or BakeSettings.from_quality("high")
    cancel_flag = cancel_flag or [False]
    t0 = time.perf_counter()
    result = BakeResult(out_dir=out_dir)
    enabled = [L for L in lamps if L.enabled and L.brightness > 1e-4]
    if not enabled:
        result.issues.append(BakeIssue("error", "No enabled lamps to bake."))
        return result
    if not scene.parts:
        result.issues.append(BakeIssue("error", "Scene has no mesh parts."))
        return result

    use_cuda = bool(settings.prefer_cuda and cuda_available())
    result.backend = "cuda" if use_cuda else "cpu"
    if settings.prefer_cuda and not use_cuda:
        result.issues.append(
            BakeIssue("warn", "CUDA/CuPy unavailable — baking on CPU (slower).")
        )

    if on_progress:
        on_progress("Building mesh BVH…", 2, 100, 0.0)
    world = build_world(scene, enabled)
    if world.v0.shape[0] == 0:
        result.issues.append(BakeIssue("error", "No triangles to bake against."))
        return result
    bvh = build_bvh(world)
    n_parts = len(scene.parts)
    n_tris = int(world.v0.shape[0])
    result.issues.append(
        BakeIssue(
            "info",
            f"Cross-mesh occluders: {n_parts} meshes · {n_tris} tris "
            f"(shadows + contact AO r={settings.ao_radius:.2f}m)",
        )
    )
    lamps_pack = pack_for_gpu(enabled, cast=True)
    groups = _target_groups(scene)
    if not groups:
        result.issues.append(BakeIssue("error", "No UV-mapped parts to bake."))
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    n_groups = len(groups)
    for gi, (mk, stem, parts, alb_path, prm_path) in enumerate(groups):
        if cancel_flag[0]:
            result.cancelled = True
            break
        base = 5 + int(90 * gi / n_groups)
        span = max(1, int(90 / n_groups) - 2)
        label = f"{mk + ' / ' if mk else ''}{stem}"
        if on_progress:
            on_progress(f"Raster UV · {label}", base, 100, 0.0)

        tw, th = _resolve_res(alb_path, settings.max_res)
        # merge rasters from all parts sharing the map
        surf: SurfMap | None = None
        for part in parts:
            sm = rasterize_part_uv(part, tw, th)
            if sm is None:
                continue
            if surf is None:
                surf = sm
            else:
                # union
                fresh = sm.mask & ~surf.mask
                surf.pos[fresh] = sm.pos[fresh]
                surf.nrm[fresh] = sm.nrm[fresh]
                both = sm.mask & surf.mask
                surf.overlap += int(both.sum()) + sm.overlap
                surf.mask |= sm.mask
        if surf is None or not surf.mask.any():
            result.issues.append(BakeIssue("warn", f"No UV coverage: {label}"))
            continue
        if surf.overlap > 64:
            result.issues.append(
                BakeIssue(
                    "warn",
                    f"UV overlap ~{surf.overlap} texels on {label} — bake may smear.",
                )
            )

        # irradiance
        irr = None
        used_cuda_direct = False
        if use_cuda:
            if on_progress:
                on_progress(f"CUDA direct · {label}", base + 1, 100, 0.0)
            try:
                irr = _bake_direct_cuda(
                    surf.pos,
                    surf.nrm,
                    surf.mask,
                    lamps_pack,
                    world,
                    bvh,
                    settings.spp_direct,
                    settings.lamp_radius,
                    on_progress=on_progress,
                    progress_base=base + 1,
                    progress_span=max(1, span // 3),
                    cancel_flag=cancel_flag,
                    issues=result.issues,
                )
                used_cuda_direct = irr is not None
                if irr is None and use_cuda:
                    result.backend = "cpu+cuda-vram"
            except Exception as exc:  # noqa: BLE001
                result.issues.append(
                    BakeIssue("warn", f"CUDA direct failed ({exc}); CPU fallback.")
                )
                irr = None
                use_cuda = False
                result.backend = "cpu+cuda-fail"
        if irr is None:
            # full CPU path (direct + GI)
            irr = _bake_irradiance_cpu(
                surf,
                lamps_pack,
                world,
                bvh,
                settings,
                on_progress,
                base + 2,
                max(1, span // 2),
                cancel_flag,
            )
        else:
            if on_progress:
                on_progress(f"CUDA direct done · {label}", base + span // 4, 100, 0.0)
            # CUDA skips GI — add it on CPU so multi-mesh bounce isn't flat
            if settings.spp_gi > 0 and settings.bounces > 0 and not cancel_flag[0]:
                gi = _bake_irradiance_cpu(
                    surf,
                    lamps_pack,
                    world,
                    bvh,
                    settings,
                    on_progress,
                    base + span // 4,
                    max(1, span // 4),
                    cancel_flag,
                    do_direct=False,
                    do_gi=True,
                    stage="GI",
                )
                irr = irr + gi
                if used_cuda_direct:
                    result.backend = "cuda+cpu-gi"

        if cancel_flag[0]:
            result.cancelled = True
            break

        if settings.denoise:
            if on_progress:
                on_progress(f"Denoise · {label}", base + span - 6, 100, 0.0)
            # fewer passes so contact AO (next) stays sharp
            irr = _denoise_atrous(irr, surf.mask, surf.nrm, passes=3)

        # contact AO after denoise — grounds seats onto floor across meshes
        ao = np.ones(surf.mask.shape, dtype=np.float32)
        if settings.ao_spp > 0 and settings.ao_strength > 1e-4 and not cancel_flag[0]:
            ao = _bake_ao_cpu(
                surf,
                world,
                bvh,
                settings,
                on_progress,
                base + span - 4,
                3,
                cancel_flag,
            )

        if cancel_flag[0]:
            result.cancelled = True
            break

        albedo = _load_rgba_f32(alb_path, tw, th)
        param = _load_rgba_f32(prm_path, tw, th)
        # default parameter if missing: mid rough / white AO
        if prm_path is None or not Path(prm_path).is_file():
            param[..., 0] = 0.0
            param[..., 1] = 0.55
            param[..., 2] = 1.0
            param[..., 3] = 0.0

        is_lamp_group = any(
            part_is_lamp(p, texture_stem(p.albedo_ref or p.name or "") or "") for p in parts
        )
        str_ao = float(np.clip(settings.ao_strength, 0.0, 1.0))
        ao_w = (1.0 - str_ao) + str_ao * ao  # 1=open, lower in creases
        ao3 = ao_w[..., None].astype(np.float32)
        light = irr * settings.albedo_scale * (0.40 + 0.60 * ao3)
        ambient_eff = (settings.ambient * ao_w)[..., None].astype(np.float32)
        # albedo: base * (ambient*AO + light), soft highlight add
        lit = albedo[..., :3] * (ambient_eff + light) + light * 0.08
        if is_lamp_group:
            # keep tubes readable — lift toward lamp tint average
            tint = np.mean(
                [L.color for L in enabled if texture_stem(L.stem) == stem or L.stem == stem],
                axis=0,
            ) if any(L.stem == stem for L in enabled) else np.array([1.0, 0.62, 0.22])
            lit = np.clip(lit + np.asarray(tint, dtype=np.float32) * 0.25, 0, 1)
        albedo_out = albedo.copy()
        albedo_out[..., :3] = np.clip(lit, 0.0, 1.0)
        albedo_out[..., 3] = albedo[..., 3]

        lum = 0.2126 * light[..., 0] + 0.7152 * light[..., 1] + 0.0722 * light[..., 2]
        param_out = param.copy()
        param_out[..., 0] = np.clip(
            param[..., 0] + lum * settings.emissive_scale * (1.35 if is_lamp_group else 1.0),
            0.0,
            1.0,
        )
        # bake contact AO into parameter B (Trainz AO channel)
        param_out[..., 2] = np.clip(param[..., 2] * ao_w, 0.0, 1.0)
        # only write covered texels; keep original elsewhere
        m = surf.mask
        albedo_final = albedo.copy()
        param_final = param.copy()
        albedo_final[m] = albedo_out[m]
        param_final[m] = param_out[m]

        safe_mk = (mk or "mesh").replace("\\", "_").replace("/", "_").replace(":", "_")
        stem_safe = stem.replace("\\", "_").replace("/", "_")
        alb_name = f"{safe_mk}__{stem_safe}_albedo.png"
        prm_name = f"{safe_mk}__{stem_safe}_parameter.png"
        alb_path_out = out_dir / alb_name
        prm_path_out = out_dir / prm_name
        _save_rgba(alb_path_out, albedo_final)
        _save_rgba(prm_path_out, param_final)
        _write_texture_txt(out_dir / f"{safe_mk}__{stem_safe}_albedo.texture.txt", alb_name, "albedo")
        _write_texture_txt(
            out_dir / f"{safe_mk}__{stem_safe}_parameter.texture.txt", prm_name, "parameter"
        )
        result.written.extend(
            [
                alb_path_out,
                prm_path_out,
                out_dir / f"{safe_mk}__{stem_safe}_albedo.texture.txt",
                out_dir / f"{safe_mk}__{stem_safe}_parameter.texture.txt",
            ]
        )
        result.issues.append(
            BakeIssue("info", f"Baked {label} -> {alb_name} + parameter ({tw}x{th})")
        )

    # report
    report = out_dir / "bake_report.txt"
    lines = [
        f"backend={result.backend}",
        f"quality={settings.quality}",
        f"seconds={time.perf_counter() - t0:.2f}",
        f"lamps={len(enabled)}",
        "",
    ]
    for iss in result.issues:
        lines.append(f"[{iss.level}] {iss.message}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result.written.append(report)
    result.seconds = time.perf_counter() - t0
    if on_progress:
        on_progress("Done" if not result.cancelled else "Cancelled", 100, 100, 0.0)
    return result
