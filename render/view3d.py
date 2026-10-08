"""QOpenGLWidget mesh preview — PBR lit mesh, world axes, corner gizmo.

Uses GLSL 120 (compat) so it works on Qt's default OpenGL context
without fighting Core-profile + fixed-function mix issues.
"""
from __future__ import annotations

import ctypes
import math
import os
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# PyOpenGL: disable per-call glGetError BEFORE importing GL (else orbit feels like 20fps).
os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")
os.environ.setdefault("PYOPENGL_ERROR_LOGGING", "0")
import OpenGL

OpenGL.ERROR_CHECKING = False
OpenGL.ERROR_LOGGING = False
try:
    import OpenGL._configflags as _gl_cfg

    _gl_cfg.ERROR_CHECKING = False
    _gl_cfg.ERROR_LOGGING = False
except Exception:
    pass

import numpy as np
from OpenGL import GL
from OpenGL.GL import shaders as gl_shaders
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QSurfaceFormat,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QFrame, QWidget

from ..io.scene import Attachment, MeshPart, Scene
from ..io.texture import stems_match, texture_stem
from .env import EnvPreset, get_env
from ..lamps import MAX_LAMPS, pack_for_gpu
from ..ui.frost import glass_is_dark, paint_glass_chip

# Full Trainz-quality preview. Old 80k step-decimate shredded interiors into streaks.
# Cabin multi-mesh (int+cab+seats) is ~300k–1M tris — fine on modern GPUs.
MAX_PREVIEW_TRIS = 2_500_000
# Steady-state uploads per paint; burst after precache seed for fast first look.
TEX_UPLOADS_PER_FRAME = 8
TEX_UPLOADS_BURST = 48
TEX_BURST_FRAMES = 16
# Real lamp→mesh shadows (ceiling lights look down). Atlas 4×2 color-depth tiles.
# Cached across camera frames — only rebuilt when lamps/meshes change.
MAX_SHADOW_LAMPS = 8
SHADOW_TILE = 128  # proven orbit budget (256×4 PCF was a regression)
SHADOW_COLS = 4
SHADOW_ROWS = 2
SHADOW_LAMPS_PER_FRAME = 4  # amortize atlas rebuild across paints

# Trainz / PAY viewer: +Z up, −Y forward. Light dirs: L, R, F, B, top.
WORLD_UP = np.array([0.0, 0.0, 1.0], dtype=np.float64)
LIGHT_DIRS = (
    (-1.0, 0.0, 0.4),
    (1.0, 0.0, 0.4),
    (0.0, -1.0, 0.3),
    (0.0, 1.0, 0.3),
    (0.0, 0.0, 1.0),
)
LIGHT_RAD = (0.95, 0.75, 0.85, 0.35, 0.40)
SUN_FILL_RAD = 0.28  # soft top fill when sun mode
DEFAULT_EMISSIVE_SCALE = 0.15

SHADING_WIRE = "wire"
SHADING_SOLID = "solid"
SHADING_MATERIAL = "material"
SHADING_RENDERED = "rendered"

# Blender Face Orientation overlay (winding / gl_FrontFacing)
FACE_ORIENT_FRONT_RGB = (0.173, 0.420, 0.792)  # blue = front
FACE_ORIENT_BACK_RGB = (0.800, 0.180, 0.180)  # red = back


def face_orient_rgb(front_facing: bool) -> tuple[float, float, float]:
    """CPU twin of the face-orient fragment colors (Blender-style)."""
    return FACE_ORIENT_FRONT_RGB if front_facing else FACE_ORIENT_BACK_RGB


def sun_dir_zup(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    """Z-up light direction toward the sun (Trainz / PAY — el=90 → +Z)."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    return (
        math.cos(el) * math.sin(az),
        math.cos(el) * math.cos(az),
        math.sin(el),
    )


# Back-compat alias (viewport is Z-up now)
sun_dir_yup = sun_dir_zup


# Cool moonlight direction (toward moon) — shared by shader lighting + sky mesh
MOON_DIR = (0.25, 0.18, 0.92)
# Celestial body distance from eye (sky-locked, no parallax)
_CELESTIAL_DIST = 420.0


def _hash2(ix: int, iy: int) -> float:
    n = (ix * 374761393 + iy * 668265263) & 0x7FFFFFFF
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0x7FFFFFFF) / float(0x7FFFFFFF)


def _moon_albedo(u: float, v: float) -> tuple[float, float, float]:
    """Procedural cratered lunar surface (no external texture)."""
    # base mare / highland
    base = 0.55 + 0.18 * math.sin(u * 17.0) * math.cos(v * 11.0)
    # a few big craters
    for cx, cy, cr, depth in (
        (0.28, 0.42, 0.09, 0.28),
        (0.62, 0.55, 0.12, 0.22),
        (0.45, 0.28, 0.06, 0.35),
        (0.78, 0.35, 0.05, 0.25),
        (0.18, 0.68, 0.07, 0.20),
        (0.55, 0.78, 0.08, 0.18),
        (0.88, 0.72, 0.04, 0.30),
    ):
        dx = (u - cx) * 1.6
        dy = v - cy
        d = math.sqrt(dx * dx + dy * dy)
        if d < cr:
            rim = abs(d - cr * 0.72)
            base -= depth * max(0.0, 1.0 - d / cr) * 0.85
            base += 0.12 * max(0.0, 1.0 - rim / (cr * 0.18))
    # fine noise
    iu, iv = int(u * 64), int(v * 32)
    base += (_hash2(iu, iv) - 0.5) * 0.08
    base = float(np.clip(base, 0.18, 0.92))
    # cool gray-blue lunar tint
    return (base * 0.92, base * 0.94, base * 1.02)


def uv_sphere_colored(
    center: tuple[float, float, float] | np.ndarray,
    radius: float,
    *,
    kind: str = "sun",
    segments: int = 28,
    rings: int = 18,
    intensity: float = 1.0,
) -> np.ndarray:
    """Triangle soup [x y z r g b] for sun/moon body (Y-up UV sphere)."""
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    rows: list[list[float]] = []
    segs = max(8, segments)
    rgs = max(4, rings)

    def vert(i: int, j: int) -> tuple[float, float, float, float, float, float]:
        u = i / segs
        v = j / rgs
        theta = u * 2.0 * math.pi
        phi = v * math.pi
        nx = math.sin(phi) * math.cos(theta)
        ny = math.cos(phi)
        nz = math.sin(phi) * math.sin(theta)
        x = cx + radius * nx
        y = cy + radius * ny
        z = cz + radius * nz
        if kind == "moon":
            r, g, b = _moon_albedo(u, 1.0 - v)
            # soft light from "sun side" of moon (phase-ish)
            lit = 0.35 + 0.65 * max(0.0, nx * 0.4 + ny * 0.2 + nz * 0.9)
            r, g, b = r * lit * intensity, g * lit * intensity, b * lit * intensity
        else:
            # sun: hot core + limb darkening
            limb = max(0.0, ny * 0.15 + 0.85)  # slight
            facing = 0.55 + 0.45 * max(0.0, -nz * 0.2 + ny * 0.1 + 0.9)
            warm = 0.55 + 0.45 * max(0.0, 1.0 - abs(ny))
            r = min(1.0, (1.0 * facing + 0.15) * intensity)
            g = min(1.0, (0.92 * facing + 0.05 * warm) * intensity)
            b = min(1.0, (0.55 * facing * limb + 0.08) * intensity)
        return x, y, z, r, g, b

    for j in range(rgs):
        for i in range(segs):
            v00 = vert(i, j)
            v10 = vert(i + 1, j)
            v01 = vert(i, j + 1)
            v11 = vert(i + 1, j + 1)
            rows.extend([list(v00), list(v10), list(v11)])
            rows.extend([list(v00), list(v11), list(v01)])
    return np.asarray(rows, dtype=np.float32)


def sun_corona_shell(
    center: tuple[float, float, float] | np.ndarray,
    radius: float,
    intensity: float = 1.0,
) -> np.ndarray:
    """Larger dim shell around sun (soft glow without fogging the whole sky)."""
    return uv_sphere_colored(
        center,
        radius * 1.55,
        kind="sun",
        segments=20,
        rings=12,
        intensity=0.22 * intensity,
    )


def fly_approach_dist(current_dist: float, *, approach: bool = True) -> float:
    """Orbit distance after fly-to. Always keeps current dolly (stable a.* hops)."""
    d = float(current_dist)
    if not approach:
        return d
    return d


def is_mesh_key_hidden(mesh_key: str, hidden: set[str] | frozenset[str]) -> bool:
    """Scene mesh table Show-off → skip this batch (empty key = always draw)."""
    return bool(mesh_key) and mesh_key in hidden


def attachment_owner_mesh_key(
    att_name: str, mesh_keys: Sequence[str] | set[str] | frozenset[str]
) -> str:
    """Map a.* name → mesh_key. Multi prefix ``stem/a.foo``; single mesh = sole key."""
    keys = [str(k) for k in mesh_keys if k]
    name = att_name or ""
    if "/" in name:
        stem = name.split("/", 1)[0]
        for mk in keys:
            if Path(mk).stem == stem:
                return mk
        return ""
    return keys[0] if len(keys) == 1 else ""


def is_attachment_hidden(
    att_name: str,
    hidden_att_mesh_keys: set[str] | frozenset[str],
    mesh_keys: Sequence[str] | set[str] | frozenset[str],
) -> bool:
    """Scene table Atts-off → skip gizmos for that mesh's a.*."""
    if not hidden_att_mesh_keys:
        return False
    owner = attachment_owner_mesh_key(att_name, mesh_keys)
    return bool(owner) and owner in hidden_att_mesh_keys


def _two_sided_name_hit(have: str, want: str) -> bool:
    """Exact material name, or the same stem before ``.m.``."""
    a = (have or "").strip().lower()
    b = (want or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    return a.split(".m.")[0] == b.split(".m.")[0]


def apply_named_two_sided(parts, batches, name: str, on: bool) -> int:
    """Flag parts and draw batches with this material name. No scene reload."""
    if not (name or "").strip():
        return 0
    parts_hit = 0
    batches_hit = 0
    for part in parts:
        if _two_sided_name_hit(getattr(part, "name", "") or "", name):
            part.two_sided = bool(on)
            parts_hit += 1
    for batch in batches:
        if _two_sided_name_hit(getattr(batch, "name", "") or "", name):
            batch.two_sided = bool(on)
            batches_hit += 1
    return parts_hit or batches_hit


def highlight_pick(
    *,
    name: str,
    mesh_key: str,
    ref_stems: set[str],
    names: set[str],
    stems: set[str],
    mesh_keys: set[str],
) -> bool:
    """True when a batch should take the Mat-style glowing outline.

    Part names (Editor Meshes row) win. Otherwise whole files by mesh_key,
    or texture-stem families (Mat list).
    """
    if names:
        return bool(name) and name in names
    if mesh_keys and mesh_key not in mesh_keys:
        return False
    if not stems:
        return bool(mesh_keys) and mesh_key in mesh_keys
    return stems_match(ref_stems, stems)


@dataclass
class DrawBatch:
    verts: np.ndarray  # unique Nx8 float32 (pos3,nrm3,uv2)
    indices: np.ndarray  # uint32 triangle indices (shared verts — same look, less GPU traffic)
    color: tuple[float, float, float]
    albedo: str | None
    normal: str | None
    parameter: str | None
    name: str
    albedo_ref: str
    normal_ref: str
    parameter_ref: str
    material_type: str
    mesh_key: str = ""
    two_sided: bool = False
    # Disk presence cached at flatten — never Path.is_file() inside paintGL.
    has_albedo: bool = False
    has_normal: bool = False
    has_parameter: bool = False
    # GPU buffers — CPU verts/indices kept for bounds / outline
    vbo: int | None = None
    ibo: int | None = None
    vcount: int = 0
    icount: int = 0

    def ref_stems(self) -> set[str]:
        out: set[str] = set()
        for ref in (
            self.albedo_ref,
            self.normal_ref,
            self.parameter_ref,
            self.albedo,
            self.normal,
            self.parameter,
            self.name,
        ):
            if ref:
                st = texture_stem(ref)
                if st:
                    out.add(st)
        return out


def _path_is_file(path: str | None) -> bool:
    return bool(path) and Path(path).is_file()


VERT_SRC = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_nrm;
attribute vec2 in_uv;
uniform mat4 u_mvp;
uniform mat4 u_model;
varying vec3 v_nrm;
varying vec2 v_uv;
varying vec3 v_world;
void main() {
    vec4 world = u_model * vec4(in_pos, 1.0);
    v_world = world.xyz;
    v_nrm = mat3(u_model) * in_nrm;
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

# Trainz PBRMetal parameter pack: R=emissive (weak), G=roughness, B=AO, A=metallic
# Normal Y fix from paid viewer: fixedNormal.y = abs(fixedNormal.y - 1.0) then *2-1
FRAG_SRC = """
#version 120
#extension GL_OES_standard_derivatives : enable

varying vec3 v_nrm;
varying vec2 v_uv;
varying vec3 v_world;
uniform sampler2D u_albedo;
uniform sampler2D u_normal;
uniform sampler2D u_parameter;
uniform vec3 u_cam_pos;
uniform vec3 u_flat_color;
uniform float u_use_tex;
uniform float u_has_normal;
uniform float u_has_parameter;
uniform float u_self_illum;
uniform float u_ambient;
uniform float u_emissive_scale;
uniform float u_mat_edit;       // 1 = apply Editor Material preview overrides
uniform float u_edit_emissive;  // replaces parameter R when editing
uniform float u_edit_rough;     // replaces parameter G
uniform float u_edit_metal;     // replaces parameter A
uniform float u_edit_specular;  // scales dielectric F0 (0.04 * specular)
uniform vec3 u_lights[5];
uniform float u_light_on[5];
uniform vec3 u_light_rad[5];
uniform int u_debug_mode;
uniform float u_face_orient;  // 1 = Blender Face Orientation (blue front / red back)
uniform float u_two_sided;    // 1 = flip N toward camera (Trainz interior)
uniform vec3 u_sky_top;
uniform vec3 u_sky_horizon;
uniform float u_ibl_strength;
uniform sampler2D u_env_map;
uniform float u_use_env_map;
uniform int u_lamp_count;
uniform vec3 u_lamp_pos[64];
uniform vec3 u_lamp_col[64];
uniform float u_lamp_power[64];
uniform float u_lamp_range[64];
uniform float u_lamp_mode[64];
uniform vec3 u_lamp_dir[64];
uniform float u_lamp_cone[64];
uniform float u_moon_on;
uniform vec3 u_moon_dir;
uniform vec3 u_moon_rad;
uniform sampler2D u_shadow_atlas;
uniform int u_shadow_count;
uniform mat4 u_shadow_vp[8];
float lampShadow(vec3 world, int li) {
    // Color-encoded depth atlas (GL 1.20 can't reliably sample DEPTH_COMPONENT).
    if (li < 0 || li >= u_shadow_count || li >= 8) return 1.0;
    vec4 clip = u_shadow_vp[li] * vec4(world, 1.0);
    if (clip.w <= 1e-5) return 1.0;
    float iw = 1.0 / clip.w;
    vec2 uv = clip.xy * iw * 0.5 + 0.5;
    float z = clip.z * iw * 0.5 + 0.5;
    if (uv.x <= 0.001 || uv.x >= 0.999 || uv.y <= 0.001 || uv.y >= 0.999) return 1.0;
    if (z <= 0.001 || z >= 0.999) return 1.0;
    float col = mod(float(li), 4.0);
    float row = floor(float(li) / 4.0);
    // 4×2 atlas → tile size (0.25, 0.5)
    vec2 tuv = vec2((col + uv.x) * 0.25, (row + uv.y) * 0.5);
    float bias = 0.0015;
    float closest = texture2D(u_shadow_atlas, tuv).r;
    float lit = (z - bias > closest) ? 0.0 : 1.0;
    return mix(0.08, 1.0, lit);
}

vec3 getNormalFromMap(vec3 N) {
    vec3 tangentNormal = texture2D(u_normal, v_uv).xyz;
    tangentNormal.y = abs(tangentNormal.y - 1.0);
    tangentNormal = tangentNormal * 2.0 - 1.0;

    vec3 Q1 = dFdx(v_world);
    vec3 Q2 = dFdy(v_world);
    vec2 st1 = dFdx(v_uv);
    vec2 st2 = dFdy(v_uv);

    vec3 N0 = normalize(N);
    vec3 T = normalize(Q1 * st2.t - Q2 * st1.t);
    vec3 B = -normalize(cross(N0, T));
    mat3 TBN = mat3(T, B, N0);
    return normalize(TBN * tangentNormal);
}

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = 3.14159265 * denom * denom;
    return a2 / max(denom, 1e-6);
}

float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    return NdotV / max(NdotV * (1.0 - k) + k, 1e-6);
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    return GeometrySchlickGGX(NdotV, roughness) * GeometrySchlickGGX(NdotL, roughness);
}

vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 shadeLight(vec3 N, vec3 V, vec3 L, vec3 albedo, float roughness, float metallic, vec3 radiance) {
    vec3 H = normalize(V + L);
    float NDF = DistributionGGX(N, H, roughness);
    float G = GeometrySmith(N, V, L, roughness);
    float dielec = 0.04 * (u_mat_edit > 0.5 ? max(u_edit_specular, 0.0) : 1.0);
    vec3 F0 = mix(vec3(dielec), albedo, metallic);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);
    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 1e-5;
    vec3 specular = numerator / denominator;
    vec3 kS = F;
    vec3 kD = (vec3(1.0) - kS) * (1.0 - metallic);
    float NdotL = max(dot(N, L), 0.0);
    return (kD * albedo / 3.14159265 + specular) * radiance * NdotL;
}

// World is Trainz Z-up; equirect HDRIs are Y-up — convert before lookup.
vec3 worldToYup(vec3 d) {
    return vec3(d.x, d.z, -d.y);
}

vec2 dirToEquirect(vec3 d) {
    vec3 y = worldToYup(normalize(d));
    float u = atan(y.z, y.x) * 0.15915494309 + 0.5;
    float v = asin(clamp(y.y, -1.0, 1.0)) * 0.31830988618 + 0.5;
    return vec2(u, 1.0 - v);
}

vec3 sampleEnvRaw(vec3 d) {
    vec3 n = normalize(d);
    if (u_use_env_map > 0.5) {
        return texture2D(u_env_map, dirToEquirect(n)).rgb;
    }
    float skyT = clamp(n.z * 0.5 + 0.5, 0.0, 1.0);
    return mix(u_sky_horizon, u_sky_top, skyT);
}

// Cheap roughness blur (UE5-ish split-sum stand-in — no prefiltered mips on GL 1.20)
vec3 sampleEnv(vec3 d, float roughness) {
    vec3 n = normalize(d);
    float blur = roughness * roughness * 0.07;
    vec3 c = sampleEnvRaw(n);
    if (blur < 0.0015 || u_use_env_map < 0.5) return c;
    vec3 up = abs(n.z) < 0.99 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 t = normalize(cross(up, n));
    vec3 b = cross(n, t);
    c *= 0.36;
    c += sampleEnvRaw(normalize(n + t * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n - t * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n + b * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n - b * blur)) * 0.16;
    return c;
}

vec3 shadeLamp(
    vec3 N, vec3 V, vec3 world,
    vec3 lampPos, vec3 lampCol, float power, float range,
    float mode, vec3 lampDir, float coneCos,
    vec3 albedo, float roughness, float metallic,
    int lampIndex
) {
    // Full GGX PBR fill + real mesh shadows from lamp depth atlas.
    vec3 toL = lampPos - world;
    float dist = length(toL);
    if (dist < 1e-4) return vec3(0.0);
    float r = max(range, 0.05);
    float nd = dist / r;
    if (nd >= 1.0) return vec3(0.0);
    float fall = 1.0 - nd;
    fall = fall * fall;
    vec3 L = toL / dist;
    float atten = power * fall;
    if (mode > 1.5) {
        float cd = dot(-L, normalize(lampDir));
        float spot = smoothstep(coneCos, min(1.0, coneCos + 0.12), cd);
        atten *= spot;
    }
    if (atten < 1e-4) return vec3(0.0);
    // Shadow before GGX — interiors are mostly occluded per lamp.
    float sh = lampShadow(world, lampIndex);
    if (sh < 0.02) return vec3(0.0);
    vec3 radiance = lampCol * atten * 3.6;
    return shadeLight(N, V, L, albedo, roughness, metallic, radiance) * sh;
}

void main() {
    // Face Orientation (Blender): winding via gl_FrontFacing — before normal flip
    if (u_face_orient > 0.5) {
        if (gl_FrontFacing) {
            gl_FragColor = vec4(0.173, 0.420, 0.792, 1.0);
        } else {
            gl_FragColor = vec4(0.800, 0.180, 0.180, 1.0);
        }
        return;
    }

    vec4 albedo = (u_use_tex > 0.5)
        ? texture2D(u_albedo, v_uv)
        : vec4(u_flat_color, 1.0);
    if (albedo.a < 0.04) discard;

    float roughness = 0.55;
    float metallic = 0.0;
    float ao = 1.0;
    float emissive = 0.0;
    if (u_has_parameter > 0.5) {
        vec4 p = texture2D(u_parameter, v_uv);
        emissive = p.r;
        roughness = clamp(p.g, 0.04, 1.0);
        ao = p.b;
        metallic = p.a;
    }
    if (u_mat_edit > 0.5) {
        // MeshEditor-style material preview: override Trainz parameter channels
        emissive = u_edit_emissive;
        roughness = clamp(u_edit_rough, 0.04, 1.0);
        metallic = clamp(u_edit_metal, 0.0, 1.0);
    }

    vec3 N = normalize(v_nrm);
    if (u_has_normal > 0.5) {
        N = getNormalFromMap(N);
    }
    vec3 Vpre = normalize(u_cam_pos - v_world);
    // Only two-sided mats flip — always-flip killed Lit specular / Face Orientation feel
    if (u_two_sided > 0.5 && dot(N, Vpre) < 0.0) {
        N = -N;
    }

    if (u_debug_mode == 1) {
        gl_FragColor = vec4(albedo.rgb, albedo.a);
        return;
    }
    if (u_debug_mode == 2) {
        gl_FragColor = vec4(N * 0.5 + 0.5, 1.0);
        return;
    }
    if (u_debug_mode == 3) {
        gl_FragColor = vec4(vec3(roughness), 1.0);
        return;
    }
    if (u_debug_mode == 4) {
        gl_FragColor = vec4(vec3(metallic), 1.0);
        return;
    }
    if (u_debug_mode == 5) {
        gl_FragColor = vec4(vec3(ao), 1.0);
        return;
    }

    vec3 V = Vpre;
    vec3 col = vec3(0.0);
    for (int i = 0; i < 5; i++) {
        if (u_light_on[i] > 0.5) {
            col += shadeLight(N, V, normalize(u_lights[i]), albedo.rgb, roughness, metallic, u_light_rad[i]);
        }
    }
    if (u_moon_on > 0.5) {
        col += shadeLight(N, V, normalize(u_moon_dir), albedo.rgb, roughness, metallic, u_moon_rad);
    }
    for (int i = 0; i < 64; i++) {
        if (i >= u_lamp_count) break;
        if (u_lamp_power[i] < 1e-4) continue;
        col += shadeLamp(
            N, V, v_world,
            u_lamp_pos[i], u_lamp_col[i], u_lamp_power[i], u_lamp_range[i],
            u_lamp_mode[i], u_lamp_dir[i], u_lamp_cone[i],
            albedo.rgb, roughness, metallic,
            i
        );
    }
    // IBL — roughness-warped reflection + Fresnel (HDRI or procedural softbox)
    float ndv = max(dot(N, V), 0.0);
    float specF0 = 0.04 * (u_mat_edit > 0.5 ? max(u_edit_specular, 0.0) : 1.0);
    vec3 F0 = mix(vec3(specF0), albedo.rgb, metallic);
    vec3 F = fresnelSchlick(ndv, F0);
    vec3 R = reflect(-V, N);
    R = normalize(mix(R, N, roughness * roughness * 0.55));
    vec3 iblSpec = sampleEnv(R, roughness);
    vec3 iblDiff = sampleEnv(N, 0.92);
    float iblMul = (u_moon_on > 0.5) ? 0.78 : 1.0;
    // Fuller GGX IBL — dielectrics keep punchy Fresnel, metals take albedo*F
    float specAmt = mix(1.15, 0.18, roughness * roughness);
    col += iblSpec * u_ibl_strength * iblMul * F * specAmt * ao;
    col += iblDiff * u_ibl_strength * 0.62 * iblMul * albedo.rgb * (1.0 - metallic) * (1.0 - F) * ao;
    vec3 ambient = vec3(u_ambient) * albedo.rgb * ao * 0.32;
    col += ambient + albedo.rgb * emissive * u_emissive_scale;
    float rim = 0.82 + 0.45 * pow(1.0 - ndv, 2.5);
    col += albedo.rgb * u_self_illum * rim;
    // Mild ACES-ish — keeps specular highlights instead of washing them
    col = clamp((col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14), 0.0, 1.0);
    col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
    gl_FragColor = vec4(col, 1.0);
}
"""

DEPTH_VERT = """
#version 120
attribute vec3 in_pos;
uniform mat4 u_mvp;
void main() {
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

DEPTH_FRAG = """
#version 120
void main() {
    // Hardware depth — do NOT pass z/w as a varying (perspective-correct interp breaks it).
    float d = gl_FragCoord.z;
    gl_FragColor = vec4(d, d, d, 1.0);
}
"""

LINE_VERT = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_col;
uniform mat4 u_mvp;
varying vec3 v_col;
void main() {
    v_col = in_col;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

LINE_FRAG = """
#version 120
varying vec3 v_col;
void main() {
    gl_FragColor = vec4(v_col, 1.0);
}
"""

# Soft lamp / selection glow — camera-facing disc, additive in paint
GLOW_VERT = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_col;
attribute vec2 in_uv;
uniform mat4 u_mvp;
varying vec3 v_col;
varying vec2 v_uv;
void main() {
    v_col = in_col;
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

GLOW_FRAG = """
#version 120
varying vec3 v_col;
varying vec2 v_uv;
void main() {
    vec2 d = v_uv * 2.0 - 1.0;
    float r2 = dot(d, d);
    if (r2 > 1.0) discard;
    // soft bulb: bright core + wide falloff
    float core = exp(-r2 * 9.0);
    float halo = exp(-r2 * 2.2) * 0.55;
    float a = core + halo;
    gl_FragColor = vec4(v_col * a, a);
}
"""

SKY_VERT = """
#version 120
attribute vec3 in_pos;
uniform mat4 u_mvp;
varying vec3 v_dir;
void main() {
    v_dir = in_pos;
    vec4 clip = u_mvp * vec4(in_pos, 1.0);
    gl_Position = clip.xyww;
}
"""

SKY_FRAG = """
#version 120
varying vec3 v_dir;
uniform sampler2D u_env_map;
uniform float u_use_env_map;
uniform vec3 u_sky_top;
uniform vec3 u_sky_horizon;
uniform vec3 u_sky_ground;
uniform float u_exposure;
// sun/moon are real meshes now — no analytic haze (was fogging env=none)

vec3 worldToYup(vec3 d) {
    return vec3(d.x, d.z, -d.y);
}

vec2 dirToEquirect(vec3 d) {
    vec3 y = worldToYup(normalize(d));
    float u = atan(y.z, y.x) * 0.15915494309 + 0.5;
    float v = asin(clamp(y.y, -1.0, 1.0)) * 0.31830988618 + 0.5;
    return vec2(u, 1.0 - v);
}

vec3 tonemapAces(vec3 x) {
    float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec3 d = normalize(v_dir);
    vec3 c;
    if (u_use_env_map > 0.5) {
        c = texture2D(u_env_map, dirToEquirect(d)).rgb;
        // slight contrast — no haze wash
        c = pow(max(c, vec3(0.0)), vec3(0.96));
    } else {
        float h = d.z;
        vec3 sky = mix(u_sky_horizon, u_sky_top, smoothstep(-0.02, 0.72, h));
        c = mix(u_sky_ground, sky, smoothstep(-0.45, 0.08, h));
        c = tonemapAces(c * u_exposure);
        c = pow(c, vec3(1.0 / 2.2));
    }
    gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""

# Unit cube for equirect skybox (pos only)
_SKY_CUBE = np.asarray(
    [
        # +X
        [1, -1, -1], [1, -1, 1], [1, 1, 1], [1, -1, -1], [1, 1, 1], [1, 1, -1],
        # -X
        [-1, -1, 1], [-1, -1, -1], [-1, 1, -1], [-1, -1, 1], [-1, 1, -1], [-1, 1, 1],
        # +Y
        [-1, 1, -1], [1, 1, -1], [1, 1, 1], [-1, 1, -1], [1, 1, 1], [-1, 1, 1],
        # -Y
        [-1, -1, 1], [1, -1, 1], [1, -1, -1], [-1, -1, 1], [1, -1, -1], [-1, -1, -1],
        # +Z
        [-1, -1, 1], [-1, 1, 1], [1, 1, 1], [-1, -1, 1], [1, 1, 1], [1, -1, 1],
        # -Z
        [1, -1, -1], [1, 1, -1], [-1, 1, -1], [1, -1, -1], [-1, 1, -1], [-1, -1, -1],
    ],
    dtype=np.float32,
)


def _configure_gl_format() -> None:
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setSamples(0)  # MSAA + huge mesh = jank on macOS
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    fmt.setSwapInterval(1)  # vsync — smooth orbit (0 = uncapped, tears)
    QSurfaceFormat.setDefaultFormat(fmt)


_configure_gl_format()


def _look_at_mat(eye: np.ndarray, center: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = center - eye
    f = f / (np.linalg.norm(f) + 1e-12)
    s = np.cross(f, up)
    sn = np.linalg.norm(s)
    if sn < 1e-12:
        s = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    else:
        s = s / sn
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float64)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    t = np.eye(4, dtype=np.float64)
    t[0, 3] = -eye[0]
    t[1, 3] = -eye[1]
    t[2, 3] = -eye[2]
    return (m @ t).astype(np.float32)


def _perspective_mat(fovy_deg: float, aspect: float, znear: float, zfar: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / max(aspect, 1e-6)
    m[1, 1] = f
    m[2, 2] = (zfar + znear) / (znear - zfar)
    m[2, 3] = (2.0 * zfar * znear) / (znear - zfar)
    m[3, 2] = -1.0
    return m


# Full-frame 24mm sensor height → focal length (mm) ↔ vertical FOV
_SENSOR_H_MM = 24.0
_FOCAL_MM_MIN = 12.0
_FOCAL_MM_MAX = 400.0
# ≈ previous fixed 45° fovy: 24 / (2*tan(22.5°)) ≈ 28.97
_DEFAULT_FOCAL_MM = 29.0


def _focal_mm_to_fovy(focal_mm: float) -> float:
    f = max(float(focal_mm), 1e-3)
    return math.degrees(2.0 * math.atan(_SENSOR_H_MM / (2.0 * f)))


def ease_out_cubic(u: float) -> float:
    """0..1 → eased 0..1 (fast start, soft settle)."""
    t = 0.0 if u < 0.0 else (1.0 if u > 1.0 else float(u))
    return 1.0 - (1.0 - t) ** 3


def format_fps_hud_text(
    paints: Sequence[float],
    walls: Sequence[float],
    frame_id: int,
    *,
    idle: bool = False,
) -> str:
    """Plain-text F3 HUD body (glass chip — never QPainter into the GL FBO)."""
    if not paints:
        return ""
    paint_cur = paints[-1]
    paint_avg = sum(paints) / len(paints)
    paint_min = min(paints)
    paint_max = max(paints)
    if walls:
        wall_cur = walls[-1]
        wall_avg = sum(walls) / len(walls)
        fps_cur = 1000.0 / max(wall_cur, 1e-3)
        fps_avg = 1000.0 / max(wall_avg, 1e-3)
    else:
        fps_cur = fps_avg = 1000.0 / max(paint_cur, 1e-3)
    tail = f"#{frame_id}"
    if idle:
        tail = f"{tail}  idle"
    return "\n".join(
        (
            f"{fps_cur:5.1f} fps  {paint_cur:5.1f} ms",
            f"avg {fps_avg:5.1f}  {paint_avg:5.1f} ms  ({paint_min:.0f}–{paint_max:.0f})",
            tail,
        )
    )


def fps_hud_top_right(
    host_w: int,
    chip_w: int,
    *,
    margin: int = 12,
    dock_left: int | None = None,
    left_min: int = 12,
    top: int = 10,
) -> tuple[int, int]:
    """Top-right of the clear viewport, in the chip parent's coordinates.

    ``dock_left`` is the Editor sidebar's left edge, or None when it is shut.
    ponytail: a clear strip narrower than the chip clamps to ``left_min`` and
    can tuck under the dock. Upgrade path is a smaller chip, not overlap logic.
    """
    right = int(host_w) - int(margin)
    if dock_left is not None:
        right = min(right, int(dock_left) - int(margin))
    x = right - int(chip_w)
    if x < int(left_min):
        x = int(left_min)
    return x, int(top)


class FpsHudChip(QFrame):
    """Glass frame-stats chip. Parent is the center host, never the GL widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fpsHud")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setProperty("glassDark", True)
        self._text = ""
        self._font = QFont()
        self._font.setFamilies(["Cascadia Mono", "Consolas", "Courier New"])
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPixelSize(12)
        self.setFont(self._font)
        self.hide()

    def hud_text(self) -> str:
        return self._text

    def set_hud_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        fm = QFontMetrics(self._font)
        lines = text.split("\n") if text else [""]
        tw = max((fm.horizontalAdvance(line) for line in lines), default=0)
        th = fm.lineSpacing() * max(1, len(lines))
        self.setFixedSize(tw + 28, th + 22)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        paint_glass_chip(self, radius=14.0)
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        if glass_is_dark(self):
            painter.setPen(QColor(120, 255, 168))
        else:
            painter.setPen(QColor(18, 92, 52))
        painter.drawText(
            self.rect().adjusted(14, 8, -12, -12),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._text,
        )


def aabb_wire_lines(
    mins: np.ndarray,
    maxs: np.ndarray,
    color: tuple[float, float, float] = (1.0, 0.55, 0.18),
) -> np.ndarray:
    """12-edge AABB as Nx6 float32 rows (xyz + rgb) for `_draw_lines`."""
    x0, y0, z0 = (float(v) for v in mins)
    x1, y1, z1 = (float(v) for v in maxs)
    r, g, b = color
    corners = (
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    )
    edges = (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    )
    rows: list[list[float]] = []
    for a, b_i in edges:
        ax, ay, az = corners[a]
        bx, by, bz = corners[b_i]
        rows.append([ax, ay, az, r, g, b])
        rows.append([bx, by, bz, r, g, b])
    return np.asarray(rows, dtype=np.float32)


def _flatten_part(part: MeshPart, tri_budget: int) -> DrawBatch | None:
    """Indexed DrawBatch: unique interleaved verts + uint32 indices (Trainz topology).

    Same pixels as expanded triangle-soup, ~2–3× less vertex bandwidth on GPU.
    Only thin if over the soft budget — keep contiguous triangle runs.
    """
    v = part.vertices.astype(np.float32, copy=False)
    idx = part.indices.astype(np.int64, copy=False)
    n_tris = len(idx) // 3
    if n_tris <= 0 or v.shape[0] <= 0:
        return None
    if n_tris > tri_budget and tri_budget > 0:
        # ponytail: keep first N contiguous tris — ugly but not streak-shredded.
        idx = idx.reshape(-1, 3)[:tri_budget].reshape(-1)

    n_verts = int(v.shape[0])
    if part.normals is not None and part.normals.shape[0] == n_verts:
        nrm = part.normals.astype(np.float32, copy=False)
    else:
        nrm = np.zeros((n_verts, 3), dtype=np.float32)
        tri = idx.reshape(-1, 3)
        a = v[tri[:, 0]]
        b = v[tri[:, 1]]
        c = v[tri[:, 2]]
        fn = np.cross(b - a, c - a)
        np.add.at(nrm, tri[:, 0], fn)
        np.add.at(nrm, tri[:, 1], fn)
        np.add.at(nrm, tri[:, 2], fn)
        lens = np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        nrm = (nrm / lens).astype(np.float32)
    if part.uvs is not None and part.uvs.shape[0] == n_verts:
        uv = part.uvs.astype(np.float32, copy=False)
    else:
        uv = np.zeros((n_verts, 2), dtype=np.float32)

    interleaved = np.empty((n_verts, 8), dtype=np.float32)
    interleaved[:, 0:3] = v
    interleaved[:, 3:6] = nrm
    interleaved[:, 6:8] = uv
    alb = part.albedo_path
    nrm_p = part.normal_path
    prm = part.parameter_path
    return DrawBatch(
        verts=np.ascontiguousarray(interleaved),
        indices=np.ascontiguousarray(idx, dtype=np.uint32),
        color=part.color,
        albedo=alb,
        normal=nrm_p,
        parameter=prm,
        name=part.name,
        albedo_ref=part.albedo_ref or "",
        normal_ref=part.normal_ref or "",
        parameter_ref=part.parameter_ref or "",
        material_type=part.material_type or "",
        mesh_key=part.mesh_key or "",
        two_sided=bool(getattr(part, "two_sided", False)),
        has_albedo=_path_is_file(alb),
        has_normal=_path_is_file(nrm_p),
        has_parameter=_path_is_file(prm),
    )


def _load_rgba(path: str | Path, *, flip_v: bool = False) -> tuple[int, int, bytes]:
    """Load RGBA for OpenGL — disk precache + preview downsample (see texcache)."""
    from ..io.texcache import load_rgba

    return load_rgba(path, flip_v=flip_v)


def _placeholder_rgba(rgb: tuple[int, int, int] = (170, 175, 185)) -> tuple[int, int, bytes]:
    r, g, b = rgb
    pix = bytes((r, g, b, 255))
    return 4, 4, pix * 16


def _is_onetex(material_type: str) -> bool:
    mt = material_type.lower()
    return "onetex" in mt or "stdonetex" in mt


def horizontal_walk_dirs(
    look: np.ndarray, right: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Camera walk on the XY ground. Trainz is Z-up — flatten Z, keep Y.

    Up/Down follow ``look`` on XY (forward / back). Left/Right follow ``right``
    on XY (strafe). Flattening Y instead sends Up into XZ.
    """
    forward = np.array([float(look[0]), float(look[1]), 0.0], dtype=np.float64)
    fl = float(np.linalg.norm(forward))
    if fl < 1e-8:
        # Looking straight up/down: yaw is lost in the look vector.
        forward = np.array([0.0, -1.0, 0.0], dtype=np.float64)
    else:
        forward /= fl
    right_h = np.array([float(right[0]), float(right[1]), 0.0], dtype=np.float64)
    rl = float(np.linalg.norm(right_h))
    if rl > 1e-8:
        right_h /= rl
    else:
        right_h = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    return forward, right_h


def screen_delta_to_world(
    dx_px: float,
    dy_px: float,
    *,
    dist: float,
    right: np.ndarray,
    up: np.ndarray,
    fine: bool = False,
    scale: float = 0.0016,
) -> np.ndarray:
    """Map screen drag (pixels) onto the camera plane. fine/Shift = 0.1×.

    dy is screen-down positive (Qt); world delta uses camera up (−dy).
    """
    s = float(dist) * float(scale) * (0.1 if fine else 1.0)
    return np.asarray(right, dtype=np.float64) * (dx_px * s) + np.asarray(
        up, dtype=np.float64
    ) * (-dy_px * s)


def screen_delta_along_axis(
    dx_px: float,
    dy_px: float,
    axis: np.ndarray,
    *,
    dist: float,
    right: np.ndarray,
    up: np.ndarray,
    fine: bool = False,
    scale: float = 0.0016,
) -> np.ndarray:
    """Constrain screen drag to a world axis (Blender translate handle)."""
    ax = np.asarray(axis, dtype=np.float64).reshape(3)
    al = float(np.linalg.norm(ax))
    if al < 1e-9:
        return np.zeros(3, dtype=np.float64)
    ax = ax / al
    # axis as seen on screen (y down)
    sx = float(np.dot(ax, np.asarray(right, dtype=np.float64)))
    sy = float(-np.dot(ax, np.asarray(up, dtype=np.float64)))
    sl = (sx * sx + sy * sy) ** 0.5
    if sl < 1e-6:
        return np.zeros(3, dtype=np.float64)
    sx /= sl
    sy /= sl
    t = float(dx_px) * sx + float(dy_px) * sy
    s = float(dist) * float(scale) * (0.1 if fine else 1.0)
    return ax * (t * s)


def project_world_to_screen(
    mvp: np.ndarray,
    pos: tuple[float, float, float] | np.ndarray,
    width: float,
    height: float,
) -> tuple[float, float, float] | None:
    """World → Qt widget coords (y down) + clip depth. None if behind camera."""
    v = np.asarray(mvp, dtype=np.float64) @ np.array(
        [float(pos[0]), float(pos[1]), float(pos[2]), 1.0], dtype=np.float64
    )
    if abs(float(v[3])) < 1e-9:
        return None
    ndc = v[:3] / v[3]
    if float(ndc[2]) < -1.0 or float(ndc[2]) > 1.0:
        return None
    sx = (float(ndc[0]) * 0.5 + 0.5) * float(width)
    sy = (1.0 - (float(ndc[1]) * 0.5 + 0.5)) * float(height)
    return sx, sy, float(ndc[2])


def _dist_point_to_segment_2d(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Pixel distance from point to segment AB."""
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-12:
        return (apx * apx + apy * apy) ** 0.5
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    qx, qy = ax + abx * t, ay + aby * t
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def pick_translate_handle(
    att: Attachment,
    mvp: np.ndarray,
    sx: float,
    sy: float,
    width: float,
    height: float,
    *,
    dist: float = 20.0,
    free_radius_px: float = 14.0,
    axis_radius_px: float = 10.0,
) -> str | None:
    """Pick Blender-style translate handle: ``\"free\"`` | ``\"x\"`` | ``\"y\"`` | ``\"z\"`` | None."""
    origin = project_world_to_screen(mvp, att.pos, width, height)
    if origin is None:
        return None
    ox, oy, _oz = origin
    d_free = ((sx - ox) ** 2 + (sy - oy) ** 2) ** 0.5
    if d_free <= float(free_radius_px):
        return "free"
    axis_len = gizmo_axis_length(dist, selected=True, move_mode=True)
    ends = att.axes_end(axis_len)
    best: str | None = None
    best_d = 1e9
    tip_r = float(axis_radius_px) * 1.45  # cone head is easier to grab
    ax_r = float(axis_radius_px)
    for key, end in zip(("x", "y", "z"), ends):
        hit = project_world_to_screen(mvp, end, width, height)
        if hit is None:
            continue
        ex, ey, _ez = hit
        d_seg = _dist_point_to_segment_2d(sx, sy, ox, oy, ex, ey)
        if d_seg <= ax_r and d_seg < best_d:
            best_d = d_seg
            best = key
        d_tip = ((sx - ex) ** 2 + (sy - ey) ** 2) ** 0.5
        if d_tip <= tip_r and d_tip < best_d:
            best_d = d_tip
            best = key
    return best


def pick_attachment_index(
    attachments: list[Attachment],
    mvp: np.ndarray,
    sx: float,
    sy: float,
    width: float,
    height: float,
    *,
    radius_px: float = 22.0,
    skip_index: set[int] | frozenset[int] | None = None,
) -> int:
    """Nearest a.* under cursor within ``radius_px``. -1 if none."""
    best_i = -1
    best_d2 = float(radius_px) ** 2
    best_z = 1e9
    skip = skip_index or ()
    for i, att in enumerate(attachments):
        if i in skip:
            continue
        hit = project_world_to_screen(mvp, att.pos, width, height)
        if hit is None:
            continue
        px, py, z = hit
        d2 = (px - sx) ** 2 + (py - sy) ** 2
        if d2 <= best_d2 and (d2 < best_d2 - 1e-6 or z < best_z):
            best_d2 = d2
            best_z = z
            best_i = i
    return best_i


def gizmo_axis_length(
    dist: float, *, selected: bool = False, move_mode: bool = False
) -> float:
    """Shared shaft+tip length so draw and pick stay in sync."""
    axis_len = max(float(dist) * (0.07 if move_mode else 0.04), 0.15)
    if selected:
        axis_len *= 1.35
    if move_mode:
        axis_len *= 1.15
    return float(axis_len)


# Blender-ish translate: shaft ends before the cone tip
_GIZMO_SHAFT_FRAC = 0.78
_GIZMO_TIP_FRAC = 0.22


def _gizmo_axis_colors(
    *, selected: bool, move_mode: bool
) -> tuple[tuple[float, float, float], ...]:
    if move_mode and selected:
        return (
            (0.95, 0.22, 0.22),
            (0.28, 0.92, 0.32),
            (0.28, 0.48, 0.98),
        )
    if selected:
        return (
            (1.0, 0.55, 0.2),
            (0.55, 1.0, 0.35),
            (0.45, 0.7, 1.0),
        )
    return (
        (1.0, 0.35, 0.35),
        (0.35, 1.0, 0.45),
        (0.4, 0.55, 1.0),
    )


def _perp_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(axis, dtype=np.float64).reshape(3)
    n = float(np.linalg.norm(a)) or 1.0
    a = a / n
    helper = (
        np.array([0.0, 1.0, 0.0], dtype=np.float64)
        if abs(float(a[1])) < 0.9
        else np.array([1.0, 0.0, 0.0], dtype=np.float64)
    )
    u = np.cross(a, helper)
    un = float(np.linalg.norm(u)) or 1.0
    u = u / un
    v = np.cross(a, u)
    return u, v


def _arrow_cone_tris(
    tip: np.ndarray,
    axis: np.ndarray,
    tip_len: float,
    tip_r: float,
    color: tuple[float, float, float],
    *,
    sides: int = 10,
) -> np.ndarray:
    """Pyramid/cone pointing along ``axis``; apex at ``tip``."""
    a = np.asarray(axis, dtype=np.float64).reshape(3)
    n = float(np.linalg.norm(a)) or 1.0
    a = a / n
    tip = np.asarray(tip, dtype=np.float64).reshape(3)
    base_c = tip - a * float(tip_len)
    u, v = _perp_basis(a)
    ring: list[np.ndarray] = []
    for i in range(sides):
        t = (2.0 * math.pi * i) / sides
        ring.append(base_c + (u * math.cos(t) + v * math.sin(t)) * float(tip_r))
    cr, cg, cb = color
    rows: list[list[float]] = []
    # side fans
    for i in range(sides):
        p0 = ring[i]
        p1 = ring[(i + 1) % sides]
        for p in (tip, p0, p1):
            rows.append([float(p[0]), float(p[1]), float(p[2]), cr, cg, cb])
    # base disc (flat back — reads as solid tip)
    dim = (cr * 0.55, cg * 0.55, cb * 0.55)
    for i in range(sides):
        p0 = ring[i]
        p1 = ring[(i + 1) % sides]
        for p, col in ((base_c, dim), (p1, dim), (p0, dim)):
            rows.append(
                [float(p[0]), float(p[1]), float(p[2]), col[0], col[1], col[2]]
            )
    return np.asarray(rows, dtype=np.float32)


def _center_cube_tris(
    center: np.ndarray, half: float, color: tuple[float, float, float]
) -> np.ndarray:
    """Axis-aligned cube (Blender free-move handle)."""
    c = np.asarray(center, dtype=np.float64).reshape(3)
    h = float(half)
    # 8 corners
    corners = [
        c + np.array([sx * h, sy * h, sz * h], dtype=np.float64)
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
        for sz in (-1.0, 1.0)
    ]
    # face indices into corners list (sx,sy,sz nested)
    # order: (-,-,-)=0 (-,-,+)=1 (-,+,-)=2 (-,+,+)=3 (+,-,-)=4 (+,-,+)=5 (+,+,-)=6 (+,+,+)=7
    faces = (
        (0, 1, 3, 2),  # -X
        (4, 6, 7, 5),  # +X
        (0, 4, 5, 1),  # -Y
        (2, 3, 7, 6),  # +Y
        (0, 2, 6, 4),  # -Z
        (1, 5, 7, 3),  # +Z
    )
    cr, cg, cb = color
    # slight face shading so the cube reads 3D without lights
    shades = (0.72, 0.95, 0.78, 1.0, 0.65, 0.88)
    rows: list[list[float]] = []
    for fi, (i0, i1, i2, i3) in enumerate(faces):
        s = shades[fi]
        col = (cr * s, cg * s, cb * s)
        for a, b, c3 in ((i0, i1, i2), (i0, i2, i3)):
            for idx in (a, b, c3):
                p = corners[idx]
                rows.append(
                    [float(p[0]), float(p[1]), float(p[2]), col[0], col[1], col[2]]
                )
    return np.asarray(rows, dtype=np.float32)


def attachment_gizmo_lines(
    att: Attachment,
    *,
    selected: bool = False,
    move_mode: bool = False,
    dist: float = 20.0,
) -> np.ndarray:
    """RGB axis shafts. Arrow cones / center cube come from ``attachment_gizmo_solids``.

    ``move_mode`` (Editor Move): longer Blender-style translate handles.
    """
    ox, oy, oz = float(att.pos[0]), float(att.pos[1]), float(att.pos[2])
    axis_len = gizmo_axis_length(dist, selected=selected, move_mode=move_mode)
    # shaft stops where the cone begins (move) or full length (view)
    shaft_len = axis_len * (_GIZMO_SHAFT_FRAC if (move_mode and selected) else 1.0)
    ex, ey, ez = att.axes_end(shaft_len)
    (rx, gx, bx), (ry, gy, by), (rz, gz, bz) = _gizmo_axis_colors(
        selected=selected, move_mode=move_mode
    )
    return np.asarray(
        [
            [ox, oy, oz, rx, gx, bx],
            [float(ex[0]), float(ex[1]), float(ex[2]), rx, gx, bx],
            [ox, oy, oz, ry, gy, by],
            [float(ey[0]), float(ey[1]), float(ey[2]), ry, gy, by],
            [ox, oy, oz, rz, gz, bz],
            [float(ez[0]), float(ez[1]), float(ez[2]), rz, gz, bz],
        ],
        dtype=np.float32,
    )


def attachment_gizmo_solids(
    att: Attachment,
    *,
    selected: bool = False,
    move_mode: bool = False,
    dist: float = 20.0,
) -> np.ndarray:
    """Solid arrow cones + center cube — Editor Move only (Nx6 pos+rgb)."""
    if not (selected and move_mode):
        return np.zeros((0, 6), dtype=np.float32)
    axis_len = gizmo_axis_length(dist, selected=True, move_mode=True)
    tip_len = axis_len * _GIZMO_TIP_FRAC
    tip_r = tip_len * 0.42
    tips = att.axes_end(axis_len)
    m = np.asarray(att.orient, dtype=np.float64).reshape(3, 3)
    colors = _gizmo_axis_colors(selected=True, move_mode=True)
    chunks: list[np.ndarray] = []
    for tip, axis, col in zip(tips, (m[0], m[1], m[2]), colors):
        chunks.append(_arrow_cone_tris(tip, axis, tip_len, tip_r, col))
    half = max(float(dist) * 0.012, 0.03) * 1.25
    chunks.append(
        _center_cube_tris(
            np.asarray(att.pos, dtype=np.float64), half, (0.95, 0.95, 0.97)
        )
    )
    return np.vstack(chunks)


def glow_billboard_mesh(
    centers: np.ndarray,
    colors: np.ndarray,
    radii: np.ndarray,
    right: np.ndarray,
    up: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Camera-facing quads → interleaved pos/col/uv + triangle indices.

    centers Nx3, colors Nx3, radii N. Returns (verts Nx8 float32, idx uint32).
    """
    n = int(centers.shape[0])
    if n <= 0:
        return np.zeros((0, 8), dtype=np.float32), np.zeros((0,), dtype=np.uint32)
    rgt = np.asarray(right, dtype=np.float64).reshape(3)
    upp = np.asarray(up, dtype=np.float64).reshape(3)
    rn = float(np.linalg.norm(rgt)) or 1.0
    un = float(np.linalg.norm(upp)) or 1.0
    rgt = rgt / rn
    upp = upp / un
    verts = np.zeros((n * 4, 8), dtype=np.float32)
    # corner offsets in UV: (0,0) (1,0) (1,1) (0,1)
    corners = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for i in range(n):
        c = centers[i].astype(np.float64)
        rad = float(radii[i])
        col = colors[i]
        for k, ((sx, sy), (u, v)) in enumerate(zip(corners, uvs)):
            p = c + rgt * (sx * rad) + upp * (sy * rad)
            row = verts[i * 4 + k]
            row[0:3] = p
            row[3:6] = col
            row[6] = u
            row[7] = v
    idx = np.empty(n * 6, dtype=np.uint32)
    for i in range(n):
        b = i * 4
        t = i * 6
        idx[t : t + 6] = (b, b + 1, b + 2, b, b + 2, b + 3)
    return verts, idx


class MeshView(QOpenGLWidget):
    """3D mesh preview. Signals fire while dragging a selected a.* in the viewport."""

    attachment_moved = Signal(int, float, float, float)
    attachment_drag_started = Signal(int)  # LMB drag begin on selected a.*
    attachment_drag_finished = Signal(int, float, float, float)
    attachment_picked = Signal(int)  # Alt+LMB click on a.* in viewport

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = Scene()
        self._yaw = 35.0
        self._pitch = 25.0
        self._dist = 20.0
        self._target = np.zeros(3, dtype=np.float64)
        self._home_yaw = 35.0
        self._home_pitch = 25.0
        self._home_dist = 20.0
        self._home_target = np.zeros(3, dtype=np.float64)
        self._focal_mm = _DEFAULT_FOCAL_MM
        self._home_focal_mm = _DEFAULT_FOCAL_MM
        self._yaw_vel = 0.0
        self._pitch_vel = 0.0
        self._zoom_vel = 0.0  # wheel dolly inertia (multiplicative per tick)
        self._focal_vel = 0.0  # Ctrl+wheel lens FOV inertia
        self._pan_vel = np.zeros(3, dtype=np.float64)
        self._last: QPoint | None = None
        self._keys_down: set[int] = set()
        self._cam_timer = QTimer(self)
        self._cam_timer.setInterval(16)  # ~60fps damp + keyboard move
        self._cam_timer.timeout.connect(self._tick_camera)
        self._cam_timer.start()
        # ponytail: never drop below 16ms while visible — 33ms idle made orbit feel steppy
        self._render_active = True
        # True while camera inertia / drag / fly — frost/outline skip only (not lighting).
        self._cam_busy = False
        self._lloc: dict | None = None  # line/colored-tri program locs
        self._grid_cache: np.ndarray | None = None
        self._celestial_key: tuple | None = None
        self._sun_body_local: np.ndarray | None = None
        self._sun_glow_local: np.ndarray | None = None
        self._moon_body_local: np.ndarray | None = None
        self._mat_edge_cache: np.ndarray | None = None
        self._mat_edge_key: tuple | None = None
        self._mat_edge_vbo: int | None = None
        self._mat_edge_count = 0
        # fly-to attachment (ease-out lerp of target + dist)
        self._fly_active = False
        self._fly_t0 = 0.0
        self._fly_dur = 0.55
        self._fly_from_tgt = np.zeros(3, dtype=np.float64)
        self._fly_to_tgt = np.zeros(3, dtype=np.float64)
        self._fly_from_dist = 20.0
        self._fly_to_dist = 20.0
        # Highlight ≠ edit: Preview/View selects/glows only; Move enables gizmo drag
        self._sel_att_index = -1
        self._edit_att_index = -1
        self._att_dragging = False
        self._att_drag_axis = "free"  # free | x | y | z
        self._alt_pick_armed = False  # Alt+LMB hit an a.* — suppress orbit for gesture
        self._show_axes = True
        self._show_grid = True
        self._show_atts = True
        self._show_corner_gizmo = True
        self._show_fps = False
        self._fps_suppressed = False
        self._fps_idle_shown = False
        self._frame_id = 0
        self._fps_last_t = 0.0
        self._fps_paint_ms: deque[float] = deque(maxlen=90)
        self._fps_wall_ms: deque[float] = deque(maxlen=90)
        # host_w, dock_left, left_min, top, margin — set by the main window
        self._fps_place: tuple[int, int | None, int, int, int] | None = None
        self._fps_host_hook = None
        # Glass chip starts here only so it exists before the center host does.
        # Main window reparents it off this QOpenGLWidget (child widgets over GL hitch).
        self._fps_chip = FpsHudChip(self)
        self._batches: list[DrawBatch] = []
        # filter: "all" shows every part with its own maps; "selected" hides non-matches
        self._tex_filter_mode = "all"
        self._tex_filter_stems: set[str] = set()
        self._tex_filter_mesh_keys: set[str] = set()
        # Scene "Meshes in scene" Show column — unchecked file names stay GPU-hidden
        self._hidden_mesh_keys: set[str] = set()
        # Scene Atts column — unchecked mesh keys hide that file's a.* gizmos
        self._hidden_att_mesh_keys: set[str] = set()
        # Mat list / Meshes list / Meshes-in-scene → orange outline
        self._highlight_stems: set[str] = set()
        self._highlight_mesh_keys: set[str] = set()
        self._highlight_names: set[str] = set()
        # optional: force one albedo image onto batches whose stems match (not whole mesh)
        self._albedo_force: str | None = None
        self._albedo_force_stems: set[str] = set()
        # optional: boost self-illum on matching stems (Preview as Self-Illum)
        self._self_illum_stems: set[str] | None = None
        self._self_illum_boost = 0.55
        self._lamp_glow: dict[str, float] = {}
        self._debug_mode = 0
        self._face_orient = False  # Blender Face Orientation overlay
        self._shading = SHADING_RENDERED
        self._lit_uniforms_dirty = True  # lamp/sun/env packs — skip re-upload while orbiting
        self._env: EnvPreset = get_env("none")
        self._show_ground = False
        self._env_sky: np.ndarray | None = None
        self._env_ground: np.ndarray | None = None
        self._env_extra: np.ndarray | None = None
        self._env_cache_key: tuple | None = None
        self._ibl_strength = 0.85
        self._lamp_pack = pack_for_gpu([])
        self._moon_on = False
        self._moon_intensity = 0.45
        self._show_lamp_gizmos = True
        # Markers for gizmo crosses only — soft glow sprites = enabled lamps only
        self._lamp_markers: list[tuple[tuple[float, float, float], tuple[float, float, float], bool, float, float]] = []
        self._anim_time = 0.0
        self._light_on = [True, True, True, True, True]  # L R F B top
        self._ambient = 0.14
        self._move_vel = np.zeros(3, dtype=np.float64)  # walk (arrows)
        self._elev_vel = 0.0  # PgUp/Dn + MMB vertical
        self._emissive_scale = DEFAULT_EMISSIVE_SCALE
        # Editor → Texture Material preview (selected family stems only)
        self._mat_edit_stems: set[str] = set()
        self._mat_edit_on = False
        self._edit_emissive = 0.0
        self._edit_rough = 0.55
        self._edit_metal = 0.0
        self._edit_specular = 1.0
        self._sun_enabled = False
        self._sun_az = 135.0
        self._sun_el = 45.0
        self._sun_intensity = 1.4
        self._clear_rgb = (0.16, 0.19, 0.22)
        self._flip_texture_v = False  # Trainz/D3D raw V + unflipped PIL upload
        self._prog = None
        self._line_prog = None
        self._glow_prog = None
        self._sky_prog = None
        self._depth_prog = None
        self._dloc: dict | None = None  # depth-pass uniform/attrib locs
        self._shadow_fbo: int | None = None
        self._shadow_tex: int | None = None
        self._shadow_rb: int | None = None
        self._shadow_count = 0
        self._shadow_vp = np.zeros((MAX_SHADOW_LAMPS, 4, 4), dtype=np.float32)
        self._shadow_dirty = True
        self._shadow_build_i = 0
        self._uloc: dict | None = None
        self._hdri_tex: int | None = None
        self._hdri_key: str | None = None
        self._use_hdri = False
        self._pending_hdri_path: str | None = None
        self._hdri_sun_hint: tuple[float, float] | None = None  # (az, el) from peak
        self._sky_exposure = 1.15
        self._tex_cache: dict[str, int] = {}
        self._tex_missing: set[str] = set()  # known-absent paths — skip is_file in paint
        self._decoded_cache: dict[str, tuple[int, int, bytes]] = {}
        self._tex_uploads_left = TEX_UPLOADS_PER_FRAME
        self._tex_burst_frames = 0
        self._need_tex_pass = False
        self._placeholder_tex: int | None = None
        self._flat_normal_tex: int | None = None
        self._flat_param_tex: int | None = None
        self._gl_ready = False
        self.setMinimumSize(480, 360)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        # Full repaint — PartialUpdate + continuous cam timer = composite hitch on Win
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

    def set_scene(self, scene: Scene) -> None:
        self._cancel_fly()
        self._scene = scene
        self._albedo_force = None
        self._albedo_force_stems.clear()
        self._self_illum_stems = None
        self._tex_filter_mode = "all"
        self._tex_filter_stems.clear()
        self._tex_filter_mesh_keys.clear()
        self._hidden_mesh_keys.clear()
        self._hidden_att_mesh_keys.clear()
        self._highlight_stems.clear()
        self._highlight_mesh_keys.clear()
        self._highlight_names.clear()
        self._lamp_markers = []
        self._anim_time = 0.0
        self._rebuild_batches()
        # Keep CPU-decoded precache seeded by LoadWorker (was wiped every open).
        self._purge_textures(keep_decoded=True)
        b = scene.bounds()
        if b is not None:
            mins, maxs = b
            self._target = (mins + maxs) * 0.5
            extent = float(np.linalg.norm(maxs - mins)) or 1.0
            self._dist = max(extent * 1.4, 1.0)
        elif scene.attachments:
            pts = np.asarray([a.pos for a in scene.attachments], dtype=np.float64)
            self._target = pts.mean(axis=0)
            span = float(np.linalg.norm(pts.max(0) - pts.min(0)))
            self._dist = max(span * 1.4, 2.0)
        self._yaw = 35.0
        self._pitch = 25.0
        self._focal_mm = _DEFAULT_FOCAL_MM
        self._yaw_vel = 0.0
        self._pitch_vel = 0.0
        self._zoom_vel = 0.0
        self._focal_vel = 0.0
        self._pan_vel = np.zeros(3, dtype=np.float64)
        self._move_vel = np.zeros(3, dtype=np.float64)
        self._elev_vel = 0.0
        self._env_cache_key = None
        self._shadow_dirty = True
        self._shadow_build_i = 0
        self._sel_att_index = -1
        self._edit_att_index = -1
        self._att_dragging = False
        self._att_drag_axis = "free"
        self.unsetCursor()
        self._store_home()
        self.update()

    def _store_home(self) -> None:
        self._home_yaw = float(self._yaw)
        self._home_pitch = float(self._pitch)
        self._home_dist = float(self._dist)
        self._home_focal_mm = float(self._focal_mm)
        self._home_target = np.array(self._target, dtype=np.float64, copy=True)

    def reset_camera(self) -> None:
        self._cancel_fly()
        self._yaw = self._home_yaw
        self._pitch = self._home_pitch
        self._dist = self._home_dist
        self._focal_mm = self._home_focal_mm
        self._target = np.array(self._home_target, dtype=np.float64, copy=True)
        self._yaw_vel = 0.0
        self._pitch_vel = 0.0
        self._zoom_vel = 0.0
        self._focal_vel = 0.0
        self._pan_vel = np.zeros(3, dtype=np.float64)
        self._move_vel = np.zeros(3, dtype=np.float64)
        self._elev_vel = 0.0
        self.update()

    def _cancel_fly(self) -> None:
        self._fly_active = False

    def fly_to(
        self,
        pos,
        *,
        duration_s: float = 0.55,
        approach: bool = True,
    ) -> None:
        """Ease-out fly: orbit target → pos; keep orbit distance steady.

        ``approach`` kept for callers; distance no longer shrinks with span
        (old cozy formula zoomed ~0.62× per nearby a.* click — jumpy).
        """
        dest = np.asarray(pos, dtype=np.float64).reshape(3)
        self._fly_from_tgt = np.array(self._target, dtype=np.float64, copy=True)
        self._fly_to_tgt = dest
        self._fly_from_dist = float(self._dist)
        # ponytail: keep dolly; only re-aim. Ceiling: no auto-frame if way out.
        self._fly_to_dist = fly_approach_dist(
            self._fly_from_dist, approach=approach
        )
        self._fly_dur = max(0.08, float(duration_s))
        self._fly_t0 = time.perf_counter()
        self._fly_active = True
        self._yaw_vel = 0.0
        self._pitch_vel = 0.0
        self._zoom_vel = 0.0
        self._focal_vel = 0.0
        self._pan_vel = np.zeros(3, dtype=np.float64)
        self._move_vel = np.zeros(3, dtype=np.float64)
        self._elev_vel = 0.0
        self.update()

    def set_selected_attachment(
        self, index: int | None, *, editable: bool = False
    ) -> None:
        """Highlight a.* (glow). ``editable=True`` (Editor Move) enables gizmo drag."""
        n = len(self._scene.attachments)
        if index is None or index < 0 or index >= n:
            self._sel_att_index = -1
            self._edit_att_index = -1
        else:
            self._sel_att_index = int(index)
            self._edit_att_index = int(index) if editable else -1
        self._att_dragging = False
        self._att_drag_axis = "free"
        if self._edit_att_index >= 0:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.unsetCursor()
        self.update()

    def set_edit_attachment(self, index: int | None) -> None:
        """Back-compat: select + enable drag (Editor). Prefer set_selected_attachment."""
        self.set_selected_attachment(index, editable=True)

    def seed_decoded_textures(self, decoded: dict[str, tuple[int, int, bytes]]) -> None:
        """CPU-decoded RGBA from LoadWorker — burst-upload across next frames."""
        self._decoded_cache.update(decoded)
        self._tex_burst_frames = TEX_BURST_FRAMES
        self._need_tex_pass = bool(decoded)
        self.update()

    def set_shading(self, mode: str) -> None:
        if mode not in (SHADING_WIRE, SHADING_SOLID, SHADING_MATERIAL, SHADING_RENDERED):
            mode = SHADING_RENDERED
        self._shading = mode
        if mode == SHADING_RENDERED:
            self._shadow_dirty = True
            self._shadow_build_i = 0
        self._lit_uniforms_dirty = True
        self.update()

    def set_environment(self, key: str) -> None:
        """key: HDRI asset id, procedural name, or 'none'."""
        from .hdri import list_hdri_assets

        self._env_cache_key = None
        self._hdri_sun_hint = None
        self._lit_uniforms_dirty = True
        hdri_map = {a.key: a for a in list_hdri_assets()}
        if key in hdri_map:
            self._use_hdri = True
            self._hdri_key = key
            self._env = get_env("studio")
            self._clear_rgb = (0.02, 0.02, 0.03)
            self._ambient = 0.10
            self._ibl_strength = 1.25
            self._load_hdri_texture(hdri_map[key].path)
        else:
            self._use_hdri = False
            self._hdri_key = None
            self._env = get_env(
                key
                if key in ("studio", "station", "harbor", "lake", "mountains", "none")
                else "none"
            )
            # clear/ambient only — never build procedural mesh sky/ground
            if self._env.key != "none":
                self._clear_rgb = self._env.clear
                self._ambient = min(self._env.ambient * 0.55, 0.22)
            else:
                self._ambient = 0.12
            # env=none still needs a real softbox so Lit PBR reads metal/glass
            self._ibl_strength = 0.72 if self._env.key == "none" else 0.45
        if self._gl_ready:
            r, g, b = self._clear_rgb
            GL.glClearColor(r, g, b, 1.0)
        self.update()

    def consume_hdri_sun_hint(self) -> tuple[float, float] | None:
        """Return (az, el) once after HDRI load — UI syncs sun sliders."""
        hint = self._hdri_sun_hint
        self._hdri_sun_hint = None
        return hint

    def _load_hdri_texture(self, path) -> None:
        from .hdri import load_hdri_rgba8

        if not self._gl_ready:
            self._pending_hdri_path = str(path)
            return
        try:
            w, h, pixels, meta = load_hdri_rgba8(path, max_w=2048)
        except Exception as e:
            print(f"trainz_studio: HDRI load failed {path}: {e}", flush=True)
            self._use_hdri = False
            return
        if self._hdri_tex is not None:
            GL.glDeleteTextures([self._hdri_tex])
        self._hdri_tex = self._make_texture(w, h, pixels)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._hdri_tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        # mip-ish feel via linear; wrap already set
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        self._pending_hdri_path = None
        if "sun_az" in meta and "sun_el" in meta:
            self._hdri_sun_hint = (float(meta["sun_az"]), float(meta["sun_el"]))
            # snap analytic sun to HDRI peak so disc + light match the map
            self._sun_az = float(meta["sun_az"])
            self._sun_el = float(np.clip(meta["sun_el"], -10.0, 89.0))
        if "exposure" in meta:
            self._sky_exposure = float(np.clip(1.0 + meta["exposure"] * 0.08, 0.9, 1.6))
        print(
            f"trainz_studio: HDRI {Path(path).name} "
            f"{w}x{h} exp={meta.get('exposure', 1):.2f} "
            f"sun={meta.get('sun_az', 0):.0f}/{meta.get('sun_el', 0):.0f}",
            flush=True,
        )

    def set_show_ground(self, on: bool) -> None:
        self._show_ground = bool(on)
        self._env_cache_key = None
        self.update()

    def set_lamps(self, lamps: list) -> None:
        """Onetex glow + omni cast — panel lights itself and hits nearby mesh."""
        self._lamp_pack = pack_for_gpu(lamps, cast=True)
        self._lamp_glow = dict(self._lamp_pack.get("glow") or {})
        markers: list[tuple[tuple[float, float, float], tuple[float, float, float], bool, float, float]] = []
        for L in lamps:
            markers.append(
                (
                    (float(L.pos[0]), float(L.pos[1]), float(L.pos[2])),
                    (float(L.color[0]), float(L.color[1]), float(L.color[2])),
                    bool(L.enabled),
                    float(L.brightness),
                    float(L.range_m),
                )
            )
        self._lamp_markers = markers
        self._shadow_dirty = True
        self._shadow_build_i = 0
        self._lit_uniforms_dirty = True
        self.update()

    def set_moon(self, on: bool, intensity: float = 0.45) -> None:
        self._moon_on = bool(on)
        self._moon_intensity = float(max(0.0, intensity))
        self._lit_uniforms_dirty = True
        self.update()

    def set_show_attachments(self, on: bool) -> None:
        self._show_atts = bool(on)

    def set_hidden_mesh_keys(self, keys: set[str] | frozenset[str] | None) -> None:
        """Hide whole files by mesh_key (Scene table Show checkboxes)."""
        nxt = {str(k) for k in (keys or set()) if k}
        if nxt == self._hidden_mesh_keys:
            return
        self._hidden_mesh_keys = nxt
        self._shadow_dirty = True
        self.update()

    def set_hidden_att_mesh_keys(self, keys: set[str] | frozenset[str] | None) -> None:
        """Hide a.* gizmos by owning mesh_key (Scene table Atts checkboxes)."""
        nxt = {str(k) for k in (keys or set()) if k}
        if nxt == self._hidden_att_mesh_keys:
            return
        self._hidden_att_mesh_keys = nxt
        self.update()

    def _scene_mesh_keys(self) -> set[str]:
        keys = {str(p.mesh_key) for p in self._scene.parts if getattr(p, "mesh_key", "")}
        if keys:
            return keys
        return {str(b.mesh_key) for b in self._batches if getattr(b, "mesh_key", "")}

    def _att_is_hidden(self, att) -> bool:
        mk = "" if isinstance(att, str) else str(getattr(att, "mesh_key", "") or "")
        if mk:
            return mk in self._hidden_att_mesh_keys
        name = att if isinstance(att, str) else str(getattr(att, "name", "") or "")
        return is_attachment_hidden(
            name, self._hidden_att_mesh_keys, self._scene_mesh_keys()
        )

    def event(self, event) -> bool:  # noqa: N802
        # Win32 Alt opens the menu bar and drops Alt from the click — keep it for a.* pick.
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and event.key() == Qt.Key.Key_Alt
        ):
            event.accept()
            return True
        return super().event(event)

    def set_render_active(self, on: bool) -> None:
        """Pause camera timer / paints — Packages preview must stop when Mesh Studio runs."""
        self._render_active = bool(on)
        if self._render_active:
            self._wake_cam_timer()
            self.update()
        else:
            self._cam_timer.stop()
            self._yaw_vel = 0.0
            self._pitch_vel = 0.0
            self._zoom_vel = 0.0
            self._focal_vel = 0.0
            self._pan_vel[:] = 0.0
            self._cam_busy = False

    def _wake_cam_timer(self) -> None:
        """Snap back to 16ms — hidden path uses 120ms sleep and must not lag first orbit."""
        if self._cam_timer.interval() != 16:
            self._cam_timer.setInterval(16)
        if not self._cam_timer.isActive():
            self._cam_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._render_active:
            self._wake_cam_timer()

    def set_show_lamp_gizmos(self, on: bool) -> None:
        self._show_lamp_gizmos = bool(on)
        self.update()

    @property
    def fps_chip(self) -> FpsHudChip:
        return self._fps_chip

    def set_fps_place(
        self,
        host_w: int,
        dock_left: int | None,
        left_min: int,
        *,
        top: int = 10,
        margin: int = 12,
    ) -> None:
        """Remember the clear-viewport box. ``dock_left`` None = right sidebar shut."""
        self._fps_place = (int(host_w), dock_left, int(left_min), int(top), int(margin))
        self.apply_fps_place()

    def apply_fps_place(self) -> None:
        spec = self._fps_place
        chip = self._fps_chip
        if spec is None or not chip.isVisible() or chip.width() < 8:
            return
        host_w, dock_left, left_min, top, margin = spec
        x, y = fps_hud_top_right(
            host_w,
            chip.width(),
            margin=margin,
            dock_left=dock_left,
            left_min=left_min,
            top=top,
        )
        if chip.pos() != QPoint(x, y):
            chip.move(x, y)

    def set_show_fps(self, on: bool) -> None:
        self._show_fps = bool(on)
        self._fps_idle_shown = False
        if not self._show_fps:
            self._fps_chip.hide()
            return
        # One frame to fill the chip. Idle ticks must not keep redrawing.
        self.update()

    def set_texture_filter(
        self,
        mode: str,
        stems: set[str] | None = None,
        mesh_keys: set[str] | None = None,
    ) -> None:
        """mode in {\"all\",\"selected\"}; selected hides parts whose refs miss stems.

        When mesh_keys is set, only those meshes are considered (multi-mesh preview).
        """
        if mode not in ("all", "selected"):
            mode = "all"
        self._tex_filter_mode = mode
        self._tex_filter_stems = {texture_stem(s) for s in (stems or set()) if s}
        self._tex_filter_mesh_keys = {str(k) for k in (mesh_keys or set()) if k}
        if mode == "all":
            self._albedo_force = None
            self._albedo_force_stems.clear()
        self._shadow_dirty = True
        self._shadow_build_i = 0
        self.update()

    def set_mat_highlight(
        self,
        stems: set[str] | None,
        mesh_keys: set[str] | None = None,
        *,
        frame: bool = False,
    ) -> int:
        """Mat pick, or a whole mesh file → glowing geometry outline."""
        stem_set = {texture_stem(s) for s in (stems or set()) if s}
        keys = {str(k) for k in (mesh_keys or set()) if k}
        same = (
            stem_set == self._highlight_stems
            and keys == self._highlight_mesh_keys
            and not self._highlight_names
        )
        self._highlight_names.clear()
        self._highlight_stems = stem_set
        self._highlight_mesh_keys = keys
        n = sum(1 for b in self._batches if self._batch_is_highlighted(b))
        if frame and n and not same:
            self._frame_highlight()
        self.update()
        return n

    def set_part_highlight(
        self, names: set[str] | None, *, frame: bool = False
    ) -> int:
        """Editor Meshes row → same glowing outline as a Mat pick, by part name."""
        nxt = {str(n) for n in (names or set()) if n}
        same = (
            nxt == self._highlight_names
            and not self._highlight_stems
            and not self._highlight_mesh_keys
        )
        self._highlight_stems.clear()
        self._highlight_mesh_keys.clear()
        self._highlight_names = nxt
        n = sum(1 for b in self._batches if self._batch_is_highlighted(b))
        if frame and n and not same:
            self._frame_highlight()
        self.update()
        return n

    def frame_mat(self, stems: set[str], mesh_keys: set[str] | None = None) -> None:
        """Fly orbit target to matching part AABB (same ease as a.* click)."""
        self._fly_to_bounds(self._mat_bounds(stems, mesh_keys))

    def _frame_highlight(self) -> None:
        self._fly_to_bounds(self._highlight_bounds())

    def _fly_to_bounds(self, bounds: tuple[np.ndarray, np.ndarray] | None) -> None:
        if bounds is None:
            return
        mins, maxs = bounds
        center = (mins + maxs) * 0.5
        extent = float(np.linalg.norm(maxs - mins)) or 0.25
        # only pull in if we're extremely far; otherwise just re-aim
        if self._dist > extent * 6.0:
            self._dist = max(extent * 2.2, 0.4)
        self.fly_to(center, duration_s=0.45, approach=False)

    def _highlight_active(self) -> bool:
        return bool(
            self._highlight_names or self._highlight_stems or self._highlight_mesh_keys
        )

    def _batch_is_highlighted(self, batch: DrawBatch) -> bool:
        if self._highlight_names:
            return highlight_pick(
                name=batch.name,
                mesh_key="",
                ref_stems=set(),
                names=self._highlight_names,
                stems=set(),
                mesh_keys=set(),
            )
        return self._batch_matches_mat(
            batch, self._highlight_stems, self._highlight_mesh_keys
        )

    def _batch_matches_mat(
        self, batch: DrawBatch, stems: set[str], mesh_keys: set[str] | None
    ) -> bool:
        if mesh_keys and batch.mesh_key not in mesh_keys:
            return False
        if not stems:
            return bool(mesh_keys) and batch.mesh_key in mesh_keys
        # family match: body_albedo list row ↔ mesh ref "body"
        return stems_match(batch.ref_stems(), stems)

    def _mat_bounds(
        self, stems: set[str], mesh_keys: set[str] | None = None
    ) -> tuple[np.ndarray, np.ndarray] | None:
        keys = {str(k) for k in (mesh_keys or set()) if k}
        stem_set = {texture_stem(s) for s in stems if s}
        mins_list: list[np.ndarray] = []
        maxs_list: list[np.ndarray] = []
        for batch in self._batches:
            if not self._batch_matches_mat(batch, stem_set, keys):
                continue
            pos = batch.verts[:, 0:3]
            if pos.size == 0:
                continue
            mins_list.append(pos.min(axis=0))
            maxs_list.append(pos.max(axis=0))
        if not mins_list:
            return None
        return np.min(np.vstack(mins_list), axis=0), np.max(np.vstack(maxs_list), axis=0)

    def _highlight_bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        mins_list: list[np.ndarray] = []
        maxs_list: list[np.ndarray] = []
        for batch in self._batches:
            if not self._batch_is_highlighted(batch):
                continue
            pos = batch.verts[:, 0:3]
            if pos.size == 0:
                continue
            mins_list.append(pos.min(axis=0))
            maxs_list.append(pos.max(axis=0))
        if not mins_list:
            return None
        return np.min(np.vstack(mins_list), axis=0), np.max(np.vstack(maxs_list), axis=0)

    def _mat_outline_edge_lines(self) -> np.ndarray:
        """Triangle edges of highlighted batches — cached (rebuild was ~80k Python loops/paint)."""
        if not self._highlight_active():
            return np.zeros((0, 6), dtype=np.float32)
        key = (
            frozenset(self._highlight_stems),
            frozenset(self._highlight_mesh_keys),
            frozenset(self._highlight_names),
            id(self._batches),
            len(self._batches),
        )
        if key == self._mat_edge_key and self._mat_edge_cache is not None:
            if self._mat_edge_vbo is None:
                self._upload_mat_edges(self._mat_edge_cache)
            return self._mat_edge_cache
        rows: list[list[float]] = []
        max_tris = 12_000  # ponytail: enough silhouette; 80k shredded orbit FPS
        tris_total = 0
        col = (1.0, 0.45, 0.10)
        for batch in self._batches:
            if not self._batch_is_highlighted(batch):
                continue
            pos = batch.verts[:, 0:3]
            idx = batch.indices
            if idx.size >= 3:
                n_tris = int(idx.shape[0]) // 3
            else:
                n_tris = int(batch.verts.shape[0]) // 3
                idx = None
            if n_tris < 1:
                continue
            step = max(1, n_tris // max(max_tris - tris_total, 1)) if tris_total + n_tris > max_tris else 1
            for ti in range(0, n_tris, step):
                if idx is not None:
                    i0 = int(idx[ti * 3])
                    i1 = int(idx[ti * 3 + 1])
                    i2 = int(idx[ti * 3 + 2])
                    a, b, c = pos[i0], pos[i1], pos[i2]
                else:
                    base = ti * 3
                    a, b, c = pos[base], pos[base + 1], pos[base + 2]
                for p, q in ((a, b), (b, c), (c, a)):
                    rows.append([float(p[0]), float(p[1]), float(p[2]), *col])
                    rows.append([float(q[0]), float(q[1]), float(q[2]), *col])
                tris_total += 1
                if tris_total >= max_tris:
                    break
            if tris_total >= max_tris:
                break
        out = np.asarray(rows, dtype=np.float32) if rows else np.zeros((0, 6), dtype=np.float32)
        self._mat_edge_key = key
        self._mat_edge_cache = out
        self._upload_mat_edges(out)
        return out

    def _release_mat_edge_vbo(self) -> None:
        vbo = self._mat_edge_vbo
        self._mat_edge_vbo = None
        self._mat_edge_count = 0
        if vbo and self._gl_ready:
            try:
                GL.glDeleteBuffers(1, [int(vbo)])
            except Exception:
                pass

    def _upload_mat_edges(self, edges: np.ndarray) -> None:
        """One GPU upload — orbit used to re-stream the line array every frame."""
        if not self._gl_ready:
            return
        if edges.size == 0:
            self._release_mat_edge_vbo()
            return
        data = np.ascontiguousarray(edges, dtype=np.float32)
        if self._mat_edge_vbo is None:
            self._mat_edge_vbo = int(GL.glGenBuffers(1))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, int(self._mat_edge_vbo))
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self._mat_edge_count = int(data.shape[0])

    def _draw_outline_edges(self, mvp: np.ndarray) -> None:
        if not self._mat_edge_count or self._mat_edge_vbo is None or self._line_prog is None:
            return
        if self._lloc is None:
            self._cache_line_locs()
        loc = self._lloc
        if loc is None:
            return
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, int(self._mat_edge_vbo))
        GL.glUseProgram(self._line_prog)
        GL.glUniformMatrix4fv(loc["mvp"], 1, GL.GL_TRUE, mvp)
        GL.glLineWidth(1.5)
        GL.glEnableVertexAttribArray(loc["pos"])
        GL.glEnableVertexAttribArray(loc["col"])
        GL.glVertexAttribPointer(loc["pos"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(0))
        GL.glVertexAttribPointer(loc["col"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(12))
        GL.glDrawArrays(GL.GL_LINES, 0, int(self._mat_edge_count))
        GL.glDisableVertexAttribArray(loc["pos"])
        GL.glDisableVertexAttribArray(loc["col"])
        GL.glLineWidth(1.0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glUseProgram(0)

    def _draw_mat_outline(self, mvp: np.ndarray) -> None:
        """Triangle-edge frame on the selected geometry. Stays on while the camera moves."""
        if not self._highlight_active():
            return
        self._mat_outline_edge_lines()
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            self._draw_outline_edges(mvp)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)

    def set_albedo_force_on_stems(self, path: str | Path | None, stems: set[str]) -> None:
        """Right-click 'Force as albedo on selection' — only matching parts, never whole mesh."""
        if path is None or not stems:
            self._albedo_force = None
            self._albedo_force_stems.clear()
        else:
            p = str(Path(path))
            self._albedo_force = p if Path(p).is_file() else None
            self._albedo_force_stems = {texture_stem(s) for s in stems if s}
        self.update()

    def set_self_illum_stems(self, stems: set[str] | None, boost: float = 0.55) -> None:
        """Preview as Self-Illum for matching stems; None clears override boost."""
        if stems is None:
            self._self_illum_stems = None
        else:
            self._self_illum_stems = {texture_stem(s) for s in stems if s}
            self._self_illum_boost = float(boost)
        self.update()

    def set_light_enabled(self, index: int, on: bool) -> None:
        if 0 <= index < 5:
            self._light_on[index] = bool(on)
            self._lit_uniforms_dirty = True
            self.update()

    def set_sun(
        self,
        enabled: bool,
        azimuth_deg: float = 135.0,
        elevation_deg: float = 45.0,
        intensity: float = 1.4,
    ) -> None:
        self._sun_enabled = bool(enabled)
        self._sun_az = float(azimuth_deg)
        self._sun_el = float(elevation_deg)
        self._sun_intensity = float(intensity)
        self._lit_uniforms_dirty = True
        self.update()

    def set_emissive_scale(self, scale: float) -> None:
        """Preview-only multiplier on parameter R / self-illum emissive term."""
        self._emissive_scale = float(scale)
        self._lit_uniforms_dirty = True
        self.update()

    def set_material_preview(
        self,
        stems: set[str] | None,
        *,
        enabled: bool,
        emissive: float = 0.0,
        roughness: float = 0.55,
        metal: float = 0.0,
        specular: float = 1.0,
    ) -> None:
        """Editor Material preview — overrides Trainz parameter channels for matching stems.

        Preview only (does not write .trainzmesh / parameter maps).
        """
        if stems is None or not enabled:
            self._mat_edit_stems = set()
            self._mat_edit_on = False
        else:
            self._mat_edit_stems = {texture_stem(s) for s in stems if s}
            self._mat_edit_on = bool(self._mat_edit_stems)
        self._edit_emissive = float(max(0.0, emissive))
        self._edit_rough = float(np.clip(roughness, 0.04, 1.0))
        self._edit_metal = float(np.clip(metal, 0.0, 1.0))
        self._edit_specular = float(max(0.0, specular))
        self.update()

    def clear_material_preview(self) -> None:
        self.set_material_preview(None, enabled=False)

    def set_two_sided_for_material(self, name: str, on: bool) -> int:
        """Live preview: cull off on that material only. Does not reload the scene."""
        return self.set_two_sided_for_materials([name], on)

    def set_two_sided_for_materials(self, names, on: bool) -> int:
        """Flip back faces on those materials and redraw. Camera and buffers stay put."""
        n = 0
        for name in names:
            n += apply_named_two_sided(self._scene.parts, self._batches, name, on)
        self._shadow_dirty = True
        self.update()
        return n

    def set_two_sided_for_stems(
        self,
        stems: set[str] | None,
        on: bool,
        *,
        mesh_key: str | None = None,
    ) -> None:
        """Toggle Trainz two-sided (no backface cull) for parts matching stems."""
        want = {texture_stem(s) for s in (stems or ()) if s}
        if not want:
            return
        for part in self._scene.parts:
            if mesh_key and (part.mesh_key or "") != mesh_key:
                continue
            refs = {
                texture_stem(r)
                for r in (
                    part.albedo_ref,
                    part.normal_ref,
                    part.parameter_ref,
                    part.albedo_path or "",
                    part.normal_path or "",
                    part.parameter_path or "",
                    part.name,
                )
                if r
            }
            if stems_match(refs, want):
                part.two_sided = bool(on)
        for batch in self._batches:
            if mesh_key and batch.mesh_key != mesh_key:
                continue
            if stems_match(batch.ref_stems(), want):
                batch.two_sided = bool(on)
        self.update()

    def set_clear_color(self, rgb: tuple[float, float, float]) -> None:
        self._clear_rgb = rgb
        if self._gl_ready:
            GL.glClearColor(rgb[0], rgb[1], rgb[2], 1.0)
        self.update()

    def set_debug_mode(self, mode: int) -> None:
        self._debug_mode = int(mode)
        self.update()

    def set_face_orientation(self, on: bool) -> None:
        """Blender-style Face Orientation: blue front / red back (triangle winding)."""
        on = bool(on)
        if self._face_orient == on:
            return
        self._face_orient = on
        self.update()

    def set_flip_texture_v(self, on: bool) -> None:
        """Optional ImageOps.flip. Default False — Trainz V=0 is top of image."""
        on = bool(on)
        if self._flip_texture_v == on:
            return
        self._flip_texture_v = on
        self._purge_textures()
        self.update()

    def set_anim_time(self, t: float) -> None:
        # stub: stores scrub time for future skinning; no bone matrices yet
        self._anim_time = float(t)
        self.update()

    def _rebuild_batches(self) -> None:
        self._release_batch_vbos()
        self._batches.clear()
        parts = [p for p in self._scene.parts if p.indices.size and p.vertices.size]
        if not parts:
            return
        totals = [max(len(p.indices) // 3, 1) for p in parts]
        total = sum(totals)
        # Give every part its fair share; never starve small parts under 4k.
        for part, n in zip(parts, totals):
            if total <= MAX_PREVIEW_TRIS:
                budget = n  # full mesh — Trainz-faithful
            else:
                budget = max(4000, int(MAX_PREVIEW_TRIS * (n / total)))
            batch = _flatten_part(part, budget)
            if batch is not None and batch.verts.size:
                self._batches.append(batch)
        self._upload_batch_vbos()
        self._shadow_dirty = True
        self._shadow_build_i = 0
        self._mat_edge_key = None
        self._mat_edge_cache = None
        self._release_mat_edge_vbo()

    def _release_batch_vbos(self) -> None:
        ids = [int(b.vbo) for b in self._batches if b.vbo]
        ids += [int(b.ibo) for b in self._batches if b.ibo]
        if ids and self._gl_ready:
            try:
                GL.glDeleteBuffers(len(ids), ids)
            except Exception:
                pass
        for b in self._batches:
            b.vbo = None
            b.ibo = None
            b.vcount = 0
            b.icount = 0

    def _upload_batch_vbos(self) -> None:
        """Upload interleaved verts + indices once — full Lit draw stays on GPU."""
        if not self._gl_ready:
            return
        for batch in self._batches:
            if batch.vbo or batch.verts.size == 0:
                continue
            data = np.ascontiguousarray(batch.verts, dtype=np.float32)
            vbo = int(GL.glGenBuffers(1))
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
            batch.vbo = vbo
            batch.vcount = int(data.shape[0])
            if batch.indices.size:
                idata = np.ascontiguousarray(batch.indices, dtype=np.uint32)
                ibo = int(GL.glGenBuffers(1))
                GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ibo)
                GL.glBufferData(
                    GL.GL_ELEMENT_ARRAY_BUFFER, idata.nbytes, idata, GL.GL_STATIC_DRAW
                )
                batch.ibo = ibo
                batch.icount = int(idata.shape[0])
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)

    def _bind_batch_attribs(
        self,
        batch: DrawBatch,
        loc_pos: int,
        loc_nrm: int = -1,
        loc_uv: int = -1,
    ) -> int:
        """Bind pos[/nrm/uv] from VBO (preferred) or client-side numpy fallback."""
        n = int(batch.vcount or batch.verts.shape[0])
        if n <= 0:
            return 0
        if batch.vbo:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, int(batch.vbo))
            GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(0))
            if loc_nrm >= 0:
                GL.glVertexAttribPointer(
                    loc_nrm, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(12)
                )
            if loc_uv >= 0:
                GL.glVertexAttribPointer(
                    loc_uv, 2, GL.GL_FLOAT, False, 32, ctypes.c_void_p(24)
                )
            return n
        base = batch.verts.ctypes.data
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base))
        if loc_nrm >= 0:
            GL.glVertexAttribPointer(
                loc_nrm, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base + 12)
            )
        if loc_uv >= 0:
            GL.glVertexAttribPointer(
                loc_uv, 2, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base + 24)
            )
        return n

    def _draw_batch_tris(
        self,
        batch: DrawBatch,
        loc_pos: int,
        loc_nrm: int = -1,
        loc_uv: int = -1,
    ) -> None:
        """glDrawElements via IBO when present — full shading, indexed topology."""
        n = self._bind_batch_attribs(batch, loc_pos, loc_nrm, loc_uv)
        if n <= 0:
            return
        if batch.ibo and batch.icount > 0:
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, int(batch.ibo))
            GL.glDrawElements(
                GL.GL_TRIANGLES,
                int(batch.icount),
                GL.GL_UNSIGNED_INT,
                ctypes.c_void_p(0),
            )
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
        else:
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, n)

    def _purge_textures(self, *, keep_decoded: bool = False) -> None:
        """Drop GPU textures. Keep CPU precache when seeding a new scene open."""
        if not self._gl_ready:
            self._tex_cache.clear()
            self._tex_missing.clear()
            if not keep_decoded:
                self._decoded_cache.clear()
            return
        for tex_id in self._tex_cache.values():
            GL.glDeleteTextures([tex_id])
        self._tex_cache.clear()
        self._tex_missing.clear()
        if not keep_decoded:
            self._decoded_cache.clear()

    def _fb_size(self) -> tuple[int, int]:
        """Paint at widget logical size — same as the smooth pre-regression path.

        Full devicePixelRatio × Lit GGX×64 lamps ≈ 30fps on cabin HiDPI.
        Sharpness comes from settle-frame Lit, not 4× fill during orbit.
        """
        return max(int(self.width()), 1), max(int(self.height()), 1)

    def _batch_visible(self, batch: DrawBatch) -> bool:
        if is_mesh_key_hidden(batch.mesh_key or "", self._hidden_mesh_keys):
            return False
        if self._tex_filter_mode != "selected":
            return True
        if self._tex_filter_mesh_keys and batch.mesh_key not in self._tex_filter_mesh_keys:
            return False
        if not self._tex_filter_stems:
            # mesh-only filter (whole file selected)
            return bool(self._tex_filter_mesh_keys) and batch.mesh_key in self._tex_filter_mesh_keys
        return stems_match(batch.ref_stems(), self._tex_filter_stems)

    def _self_illum_for(self, batch: DrawBatch, has_parameter: bool) -> float:
        from ..lamps import glow_key

        stems = batch.ref_stems()
        glow = 0.0
        mk = batch.mesh_key or ""
        for st in stems:
            glow = max(glow, float(self._lamp_glow.get(glow_key(mk, st), 0.0)))
            glow = max(glow, float(self._lamp_glow.get(st, 0.0)))
        if self._self_illum_stems is not None and (stems & self._self_illum_stems):
            glow = max(glow, self._self_illum_boost)
        if glow > 0.0:
            return glow
        # no free onetex glow — only when a lamp is enabled (or Mat Self-Illum)
        return 0.0

    def _batch_wants_mat_edit(self, batch: DrawBatch) -> bool:
        if not self._mat_edit_on or not self._mat_edit_stems:
            return False
        return bool(batch.ref_stems() & self._mat_edit_stems)

    def initializeGL(self) -> None:
        GL.glEnable(GL.GL_DEPTH_TEST)
        # ponytail: no backface cull — Trainz cabin walls/seats punch holes from inside if culled
        GL.glDisable(GL.GL_CULL_FACE)
        # opaque cabin draw — blend was making albedo-alpha walls see-through
        GL.glDisable(GL.GL_BLEND)
        r, g, b = self._clear_rgb
        GL.glClearColor(r, g, b, 1.0)
        try:
            self._prog = gl_shaders.compileProgram(
                gl_shaders.compileShader(VERT_SRC, GL.GL_VERTEX_SHADER),
                gl_shaders.compileShader(FRAG_SRC, GL.GL_FRAGMENT_SHADER),
            )
            self._line_prog = gl_shaders.compileProgram(
                gl_shaders.compileShader(LINE_VERT, GL.GL_VERTEX_SHADER),
                gl_shaders.compileShader(LINE_FRAG, GL.GL_FRAGMENT_SHADER),
            )
            self._glow_prog = gl_shaders.compileProgram(
                gl_shaders.compileShader(GLOW_VERT, GL.GL_VERTEX_SHADER),
                gl_shaders.compileShader(GLOW_FRAG, GL.GL_FRAGMENT_SHADER),
            )
            self._sky_prog = gl_shaders.compileProgram(
                gl_shaders.compileShader(SKY_VERT, GL.GL_VERTEX_SHADER),
                gl_shaders.compileShader(SKY_FRAG, GL.GL_FRAGMENT_SHADER),
            )
            self._depth_prog = gl_shaders.compileProgram(
                gl_shaders.compileShader(DEPTH_VERT, GL.GL_VERTEX_SHADER),
                gl_shaders.compileShader(DEPTH_FRAG, GL.GL_FRAGMENT_SHADER),
            )
        except Exception as e:
            print(f"trainz_studio: shader compile failed: {e}", flush=True)
            self._prog = None
            self._line_prog = None
            self._glow_prog = None
            self._sky_prog = None
            self._depth_prog = None
        self._cache_prog_locs()
        self._cache_line_locs()
        self._placeholder_tex = self._make_texture(*_placeholder_rgba())
        self._flat_normal_tex = self._make_texture(*_placeholder_rgba((128, 128, 255)))
        flat_p = bytes((0, 140, 255, 0)) * 16
        self._flat_param_tex = self._make_texture(4, 4, flat_p)
        self._gl_ready = True
        self._upload_batch_vbos()  # scene may have loaded before GL context existed
        if self._pending_hdri_path:
            self._load_hdri_texture(self._pending_hdri_path)

    def resizeGL(self, w: int, h: int) -> None:
        GL.glViewport(0, 0, max(w, 1), max(h, 1))

    def _release_shadow_fbo(self) -> None:
        if self._shadow_fbo:
            try:
                GL.glDeleteFramebuffers(1, [int(self._shadow_fbo)])
            except Exception:
                pass
            self._shadow_fbo = None
        if self._shadow_tex:
            try:
                GL.glDeleteTextures([int(self._shadow_tex)])
            except Exception:
                pass
            self._shadow_tex = None
        if self._shadow_rb:
            try:
                GL.glDeleteRenderbuffers(1, [int(self._shadow_rb)])
            except Exception:
                pass
        self._shadow_rb = None
        self._shadow_count = 0
        self._shadow_dirty = True
        self._shadow_build_i = 0

    def _ensure_shadow_fbo(self) -> bool:
        if self._shadow_fbo and self._shadow_tex and self._shadow_rb:
            return True
        self._release_shadow_fbo()
        tw = SHADOW_TILE * SHADOW_COLS
        th = SHADOW_TILE * SHADOW_ROWS
        try:
            tex = int(GL.glGenTextures(1))
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            # Float color holds gl_FragCoord.z — samplable on GL 1.20 (unlike DEPTH_COMPONENT)
            internal = GL.GL_RGBA32F
            fmt = GL.GL_RGBA
            typ = GL.GL_FLOAT
            try:
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, tw, th, 0, fmt, typ, None)
            except Exception:
                internal = GL.GL_RGBA8
                typ = GL.GL_UNSIGNED_BYTE
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, tw, th, 0, fmt, typ, None)
            rb = int(GL.glGenRenderbuffers(1))
            GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, rb)
            GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT24, tw, th)
            fbo = int(GL.glGenFramebuffers(1))
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
            GL.glFramebufferTexture2D(
                GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0
            )
            GL.glFramebufferRenderbuffer(
                GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_RENDERBUFFER, rb
            )
            status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
            if status != GL.GL_FRAMEBUFFER_COMPLETE and internal == GL.GL_RGBA32F:
                # Fall back to 8-bit if float attach rejected
                GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
                GL.glTexImage2D(
                    GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, tw, th, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None
                )
                GL.glFramebufferTexture2D(
                    GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0
                )
                status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
            self._restore_default_fbo()
            if status != GL.GL_FRAMEBUFFER_COMPLETE:
                GL.glDeleteFramebuffers(1, [fbo])
                GL.glDeleteTextures([tex])
                GL.glDeleteRenderbuffers(1, [rb])
                print(f"trainz_studio: shadow FBO incomplete ({status})", flush=True)
                return False
            self._shadow_tex = tex
            self._shadow_rb = rb
            self._shadow_fbo = fbo
            return True
        except Exception as exc:
            print(f"trainz_studio: shadow FBO failed: {exc}", flush=True)
            self._release_shadow_fbo()
            self._restore_default_fbo()
            return False

    def _restore_default_fbo(self, w: int | None = None, h: int | None = None) -> None:
        """QOpenGLWidget FBO needs COLOR_ATTACHMENT0 — DrawBuffer=NONE blanks Lit forever."""
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        try:
            GL.glDrawBuffer(GL.GL_COLOR_ATTACHMENT0)
            GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
        except Exception:
            try:
                GL.glDrawBuffer(GL.GL_BACK)
            except Exception:
                pass
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        if w is None or h is None:
            ww, hh = self._fb_size()
        else:
            ww, hh = max(int(w), 1), max(int(h), 1)
        GL.glViewport(0, 0, ww, hh)

    def _lamp_shadow_vp(self, pos: np.ndarray, range_m: float) -> np.ndarray:
        """Perspective from ceiling lamp looking down onto the cabin."""
        eye = pos.astype(np.float64)
        # Look down −Z (Trainz up); bias toward −Y so atlas isn't singular at poles
        target = eye + np.array([0.0, -0.15, -1.0], dtype=np.float64)
        up = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        view = _look_at_mat(eye, target, up)
        zfar = max(float(range_m) * 1.15, 1.0)
        proj = _perspective_mat(130.0, 1.0, 0.04, zfar)
        return proj @ view

    def _batch_casts_shadow(self, batch: DrawBatch) -> bool:
        # ponytail: skip glass — expensive, barely occludes cabin fill
        blob = f"{batch.name} {batch.mesh_key} {batch.albedo_ref}".lower()
        return "glass" not in blob

    def _cache_prog_locs(self) -> None:
        """Cache hot uniform locations once after link (avoid glGet every paint)."""
        if self._prog is None:
            self._uloc = None
        else:
            self._cache_lit_locs()
        self._dloc = None
        if self._depth_prog is not None:
            dp = self._depth_prog
            self._dloc = {
                "mvp": GL.glGetUniformLocation(dp, "u_mvp"),
                "pos": GL.glGetAttribLocation(dp, "in_pos"),
            }

    def _cache_lit_locs(self) -> None:
        p = self._prog
        if p is None:
            self._uloc = None
            return
        loc: dict = {
            "mvp": GL.glGetUniformLocation(p, "u_mvp"),
            "model": GL.glGetUniformLocation(p, "u_model"),
            "cam": GL.glGetUniformLocation(p, "u_cam_pos"),
            "flat": GL.glGetUniformLocation(p, "u_flat_color"),
            "use_tex": GL.glGetUniformLocation(p, "u_use_tex"),
            "has_n": GL.glGetUniformLocation(p, "u_has_normal"),
            "has_p": GL.glGetUniformLocation(p, "u_has_parameter"),
            "self": GL.glGetUniformLocation(p, "u_self_illum"),
            "amb": GL.glGetUniformLocation(p, "u_ambient"),
            "emis": GL.glGetUniformLocation(p, "u_emissive_scale"),
            "mat_edit": GL.glGetUniformLocation(p, "u_mat_edit"),
            "edit_emis": GL.glGetUniformLocation(p, "u_edit_emissive"),
            "edit_rough": GL.glGetUniformLocation(p, "u_edit_rough"),
            "edit_metal": GL.glGetUniformLocation(p, "u_edit_metal"),
            "edit_spec": GL.glGetUniformLocation(p, "u_edit_specular"),
            "dbg": GL.glGetUniformLocation(p, "u_debug_mode"),
            "face_orient": GL.glGetUniformLocation(p, "u_face_orient"),
            "two_sided": GL.glGetUniformLocation(p, "u_two_sided"),
            "albedo": GL.glGetUniformLocation(p, "u_albedo"),
            "normal": GL.glGetUniformLocation(p, "u_normal"),
            "param": GL.glGetUniformLocation(p, "u_parameter"),
            "shadow": GL.glGetUniformLocation(p, "u_shadow_atlas"),
            "scount": GL.glGetUniformLocation(p, "u_shadow_count"),
            "lamp_count": GL.glGetUniformLocation(p, "u_lamp_count"),
            "sky_t": GL.glGetUniformLocation(p, "u_sky_top"),
            "sky_h": GL.glGetUniformLocation(p, "u_sky_horizon"),
            "ibl": GL.glGetUniformLocation(p, "u_ibl_strength"),
            "env_map": GL.glGetUniformLocation(p, "u_env_map"),
            "use_env": GL.glGetUniformLocation(p, "u_use_env_map"),
            "moon_on": GL.glGetUniformLocation(p, "u_moon_on"),
            "moon_dir": GL.glGetUniformLocation(p, "u_moon_dir"),
            "moon_rad": GL.glGetUniformLocation(p, "u_moon_rad"),
            "pos": GL.glGetAttribLocation(p, "in_pos"),
            "nrm": GL.glGetAttribLocation(p, "in_nrm"),
            "uv": GL.glGetAttribLocation(p, "in_uv"),
            "shadow_vp": [
                GL.glGetUniformLocation(p, f"u_shadow_vp[{i}]") for i in range(MAX_SHADOW_LAMPS)
            ],
            "lamp_pos": [GL.glGetUniformLocation(p, f"u_lamp_pos[{i}]") for i in range(MAX_LAMPS)],
            "lamp_col": [GL.glGetUniformLocation(p, f"u_lamp_col[{i}]") for i in range(MAX_LAMPS)],
            "lamp_power": [GL.glGetUniformLocation(p, f"u_lamp_power[{i}]") for i in range(MAX_LAMPS)],
            "lamp_range": [GL.glGetUniformLocation(p, f"u_lamp_range[{i}]") for i in range(MAX_LAMPS)],
            "lamp_mode": [GL.glGetUniformLocation(p, f"u_lamp_mode[{i}]") for i in range(MAX_LAMPS)],
            "lamp_dir": [GL.glGetUniformLocation(p, f"u_lamp_dir[{i}]") for i in range(MAX_LAMPS)],
            "lamp_cone": [GL.glGetUniformLocation(p, f"u_lamp_cone[{i}]") for i in range(MAX_LAMPS)],
            "lights": [GL.glGetUniformLocation(p, f"u_lights[{i}]") for i in range(5)],
            "light_on": [GL.glGetUniformLocation(p, f"u_light_on[{i}]") for i in range(5)],
            "light_rad": [GL.glGetUniformLocation(p, f"u_light_rad[{i}]") for i in range(5)],
        }
        self._uloc = loc

    def _render_lamp_shadows(self) -> int:
        """Depth atlas from each lamp (down). Cached; amortized across frames when dirty."""
        if self._depth_prog is None or not self._batches:
            self._shadow_count = 0
            self._shadow_dirty = False
            return 0
        pack = self._lamp_pack
        count = int(pack.get("count", 0))
        if count <= 0:
            self._shadow_count = 0
            self._shadow_dirty = False
            return 0
        if not self._ensure_shadow_fbo():
            self._shadow_count = 0
            self._shadow_dirty = False
            return 0
        assert self._shadow_fbo is not None and self._shadow_tex is not None
        n = min(count, MAX_SHADOW_LAMPS)
        tw = SHADOW_TILE * SHADOW_COLS
        th = SHADOW_TILE * SHADOW_ROWS
        start = int(self._shadow_build_i)
        if start >= n:
            start = 0
            self._shadow_build_i = 0
        end = min(n, start + SHADOW_LAMPS_PER_FRAME)
        try:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, int(self._shadow_fbo))
            try:
                GL.glDrawBuffer(GL.GL_COLOR_ATTACHMENT0)
            except Exception:
                pass
            GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
            GL.glDisable(GL.GL_BLEND)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDepthFunc(GL.GL_LESS)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(1.5, 2.0)
            GL.glClearColor(1.0, 1.0, 1.0, 1.0)
            if start == 0:
                GL.glViewport(0, 0, tw, th)
                GL.glDisable(GL.GL_SCISSOR_TEST)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            if self._dloc is None:
                self._cache_prog_locs()
            assert self._dloc is not None
            loc_mvp = self._dloc["mvp"]
            loc_pos = self._dloc["pos"]
            GL.glUseProgram(self._depth_prog)
            GL.glEnableVertexAttribArray(loc_pos)
            GL.glEnable(GL.GL_SCISSOR_TEST)
            pos_a = pack["pos"]
            range_a = pack["range"]
            casters = [
                b for b in self._batches if self._batch_visible(b) and self._batch_casts_shadow(b)
            ]
            for li in range(start, end):
                col = li % SHADOW_COLS
                row = li // SHADOW_COLS
                x = col * SHADOW_TILE
                y = row * SHADOW_TILE
                GL.glViewport(x, y, SHADOW_TILE, SHADOW_TILE)
                GL.glScissor(x, y, SHADOW_TILE, SHADOW_TILE)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                vp = self._lamp_shadow_vp(pos_a[li], float(range_a[li]))
                self._shadow_vp[li] = vp
                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, vp)
                for batch in casters:
                    self._draw_batch_tris(batch, loc_pos)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glDisableVertexAttribArray(loc_pos)
            GL.glUseProgram(0)
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            self._shadow_build_i = end
            self._shadow_count = n
            if end >= n:
                self._shadow_dirty = False
                self._shadow_build_i = 0
            else:
                self._shadow_dirty = True
                QTimer.singleShot(0, self.update)
            return n
        except Exception as exc:
            print(f"trainz_studio: shadow pass failed: {exc}", flush=True)
            self._shadow_count = 0
            self._shadow_dirty = False
            return 0
        finally:
            self._restore_default_fbo()

    def paintGL(self) -> None:
        if not getattr(self, "_render_active", True):
            return
        t0 = time.perf_counter()
        self._tex_uploads_left = (
            TEX_UPLOADS_BURST if self._tex_burst_frames > 0 else TEX_UPLOADS_PER_FRAME
        )
        if self._tex_burst_frames > 0:
            self._tex_burst_frames -= 1
        self._need_tex_pass = False
        w, h = self._fb_size()
        self._restore_default_fbo(w, h)

        # shadows: view-independent atlas — rebuild only when lamps/meshes dirty
        if (
            self._prog is not None
            and self._batches
            and self._shading == SHADING_RENDERED
            and self._debug_mode == 0
            and not self._face_orient
        ):
            if self._shadow_dirty or self._shadow_tex is None:
                self._render_lamp_shadows()
        else:
            self._shadow_count = 0
        self._restore_default_fbo(w, h)

        r, g, b = self._clear_rgb
        if not self._use_hdri and self._env.key != "none":
            r, g, b = self._env.clear
        GL.glClearColor(r, g, b, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        aspect = w / float(h)
        eye = self._eye()
        view = _look_at_mat(eye, self._target, WORLD_UP)
        proj = _perspective_mat(_focal_mm_to_fovy(self._focal_mm), aspect, 0.05, 5000.0)
        model = np.eye(4, dtype=np.float32)
        mvp = proj @ view @ model

        # Skybox only for HDRI / clear presets — NEVER on env=none (was sun-haze fog)
        need_sky = (self._use_hdri and self._hdri_tex is not None) or (
            self._env.key != "none" and not self._use_hdri
        )
        if need_sky:
            self._draw_sky(view, proj)

        # Real sun/moon meshes (sky-locked) — visible even when env=none
        if self._sun_enabled or (self._moon_on and not self._sun_enabled):
            self._draw_celestials(eye, mvp)

        if self._show_grid and not self._use_hdri:
            self._draw_lines(self._grid_lines(), mvp, width=1.0)
        if self._show_axes:
            self._draw_lines(self._world_axes_lines(), mvp, width=2.5)

        if self._prog is not None and self._batches:
            wire = self._shading == SHADING_WIRE
            if wire:
                GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
            try:
                self._draw_meshes(mvp, model, eye)
            finally:
                if wire:
                    GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_FILL)

        # Mat pick: glowing geometry outline (not emissive / not cast lights)
        self._draw_mat_outline(mvp)

        if self._show_atts:
            sel_i = self._sel_att_index
            move = self._edit_att_index >= 0
            # One draw for all idle a.* — per-att glGet+draw was mode-independent jank.
            idle_chunks: list[np.ndarray] = []
            for i, att in enumerate(self._scene.attachments):
                if i == sel_i or self._att_is_hidden(att):
                    continue
                idle_chunks.append(
                    attachment_gizmo_lines(att, selected=False, dist=self._dist)
                )
            if idle_chunks:
                self._draw_lines(np.vstack(idle_chunks), mvp, width=2.0)
            if 0 <= sel_i < len(self._scene.attachments):
                att = self._scene.attachments[sel_i]
                if not self._att_is_hidden(att):
                    if move:
                        # Blender translate gizmo — Editor Move only; draw on top
                        GL.glDisable(GL.GL_DEPTH_TEST)
                        self._draw_lines(
                            attachment_gizmo_lines(
                                att, selected=True, move_mode=True, dist=self._dist
                            ),
                            mvp,
                            width=4.5,
                        )
                        solids = attachment_gizmo_solids(
                            att, selected=True, move_mode=True, dist=self._dist
                        )
                        if solids.size:
                            self._draw_colored_tris(solids, mvp)
                        GL.glEnable(GL.GL_DEPTH_TEST)
                    else:
                        # Preview / Editor View: highlight axes only (no arrows)
                        self._draw_lines(
                            attachment_gizmo_lines(
                                att, selected=True, move_mode=False, dist=self._dist
                            ),
                            mvp,
                            width=3.0,
                        )

        if self._show_lamp_gizmos:
            # Off bulbs: tiny crosses only (never soft glow — that looked "on")
            crosses = self._lamp_gizmo_crosses(enabled_only=False, disabled_only=True)
            if crosses.size:
                self._draw_lines(crosses, mvp, width=1.5)
            # On bulbs: soft glow at the real cast point
            lc, lcol, lrad = self._lamp_glow_sprites()
            if lc.shape[0]:
                self._draw_glow_sprites(lc, lcol, lrad, mvp)

        if self._show_corner_gizmo:
            self._draw_corner_gizmo(w, h)

        paint_ms = (time.perf_counter() - t0) * 1000.0
        if self._show_fps:
            self._note_frame_timing(paint_ms)
            self._sync_fps_hud()
        elif self._fps_chip.isVisible():
            self._fps_chip.hide()

        if self._need_tex_pass:
            QTimer.singleShot(16, self.update)

    def _note_frame_timing(self, paint_ms: float) -> None:
        self._fps_idle_shown = False
        self._frame_id += 1
        self._fps_paint_ms.append(float(paint_ms))
        now = time.perf_counter()
        if self._fps_last_t > 0.0:
            self._fps_wall_ms.append((now - self._fps_last_t) * 1000.0)
        self._fps_last_t = now

    def _mark_fps_idle_if_settled(self) -> None:
        """Hold the last sample once the camera stops — do not redraw to keep counting."""
        if self._fps_idle_shown or self._fps_last_t <= 0.0:
            return
        if (time.perf_counter() - self._fps_last_t) < 0.45:
            return
        self._fps_idle_shown = True
        self._sync_fps_hud()

    def _sync_fps_hud(self) -> None:
        """Refresh the glass chip. The main window owns its top-right anchor."""
        chip = self._fps_chip
        if self._fps_suppressed:
            chip.hide()
            return
        text = format_fps_hud_text(
            self._fps_paint_ms,
            self._fps_wall_ms,
            self._frame_id,
            idle=self._fps_idle_shown,
        )
        if not text:
            chip.hide()
            return
        first = not chip.isVisible()
        chip.set_hud_text(text)
        chip.show()
        self.apply_fps_place()
        # Reparent/raise after paint returns — doing it here re-enters the GL widget.
        if first and self._fps_host_hook is not None:
            QTimer.singleShot(0, self._fps_host_hook)

    def _draw_meshes(
        self,
        mvp: np.ndarray,
        model: np.ndarray,
        eye: np.ndarray,
    ) -> None:
        assert self._prog is not None
        if self._uloc is None:
            self._cache_prog_locs()
        U = self._uloc
        assert U is not None
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(self._prog)
        loc_mvp = U["mvp"]
        loc_model = U["model"]
        loc_cam = U["cam"]
        loc_flat = U["flat"]
        loc_use = U["use_tex"]
        loc_has_n = U["has_n"]
        loc_has_p = U["has_p"]
        loc_self = U["self"]
        loc_amb = U["amb"]
        loc_emis = U["emis"]
        loc_mat_edit = U["mat_edit"]
        loc_edit_emis = U["edit_emis"]
        loc_edit_rough = U["edit_rough"]
        loc_edit_metal = U["edit_metal"]
        loc_edit_spec = U["edit_spec"]
        loc_dbg = U["dbg"]
        loc_face = U["face_orient"]
        loc_albedo = U["albedo"]
        loc_normal = U["normal"]
        loc_param = U["param"]
        loc_pos = U["pos"]
        loc_nrm = U["nrm"]
        loc_uv = U["uv"]

        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp)
        GL.glUniformMatrix4fv(loc_model, 1, GL.GL_TRUE, model)
        GL.glUniform3f(loc_cam, float(eye[0]), float(eye[1]), float(eye[2]))
        GL.glUniform1i(loc_albedo, 0)
        GL.glUniform1i(loc_normal, 1)
        GL.glUniform1i(loc_param, 2)
        face_orient = bool(self._face_orient)
        GL.glUniform1f(loc_face, 1.0 if face_orient else 0.0)
        loc_two = U["two_sided"]
        shading = self._shading
        GL.glUniform1i(U["shadow"], 4)
        # Same Lit while orbiting and idle — orbit LOD flipped brightness (bright drag / dark release).
        scount = int(self._shadow_count)
        GL.glUniform1i(U["scount"], scount)
        GL.glUniform1i(U["lamp_count"], int(self._lamp_pack.get("count", 0)))
        for i in range(MAX_SHADOW_LAMPS):
            GL.glUniformMatrix4fv(U["shadow_vp"][i], 1, GL.GL_TRUE, self._shadow_vp[i])
        if self._shadow_tex and scount > 0:
            GL.glActiveTexture(GL.GL_TEXTURE4)
            GL.glBindTexture(GL.GL_TEXTURE_2D, int(self._shadow_tex))

        # Full Lit packs (lamps/sun/IBL) — re-upload only when lighting changes
        if self._lit_uniforms_dirty:
            amb = 0.18 if self._sun_enabled else self._ambient
            if self._moon_on and not self._sun_enabled:
                amb = min(amb, 0.06)
            if self._env.key != "none" and not (self._moon_on and not self._sun_enabled):
                amb = max(amb, self._env.ambient * 0.55)
            GL.glUniform1f(loc_amb, amb)
            GL.glUniform1f(loc_emis, self._emissive_scale)
            has_hdri = bool(self._use_hdri and self._hdri_tex is not None)
            # env=none keeps dark clear, but IBL samples a studio softbox so metal/glass still sparkle
            if self._env.key == "none" and not has_hdri:
                studio = get_env("studio")
                st = studio.sky_top
                sh = (0.38, 0.40, 0.46)  # brighter softbox — Lit metal/glass need it
            else:
                st = self._env.sky_top
                sh = self._env.sky_horizon
            GL.glUniform3f(U["sky_t"], *st)
            GL.glUniform3f(U["sky_h"], *sh)
            ibl = float(self._ibl_strength)
            if not has_hdri and self._env.key == "none":
                ibl = max(ibl, 0.85)
            elif not has_hdri:
                ibl = max(ibl, 0.55)
            GL.glUniform1f(U["ibl"], ibl)
            GL.glUniform1i(U["env_map"], 3)
            GL.glUniform1f(U["use_env"], 1.0 if has_hdri else 0.0)
            if has_hdri:
                GL.glActiveTexture(GL.GL_TEXTURE3)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._hdri_tex)

            moon = self._moon_on and not self._sun_enabled
            GL.glUniform1f(U["moon_on"], 1.0 if moon else 0.0)
            GL.glUniform3f(U["moon_dir"], *MOON_DIR)
            mi = self._moon_intensity
            GL.glUniform3f(U["moon_rad"], 0.55 * mi, 0.62 * mi, 0.85 * mi)

            pack = self._lamp_pack
            lamp_n = int(pack.get("count", 0))
            for i in range(lamp_n):
                GL.glUniform3f(
                    U["lamp_pos"][i],
                    float(pack["pos"][i, 0]),
                    float(pack["pos"][i, 1]),
                    float(pack["pos"][i, 2]),
                )
                GL.glUniform3f(
                    U["lamp_col"][i],
                    float(pack["col"][i, 0]),
                    float(pack["col"][i, 1]),
                    float(pack["col"][i, 2]),
                )
                GL.glUniform1f(U["lamp_power"][i], float(pack["power"][i]))
                GL.glUniform1f(U["lamp_range"][i], float(pack["range"][i]))
                GL.glUniform1f(U["lamp_mode"][i], float(pack["mode"][i]))
                GL.glUniform3f(
                    U["lamp_dir"][i],
                    float(pack["dir"][i, 0]),
                    float(pack["dir"][i, 1]),
                    float(pack["dir"][i, 2]),
                )
                GL.glUniform1f(U["lamp_cone"][i], float(pack["cone"][i]))
            for i in range(lamp_n, min(MAX_LAMPS, lamp_n + 8)):
                GL.glUniform1f(U["lamp_power"][i], 0.0)

            if self._sun_enabled:
                sx, sy, sz = sun_dir_zup(self._sun_az, self._sun_el)
                dirs = (
                    (sx, sy, sz),
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0),
                )
                rads = (self._sun_intensity, 0.0, 0.0, 0.0, SUN_FILL_RAD)
                ons = (True, False, False, False, True)
            elif self._moon_on:
                dirs = LIGHT_DIRS
                rads = (0.0, 0.0, 0.0, 0.0, 0.0)
                ons = (False, False, False, False, False)
            else:
                dirs = LIGHT_DIRS
                rads = LIGHT_RAD
                ons = self._light_on
            for i, (d, rad, on) in enumerate(zip(dirs, rads, ons)):
                GL.glUniform3f(U["lights"][i], *d)
                GL.glUniform1f(U["light_on"][i], 1.0 if on else 0.0)
                GL.glUniform3f(U["light_rad"][i], rad, rad, rad)
            self._lit_uniforms_dirty = False
        elif self._use_hdri and self._hdri_tex is not None:
            # HDRI tex unit must stay bound even when lamp packs are cached
            GL.glActiveTexture(GL.GL_TEXTURE3)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._hdri_tex)

        GL.glEnableVertexAttribArray(loc_pos)
        GL.glEnableVertexAttribArray(loc_nrm)
        GL.glEnableVertexAttribArray(loc_uv)
        for batch in self._batches:
            if not self._batch_visible(batch):
                continue
            albedo = batch.albedo
            if (
                self._albedo_force
                and self._albedo_force_stems
                and stems_match(batch.ref_stems(), self._albedo_force_stems)
            ):
                albedo = self._albedo_force

            use_maps = shading in (SHADING_MATERIAL, SHADING_RENDERED) and shading != SHADING_WIRE
            if shading in (SHADING_WIRE, SHADING_SOLID):
                _, use_tex = self._bind_tex(None, batch.color, unit=0)
                has_n = False
                has_p = False
            elif shading == SHADING_MATERIAL:
                _, use_tex = self._bind_tex(albedo, batch.color, unit=0)
                has_n = False
                has_p = False
                assert self._flat_normal_tex is not None
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._flat_normal_tex)
                assert self._flat_param_tex is not None
                GL.glActiveTexture(GL.GL_TEXTURE2)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._flat_param_tex)
            else:
                _, use_tex = self._bind_tex(albedo, batch.color, unit=0)
                has_n = bool(batch.has_normal)
                has_p = bool(batch.has_parameter)
                if has_n:
                    self._bind_tex(batch.normal, batch.color, unit=1)
                else:
                    assert self._flat_normal_tex is not None
                    GL.glActiveTexture(GL.GL_TEXTURE1)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, self._flat_normal_tex)
                if has_p:
                    self._bind_tex(batch.parameter, batch.color, unit=2)
                else:
                    assert self._flat_param_tex is not None
                    GL.glActiveTexture(GL.GL_TEXTURE2)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, self._flat_param_tex)

            dbg = self._debug_mode
            if shading == SHADING_MATERIAL and dbg == 0:
                # soft lit albedo preview (Blender Material Preview-ish)
                dbg = 0
            GL.glUniform1i(loc_dbg, dbg)
            GL.glUniform1f(loc_use, 1.0 if use_tex else 0.0)
            GL.glUniform1f(loc_has_n, 1.0 if has_n else 0.0)
            GL.glUniform1f(loc_has_p, 1.0 if has_p else 0.0)
            GL.glUniform1f(loc_self, self._self_illum_for(batch, has_p) if use_maps else 0.0)
            if self._batch_wants_mat_edit(batch):
                GL.glUniform1f(loc_mat_edit, 1.0)
                GL.glUniform1f(loc_edit_emis, self._edit_emissive)
                GL.glUniform1f(loc_edit_rough, self._edit_rough)
                GL.glUniform1f(loc_edit_metal, self._edit_metal)
                GL.glUniform1f(loc_edit_spec, self._edit_specular)
            else:
                GL.glUniform1f(loc_mat_edit, 0.0)
            GL.glUniform3f(loc_flat, *batch.color)

            # Face Orientation needs both sides; else per-material two-sided
            if face_orient or batch.two_sided:
                GL.glDisable(GL.GL_CULL_FACE)
            else:
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_BACK)
            GL.glUniform1f(loc_two, 1.0 if batch.two_sided else 0.0)

            self._draw_batch_tris(batch, loc_pos, loc_nrm, loc_uv)

        GL.glDisableVertexAttribArray(loc_pos)
        GL.glDisableVertexAttribArray(loc_nrm)
        GL.glDisableVertexAttribArray(loc_uv)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(0)

    def _bind_tex(
        self,
        path: str | None,
        color: tuple[float, float, float],
        unit: int = 0,
    ) -> tuple[int, bool]:
        GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
        assert self._placeholder_tex is not None
        if not path:
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._placeholder_tex)
            return self._placeholder_tex, False
        key = path
        cached = self._tex_cache.get(key)
        if cached is not None:
            GL.glBindTexture(GL.GL_TEXTURE_2D, cached)
            return cached, True
        if key in self._tex_missing:
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._placeholder_tex)
            return self._placeholder_tex, False
        if not Path(key).is_file():
            self._tex_missing.add(key)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._placeholder_tex)
            return self._placeholder_tex, False
        if self._tex_uploads_left <= 0:
            self._need_tex_pass = True
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._placeholder_tex)
            return self._placeholder_tex, False
        self._tex_uploads_left -= 1
        try:
            if key in self._decoded_cache:
                w, h, pixels = self._decoded_cache.pop(key)
            else:
                w, h, pixels = _load_rgba(path, flip_v=self._flip_texture_v)
            self._tex_cache[key] = self._make_texture(w, h, pixels)
        except Exception as e:
            print(f"trainz_studio: texture load failed {path}: {e}", flush=True)
            self._tex_missing.add(key)
            rgb = tuple(int(c * 255) for c in color)
            w, h, pixels = _placeholder_rgba(rgb)  # type: ignore[arg-type]
            self._tex_cache[key] = self._make_texture(w, h, pixels)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_cache[key])
            return self._tex_cache[key], False
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_cache[key])
        return self._tex_cache[key], True

    @staticmethod
    def _make_texture(w: int, h: int, pixels: bytes) -> int:
        # GL_LINEAR only — mipmaps made lit cabin ceilings look torn/blotchy on Trainz maps.
        tex = int(GL.glGenTextures(1))
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_RGBA,
            w,
            h,
            0,
            GL.GL_RGBA,
            GL.GL_UNSIGNED_BYTE,
            pixels,
        )
        return tex

    def _ensure_env_cache(self) -> None:
        """Build sky/ground once — rebuilding every paint caused the post-load hitch."""
        env = self._env
        extent = max(float(self._dist) * 6.0, 30.0)
        b = self._scene.bounds()
        if b is not None:
            mins, maxs = b
            extent = max(extent, float(np.linalg.norm(maxs - mins)) * 4.0)
        cx, cy, cz = float(self._target[0]), float(self._target[1]), float(self._target[2])
        # ground below mesh on XY (Z-up) so RGB axes stay visible
        z0 = -max(abs(cz) + extent * 0.15, 2.0)
        if b is not None:
            z0 = min(z0, float(b[0][2]) - max(0.5, float(np.linalg.norm(b[1] - b[0])) * 0.08))
        key = (env.key, round(extent, 1), round(cx, 1), round(cy, 1), round(z0, 2), self._show_ground)
        if key == self._env_cache_key and self._env_sky is not None:
            return
        self._env_cache_key = key

        top = env.sky_top
        hz = env.sky_horizon
        sky_rows: list[list[float]] = []
        bands = 6
        segs = 16
        rad = extent * 1.2
        for bi in range(bands):
            t0 = bi / bands
            t1 = (bi + 1) / bands
            elev0 = t0 * (math.pi * 0.48)
            elev1 = t1 * (math.pi * 0.48)
            c0 = tuple(hz[i] * (1 - t0) + top[i] * t0 for i in range(3))
            c1 = tuple(hz[i] * (1 - t1) + top[i] * t1 for i in range(3))
            for si in range(segs):
                a0 = (si / segs) * math.tau
                a1 = ((si + 1) / segs) * math.tau

                def pt(az: float, el: float, col: tuple[float, float, float]) -> list[float]:
                    return [
                        cx + math.cos(az) * math.cos(el) * rad,
                        cy + math.sin(az) * math.cos(el) * rad,
                        cz + math.sin(el) * rad,
                        *col,
                    ]

                sky_rows.append(pt(a0, elev0, c0))
                sky_rows.append(pt(a1, elev0, c0))
                sky_rows.append(pt(a1, elev1, c1))
                sky_rows.append(pt(a0, elev0, c0))
                sky_rows.append(pt(a1, elev1, c1))
                sky_rows.append(pt(a0, elev1, c1))
        self._env_sky = np.asarray(sky_rows, dtype=np.float32)

        self._env_ground = None
        if self._show_ground:
            g = env.ground
            half = extent
            self._env_ground = np.array(
                [
                    [cx - half, cy - half, z0, *g],
                    [cx + half, cy - half, z0, *g],
                    [cx + half, cy + half, z0, *g],
                    [cx - half, cy - half, z0, *g],
                    [cx + half, cy + half, z0, *g],
                    [cx - half, cy + half, z0, *g],
                ],
                dtype=np.float32,
            )

        extras: list[list[float]] = []
        if env.key == "mountains":
            cols = env.haze
            base_y = cy - extent * 0.85
            xs = np.linspace(cx - extent, cx + extent, 7)
            heights = [0.2, 0.5, 0.3, 0.65, 0.35, 0.45, 0.18]
            for i in range(len(xs) - 1):
                h0 = heights[i] * extent * 0.45
                h1 = heights[i + 1] * extent * 0.45
                extras.extend(
                    [
                        [xs[i], base_y, z0, *cols],
                        [xs[i + 1], base_y, z0, *cols],
                        [(xs[i] + xs[i + 1]) * 0.5, base_y, z0 + max(h0, h1), *cols],
                    ]
                )
        elif env.key == "harbor" and self._show_ground:
            half = extent
            extras.extend(
                [
                    [cx - half, cy - half, z0 - 0.2, 0.08, 0.18, 0.28],
                    [cx + half, cy - half, z0 - 0.2, 0.08, 0.18, 0.28],
                    [cx + half, cy + half, z0 - 0.2, 0.10, 0.26, 0.36],
                    [cx - half, cy - half, z0 - 0.2, 0.08, 0.18, 0.28],
                    [cx + half, cy + half, z0 - 0.2, 0.10, 0.26, 0.36],
                    [cx - half, cy + half, z0 - 0.2, 0.09, 0.22, 0.32],
                ]
            )
        self._env_extra = np.asarray(extras, dtype=np.float32) if extras else None

    def _draw_sky(self, view: np.ndarray, proj: np.ndarray) -> None:
        """Equirect / procedural sky only — sun/moon are separate meshes."""
        if self._sky_prog is None:
            return
        has_hdri = bool(self._use_hdri and self._hdri_tex is not None)
        view_rot = np.array(view, dtype=np.float32, copy=True)
        view_rot[0, 3] = 0.0
        view_rot[1, 3] = 0.0
        view_rot[2, 3] = 0.0
        mvp = proj @ view_rot
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self._sky_prog)
        p = self._sky_prog
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(p, "u_mvp"), 1, GL.GL_TRUE, mvp)
        GL.glUniform1i(GL.glGetUniformLocation(p, "u_env_map"), 0)
        GL.glUniform1f(GL.glGetUniformLocation(p, "u_use_env_map"), 1.0 if has_hdri else 0.0)
        st = self._env.sky_top
        sh = self._env.sky_horizon
        sg = (st[0] * 0.25, st[1] * 0.25, st[2] * 0.28)
        GL.glUniform3f(GL.glGetUniformLocation(p, "u_sky_top"), *st)
        GL.glUniform3f(GL.glGetUniformLocation(p, "u_sky_horizon"), *sh)
        GL.glUniform3f(GL.glGetUniformLocation(p, "u_sky_ground"), *sg)
        GL.glUniform1f(GL.glGetUniformLocation(p, "u_exposure"), float(self._sky_exposure))
        GL.glActiveTexture(GL.GL_TEXTURE0)
        if has_hdri:
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._hdri_tex)
        elif self._placeholder_tex is not None:
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._placeholder_tex)
        loc_pos = GL.glGetAttribLocation(p, "in_pos")
        data = _SKY_CUBE
        base = data.ctypes.data
        GL.glEnableVertexAttribArray(loc_pos)
        GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, False, 12, ctypes.c_void_p(base))
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, data.shape[0])
        GL.glDisableVertexAttribArray(loc_pos)
        GL.glUseProgram(0)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def _ensure_celestial_locals(self) -> None:
        """Build unit sun/moon soups once — translating every paint was GC death."""
        if self._sun_enabled:
            key = ("sun", round(float(self._sun_intensity), 2))
            if key == self._celestial_key and self._sun_body_local is not None:
                return
            inten = 0.85 + 0.35 * self._sun_intensity
            self._sun_body_local = uv_sphere_colored(
                (0.0, 0.0, 0.0), 1.0, kind="sun", intensity=inten
            )
            self._sun_glow_local = sun_corona_shell(
                (0.0, 0.0, 0.0), 1.0, intensity=self._sun_intensity
            )
            self._moon_body_local = None
            self._celestial_key = key
            return
        if self._moon_on:
            key = ("moon", round(float(self._moon_intensity), 2))
            if key == self._celestial_key and self._moon_body_local is not None:
                return
            self._moon_body_local = uv_sphere_colored(
                (0.0, 0.0, 0.0),
                1.0,
                kind="moon",
                segments=28,
                rings=16,
                intensity=0.7 + 0.6 * self._moon_intensity,
            )
            self._sun_body_local = None
            self._sun_glow_local = None
            self._celestial_key = key

    @staticmethod
    def _place_local_mesh(
        local: np.ndarray, center: tuple[float, float, float], radius: float
    ) -> np.ndarray:
        out = np.empty_like(local)
        out[:, 0:3] = local[:, 0:3] * float(radius) + np.asarray(center, dtype=np.float32)
        out[:, 3:6] = local[:, 3:6]
        return out

    def _draw_celestials(self, eye: np.ndarray, mvp: np.ndarray) -> None:
        """Sky-locked sun/moon sphere meshes (visible with env=none, no fog)."""
        dist = _CELESTIAL_DIST
        self._ensure_celestial_locals()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)
        try:
            if self._sun_enabled and self._sun_body_local is not None:
                sx, sy, sz = sun_dir_zup(self._sun_az, self._sun_el)
                center = (
                    float(eye[0]) + sx * dist,
                    float(eye[1]) + sy * dist,
                    float(eye[2]) + sz * dist,
                )
                rad = dist * 0.038 * (0.75 + 0.25 * min(self._sun_intensity, 2.0))
                # glow local already includes 1.55× from sun_corona_shell(radius=1)
                if self._sun_glow_local is not None:
                    self._draw_colored_tris(
                        self._place_local_mesh(self._sun_glow_local, center, rad), mvp
                    )
                self._draw_colored_tris(
                    self._place_local_mesh(self._sun_body_local, center, rad), mvp
                )
            elif self._moon_on and self._moon_body_local is not None:
                mx, my, mz = MOON_DIR
                n = math.sqrt(mx * mx + my * my + mz * mz) + 1e-9
                mx, my, mz = mx / n, my / n, mz / n
                center = (
                    float(eye[0]) + mx * dist,
                    float(eye[1]) + my * dist,
                    float(eye[2]) + mz * dist,
                )
                rad = dist * 0.048
                self._draw_colored_tris(
                    self._place_local_mesh(self._moon_body_local, center, rad), mvp
                )
        finally:
            GL.glDepthMask(GL.GL_TRUE)
            GL.glEnable(GL.GL_DEPTH_TEST)

    def _draw_environment(self, mvp: np.ndarray) -> None:
        self._ensure_env_cache()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)
        if self._env_sky is not None:
            self._draw_colored_tris(self._env_sky, mvp)
        GL.glEnable(GL.GL_DEPTH_TEST)
        if self._show_ground and self._env_ground is not None:
            self._draw_colored_tris(self._env_ground, mvp)
        if self._env_extra is not None and self._env_extra.size:
            self._draw_colored_tris(self._env_extra, mvp)
        # leave cull disabled

    def _cache_line_locs(self) -> None:
        if self._line_prog is None:
            self._lloc = None
            return
        p = self._line_prog
        self._lloc = {
            "mvp": GL.glGetUniformLocation(p, "u_mvp"),
            "pos": GL.glGetAttribLocation(p, "in_pos"),
            "col": GL.glGetAttribLocation(p, "in_col"),
        }

    def _draw_colored_tris(self, verts: np.ndarray, mvp: np.ndarray) -> None:
        if verts.size == 0 or self._line_prog is None:
            return
        if self._lloc is None:
            self._cache_line_locs()
        U = self._lloc
        if U is None:
            return
        data = np.ascontiguousarray(verts, dtype=np.float32)
        GL.glUseProgram(self._line_prog)
        GL.glUniformMatrix4fv(U["mvp"], 1, GL.GL_TRUE, mvp)
        base = data.ctypes.data
        GL.glEnableVertexAttribArray(U["pos"])
        GL.glEnableVertexAttribArray(U["col"])
        GL.glVertexAttribPointer(U["pos"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(base))
        GL.glVertexAttribPointer(U["col"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(base + 12))
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, data.shape[0])
        GL.glDisableVertexAttribArray(U["pos"])
        GL.glDisableVertexAttribArray(U["col"])
        GL.glUseProgram(0)

    def _draw_lines(self, lines: np.ndarray, mvp: np.ndarray, width: float = 1.0) -> None:
        if lines.size == 0 or self._line_prog is None:
            return
        if self._lloc is None:
            self._cache_line_locs()
        U = self._lloc
        if U is None:
            return
        verts = np.ascontiguousarray(lines, dtype=np.float32)
        GL.glUseProgram(self._line_prog)
        GL.glUniformMatrix4fv(U["mvp"], 1, GL.GL_TRUE, mvp)
        GL.glLineWidth(width)
        base = verts.ctypes.data
        GL.glEnableVertexAttribArray(U["pos"])
        GL.glEnableVertexAttribArray(U["col"])
        GL.glVertexAttribPointer(U["pos"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(base))
        GL.glVertexAttribPointer(U["col"], 3, GL.GL_FLOAT, False, 24, ctypes.c_void_p(base + 12))
        GL.glDrawArrays(GL.GL_LINES, 0, verts.shape[0])
        GL.glDisableVertexAttribArray(U["pos"])
        GL.glDisableVertexAttribArray(U["col"])
        GL.glLineWidth(1.0)
        GL.glUseProgram(0)

    def _lamp_glow_sprites(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Soft bulbs ONLY for Glow+cast-enabled lamps (never for idle bulbs)."""
        if not self._lamp_markers:
            return (
                np.zeros((0, 3), dtype=np.float32),
                np.zeros((0, 3), dtype=np.float32),
                np.zeros((0,), dtype=np.float32),
            )
        centers: list[list[float]] = []
        colors: list[list[float]] = []
        radii: list[float] = []
        for pos, col, enabled, bright, range_m in self._lamp_markers:
            if not enabled or bright <= 1e-4:
                continue
            centers.append([pos[0], pos[1], pos[2]])
            colors.append([col[0], col[1], col[2]])
            radii.append(max(min(float(range_m) * 0.22, self._dist * 0.07), 0.10))
        if not centers:
            return (
                np.zeros((0, 3), dtype=np.float32),
                np.zeros((0, 3), dtype=np.float32),
                np.zeros((0,), dtype=np.float32),
            )
        return (
            np.asarray(centers, dtype=np.float32),
            np.asarray(colors, dtype=np.float32),
            np.asarray(radii, dtype=np.float32),
        )

    def _lamp_gizmo_crosses(
        self, *, enabled_only: bool = False, disabled_only: bool = False
    ) -> np.ndarray:
        """Tiny axis crosses for bulb positions (gizmo mode — not light)."""
        rows: list[list[float]] = []
        s = max(self._dist * 0.012, 0.04)
        for pos, col, enabled, bright, _range_m in self._lamp_markers:
            if enabled_only and not enabled:
                continue
            if disabled_only and enabled:
                continue
            x, y, z = pos
            # dim gray when off; tint when on (on usually uses soft sprite instead)
            if enabled:
                r, g, b = col
            else:
                r, g, b = (0.55, 0.55, 0.58)
            rows.extend(
                [
                    [x - s, y, z, r, g, b],
                    [x + s, y, z, r, g, b],
                    [x, y - s, z, r, g, b],
                    [x, y + s, z, r, g, b],
                    [x, y, z - s, r, g, b],
                    [x, y, z + s, r, g, b],
                ]
            )
            _ = bright
        if not rows:
            return np.zeros((0, 6), dtype=np.float32)
        return np.asarray(rows, dtype=np.float32)

    def _draw_glow_sprites(
        self,
        centers: np.ndarray,
        colors: np.ndarray,
        radii: np.ndarray,
        mvp: np.ndarray,
    ) -> None:
        """Additive soft discs at world points (lamp / mat / a.* pick)."""
        if self._glow_prog is None or centers.size == 0:
            return
        right, up = self._cam_basis()
        verts, idx = glow_billboard_mesh(centers, colors, radii, right, up)
        if verts.size == 0:
            return
        data = np.ascontiguousarray(verts, dtype=np.float32)
        indices = np.ascontiguousarray(idx, dtype=np.uint32)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
        GL.glDepthMask(GL.GL_FALSE)
        # keep depth test so bulbs occlude behind solid walls a bit; overshoot with size
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(self._glow_prog)
        loc_mvp = GL.glGetUniformLocation(self._glow_prog, "u_mvp")
        loc_pos = GL.glGetAttribLocation(self._glow_prog, "in_pos")
        loc_col = GL.glGetAttribLocation(self._glow_prog, "in_col")
        loc_uv = GL.glGetAttribLocation(self._glow_prog, "in_uv")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp)
        base = data.ctypes.data
        GL.glEnableVertexAttribArray(loc_pos)
        GL.glEnableVertexAttribArray(loc_col)
        if loc_uv >= 0:
            GL.glEnableVertexAttribArray(loc_uv)
        GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base))
        GL.glVertexAttribPointer(loc_col, 3, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base + 12))
        if loc_uv >= 0:
            GL.glVertexAttribPointer(loc_uv, 2, GL.GL_FLOAT, False, 32, ctypes.c_void_p(base + 24))
        GL.glDrawElements(
            GL.GL_TRIANGLES,
            int(indices.shape[0]),
            GL.GL_UNSIGNED_INT,
            indices.ctypes.data_as(ctypes.c_void_p),
        )
        GL.glDisableVertexAttribArray(loc_pos)
        GL.glDisableVertexAttribArray(loc_col)
        if loc_uv >= 0:
            GL.glDisableVertexAttribArray(loc_uv)
        GL.glUseProgram(0)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_BLEND)
        GL.glDepthMask(GL.GL_TRUE)

    def _grid_lines(self) -> np.ndarray:
        """XY ground grid at Z=0 (Trainz Z-up)."""
        if self._grid_cache is not None:
            return self._grid_cache
        rows: list[list[float]] = []
        c = (0.30, 0.32, 0.35)
        for i in range(-20, 21):
            rows.append([i, -20.0, 0.0, *c])
            rows.append([i, 20.0, 0.0, *c])
            rows.append([-20.0, i, 0.0, *c])
            rows.append([20.0, i, 0.0, *c])
        self._grid_cache = np.asarray(rows, dtype=np.float32)
        return self._grid_cache

    def _world_axes_lines(self) -> np.ndarray:
        L = max(self._dist * 0.15, 0.5)
        return np.asarray(
            [
                [0, 0, 0, 0.95, 0.25, 0.22],
                [L, 0, 0, 0.95, 0.25, 0.22],
                [0, 0, 0, 0.25, 0.88, 0.35],
                [0, L, 0, 0.25, 0.88, 0.35],
                [0, 0, 0, 0.28, 0.50, 1.0],
                [0, 0, L, 0.28, 0.50, 1.0],
            ],
            dtype=np.float32,
        )

    def _attachment_lines(self, att: Attachment, *, selected: bool = False) -> np.ndarray:
        return attachment_gizmo_lines(att, selected=selected, dist=self._dist)

    def _sun_gizmo_lines(self) -> np.ndarray:
        """Yellow line from origin toward -sun_dir (incoming ray hint)."""
        sx, sy, sz = sun_dir_zup(self._sun_az, self._sun_el)
        L = max(self._dist * 0.35, 1.0)
        return np.asarray(
            [
                [0.0, 0.0, 0.0, 1.0, 0.92, 0.25],
                [-sx * L, -sy * L, -sz * L, 1.0, 0.92, 0.25],
            ],
            dtype=np.float32,
        )

    def _draw_corner_gizmo(self, w: int, h: int) -> None:
        """Small XYZ triad in the lower-left that only follows orbit (not pan/zoom)."""
        size = 96
        margin = 12
        GL.glViewport(margin, margin, size, size)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        eye = np.array(
            [
                math.cos(pitch) * math.sin(yaw),
                math.cos(pitch) * math.cos(yaw),
                math.sin(pitch),
            ],
            dtype=np.float64,
        )
        view = _look_at_mat(eye * 2.6, np.zeros(3), WORLD_UP.copy())
        proj = _perspective_mat(35.0, 1.0, 0.1, 20.0)
        mvp = proj @ view
        L = 0.85
        lines = np.asarray(
            [
                [0, 0, 0, 0.95, 0.25, 0.22],
                [L, 0, 0, 0.95, 0.25, 0.22],
                [0, 0, 0, 0.25, 0.88, 0.35],
                [0, L, 0, 0.25, 0.88, 0.35],
                [0, 0, 0, 0.28, 0.50, 1.0],
                [0, 0, L, 0.28, 0.50, 1.0],
            ],
            dtype=np.float32,
        )
        self._draw_lines(lines, mvp, width=3.0)
        GL.glViewport(0, 0, w, h)

    def _mvp_for_pick(self) -> tuple[np.ndarray, int, int]:
        w = max(1, int(self.width()))
        h = max(1, int(self.height()))
        aspect = w / float(h)
        eye = self._eye()
        view = _look_at_mat(eye, self._target, WORLD_UP)
        proj = _perspective_mat(_focal_mm_to_fovy(self._focal_mm), aspect, 0.05, 5000.0)
        mvp = proj @ view
        return mvp, w, h

    def pick_attachment_at(self, sx: float, sy: float, *, radius_px: float = 22.0) -> int:
        """Screen pick among visible a.* gizmos. -1 if none under cursor."""
        if not self._show_atts or not self._scene.attachments:
            return -1
        mvp, w, h = self._mvp_for_pick()
        # scale pick radius with gizmo on-screen size (near camera → larger)
        rad = max(14.0, float(radius_px) * (28.0 / max(8.0, float(self._dist))))
        skip = {
            i
            for i, att in enumerate(self._scene.attachments)
            if self._att_is_hidden(att)
        }
        return pick_attachment_index(
            self._scene.attachments,
            mvp,
            sx,
            sy,
            w,
            h,
            radius_px=rad,
            skip_index=skip or None,
        )

    def pick_translate_handle_at(self, sx: float, sy: float) -> str | None:
        """Pick free/x/y/z on the editable a.* Move gizmo. None = miss (orbit)."""
        idx = self._edit_att_index
        if idx < 0 or idx >= len(self._scene.attachments):
            return None
        mvp, w, h = self._mvp_for_pick()
        scale = 28.0 / max(8.0, float(self._dist))
        return pick_translate_handle(
            self._scene.attachments[idx],
            mvp,
            sx,
            sy,
            w,
            h,
            dist=self._dist,
            free_radius_px=max(12.0, 14.0 * scale),
            axis_radius_px=max(8.0, 10.0 * scale),
        )

    def mousePressEvent(self, event) -> None:
        self._wake_cam_timer()
        self._last = event.position().toPoint()
        self._alt_pick_armed = False
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        mods = event.modifiers() | QGuiApplication.keyboardModifiers()
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        if event.button() == Qt.MouseButton.LeftButton and alt and self._show_atts:
            # Alt+LMB: pick a.* under cursor (then Move-mode gizmo drag)
            hit = self.pick_attachment_at(
                float(self._last.x()), float(self._last.y())
            )
            if hit >= 0:
                self._alt_pick_armed = True
                self._cancel_fly()
                event.accept()
                self.attachment_picked.emit(hit)
                return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._edit_att_index >= 0
            and not alt
        ):
            handle = self.pick_translate_handle_at(
                float(self._last.x()), float(self._last.y())
            )
            if handle is not None:
                self._att_dragging = True
                self._att_drag_axis = handle
                self._cancel_fly()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                self.attachment_drag_started.emit(self._edit_att_index)
                return
            # miss gizmo → fall through to orbit (Blender-like)

    def mouseMoveEvent(self, event) -> None:
        if self._last is None:
            return
        p = event.position().toPoint()
        dx = float(p.x() - self._last.x())
        dy = float(p.y() - self._last.y())
        self._last = p
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._alt_pick_armed:
                return  # Alt+pick click — don't orbit on the same gesture
            self._cancel_fly()
            # Selected a.* Move: LMB on handle; Alt+LMB (miss) still orbits
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            if self._att_dragging and self._edit_att_index >= 0 and not alt:
                self._drag_edit_attachment(dx, dy, event.modifiers())
                return
            # Natural orbit: content follows drag (yaw was inverted vs look-at X).
            self._yaw_vel += dx * 0.045
            self._pitch_vel += dy * 0.045
            self._yaw_vel = float(np.clip(self._yaw_vel, -8.0, 8.0))
            self._pitch_vel = float(np.clip(self._pitch_vel, -8.0, 8.0))
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            self._cancel_fly()
            # MMB = slow pan: L/R horizontal + U/D elevation
            scale = self._dist * 0.00035
            self._elev_vel += -dy * scale
            self._elev_vel = float(np.clip(self._elev_vel, -self._dist * 0.04, self._dist * 0.04))
            right, _up = self._cam_basis()
            _fwd, right_h = horizontal_walk_dirs(self._target - self._eye(), right)
            self._move_vel = self._move_vel - right_h * dx * scale
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._alt_pick_armed = False
        if self._att_dragging and event.button() == Qt.MouseButton.LeftButton:
            idx = self._edit_att_index
            self._att_dragging = False
            self._att_drag_axis = "free"
            if 0 <= idx < len(self._scene.attachments):
                pos = self._scene.attachments[idx].pos
                self.attachment_drag_finished.emit(
                    idx, float(pos[0]), float(pos[1]), float(pos[2])
                )
            if self._edit_att_index >= 0:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.unsetCursor()
        self._last = None

    def _drag_edit_attachment(self, dx: float, dy: float, modifiers) -> None:
        idx = self._edit_att_index
        if idx < 0 or idx >= len(self._scene.attachments):
            return
        fine = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        right, up = self._cam_basis()
        axis = getattr(self, "_att_drag_axis", "free") or "free"
        att = self._scene.attachments[idx]
        if axis in ("x", "y", "z"):
            m = np.asarray(att.orient, dtype=np.float64).reshape(3, 3)
            col = {"x": 0, "y": 1, "z": 2}[axis]
            delta = screen_delta_along_axis(
                dx, dy, m[col], dist=self._dist, right=right, up=up, fine=fine
            )
        else:
            delta = screen_delta_to_world(
                dx, dy, dist=self._dist, right=right, up=up, fine=fine
            )
        nx = float(att.pos[0] + delta[0])
        ny = float(att.pos[1] + delta[1])
        nz = float(att.pos[2] + delta[2])
        att.pos = (nx, ny, nz)
        # Blender: orbit target stays put while translating — don't chase the point
        self.attachment_moved.emit(idx, nx, ny, nz)
        self.update()

    def wheelEvent(self, event) -> None:
        # Wheel = dolly (dist). Ctrl+wheel = lens FOV (mm). Ctrl+Shift = finer FOV.
        pixel = event.pixelDelta().y()
        angle = event.angleDelta().y()
        if pixel != 0:
            impulse = -pixel * 0.0018  # trackpad / smooth scroll
        elif angle != 0:
            impulse = -angle / 120.0 * 0.085  # notch ≈ one step
        else:
            return
        self._wake_cam_timer()
        self._cancel_fly()
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            # scroll up → longer focal (tele / magnify); opposite of dolly sign
            scale = 0.22 if (mods & Qt.KeyboardModifier.ShiftModifier) else 1.0
            self._focal_vel = float(
                np.clip(self._focal_vel - impulse * scale, -0.28, 0.28)
            )
        else:
            self._zoom_vel = float(np.clip(self._zoom_vel + impulse, -0.28, 0.28))
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
        ):
            self._cancel_fly()
            self._keys_down.add(int(key))
            event.accept()
            return
        if key == Qt.Key.Key_R:
            self.reset_camera()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        key = int(event.key())
        self._keys_down.discard(key)
        super().keyReleaseEvent(event)

    def _tick_camera(self) -> None:
        # HOME / hidden GL: sleep the timer — was burning ~60 wakeups/s idle.
        if not self.isVisible() or not self._render_active:
            if self._cam_timer.interval() != 120:
                self._cam_timer.setInterval(120)
            return
        dirty = False
        if self._fly_active:
            u = (time.perf_counter() - self._fly_t0) / self._fly_dur
            if u >= 1.0:
                self._target = np.array(self._fly_to_tgt, dtype=np.float64, copy=True)
                self._dist = float(self._fly_to_dist)
                self._fly_active = False
            else:
                e = ease_out_cubic(u)
                self._target = self._fly_from_tgt + (self._fly_to_tgt - self._fly_from_tgt) * e
                self._dist = float(
                    self._fly_from_dist + (self._fly_to_dist - self._fly_from_dist) * e
                )
            dirty = True
        if abs(self._yaw_vel) > 1e-4 or abs(self._pitch_vel) > 1e-4:
            self._yaw += self._yaw_vel
            self._pitch = float(np.clip(self._pitch + self._pitch_vel, -89.0, 89.0))
            self._yaw_vel *= 0.82
            self._pitch_vel *= 0.82
            if abs(self._yaw_vel) < 1e-3:
                self._yaw_vel = 0.0
            if abs(self._pitch_vel) < 1e-3:
                self._pitch_vel = 0.0
            dirty = True

        # wheel zoom inertia (multiplicative — feels even at any distance)
        if abs(self._zoom_vel) > 1e-5:
            self._dist = float(np.clip(self._dist * (1.0 + self._zoom_vel), 0.2, 5000.0))
            self._zoom_vel *= 0.82
            if abs(self._zoom_vel) < 1e-4:
                self._zoom_vel = 0.0
            dirty = True

        # Ctrl+wheel lens FOV (focal mm) inertia
        if abs(self._focal_vel) > 1e-5:
            self._focal_mm = float(
                np.clip(self._focal_mm * (1.0 + self._focal_vel), _FOCAL_MM_MIN, _FOCAL_MM_MAX)
            )
            self._focal_vel *= 0.82
            if abs(self._focal_vel) < 1e-4:
                self._focal_vel = 0.0
            dirty = True

        # MMB / PgUp elev inertia (Trainz +Z up)
        if abs(self._elev_vel) > 1e-6:
            self._target = self._target + np.array([0.0, 0.0, self._elev_vel])
            self._elev_vel *= 0.78
            if abs(self._elev_vel) < 1e-5:
                self._elev_vel = 0.0
            dirty = True

        # walk: Up/Down = forward/back on XY, Left/Right = strafe (Z-up)
        if self._keys_down:
            right, _up = self._cam_basis()
            forward, right_h = horizontal_walk_dirs(self._target - self._eye(), right)
            step = self._dist * 0.0032
            if int(Qt.Key.Key_Up) in self._keys_down:
                self._move_vel = self._move_vel + forward * step
            if int(Qt.Key.Key_Down) in self._keys_down:
                self._move_vel = self._move_vel - forward * step
            if int(Qt.Key.Key_Left) in self._keys_down:
                self._move_vel = self._move_vel - right_h * step
            if int(Qt.Key.Key_Right) in self._keys_down:
                self._move_vel = self._move_vel + right_h * step
            elev_step = self._dist * 0.0028
            if int(Qt.Key.Key_PageUp) in self._keys_down:
                self._elev_vel += elev_step
            if int(Qt.Key.Key_PageDown) in self._keys_down:
                self._elev_vel -= elev_step
            dirty = True

        if float(np.linalg.norm(self._move_vel)) > 1e-6:
            self._target = self._target + self._move_vel
            self._move_vel *= 0.80
            if float(np.linalg.norm(self._move_vel)) < 1e-4:
                self._move_vel[:] = 0.0
            dirty = True

        was_busy = self._cam_busy
        self._cam_busy = bool(dirty)
        if was_busy and not self._cam_busy:
            # Side frost skipped grabs during orbit — refresh once when idle.
            parent = self.parent()
            while parent is not None and not hasattr(parent, "_refresh_side_frost"):
                parent = parent.parent()
            if parent is not None:
                QTimer.singleShot(40, parent._refresh_side_frost)

        # Stay at 16ms while visible — dropping to 33ms made orbit/dolly steppy.
        if self._cam_timer.interval() != 16:
            self._cam_timer.setInterval(16)

        if dirty:
            self.update()
        elif self._show_fps:
            # F3 used to call update() every 16ms while idle, so Lit never rested.
            self._mark_fps_idle_if_settled()

    def _eye(self) -> np.ndarray:
        """Orbit eye in Trainz Z-up: pitch elevates +Z, yaw spins about Z."""
        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        x = self._dist * math.cos(pitch) * math.sin(yaw)
        y = self._dist * math.cos(pitch) * math.cos(yaw)
        z = self._dist * math.sin(pitch)
        return self._target + np.array([x, y, z])

    def _cam_basis(self) -> tuple[np.ndarray, np.ndarray]:
        eye = self._eye()
        forward = self._target - eye
        forward = forward / (np.linalg.norm(forward) + 1e-12)
        world_up = WORLD_UP
        right = np.cross(forward, world_up)
        if np.linalg.norm(right) < 1e-8:
            right = np.array([1.0, 0.0, 0.0])
        else:
            right = right / np.linalg.norm(right)
        up = np.cross(right, forward)
        up = up / (np.linalg.norm(up) + 1e-12)
        return right, up
