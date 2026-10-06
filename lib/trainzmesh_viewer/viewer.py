"""Minimal OpenGL mesh viewer (pygame-ce + moderngl)."""

from __future__ import annotations

import math
import os
import sys
from typing import List, Optional

import numpy as np

from .parser import SubMesh, TrainzMesh, parse_trainzmesh
from .textures import load_rgba, make_placeholder, resolve_texture_path


VERT = """
#version 330
in vec3 in_pos;
in vec3 in_nrm;
in vec2 in_uv;
uniform mat4 m_mvp;
uniform mat4 m_model;
out vec3 v_nrm;
out vec2 v_uv;
out vec3 v_world;
void main() {
    vec4 world = m_model * vec4(in_pos, 1.0);
    v_world = world.xyz;
    v_nrm = mat3(m_model) * in_nrm;
    v_uv = in_uv;
    gl_Position = m_mvp * vec4(in_pos, 1.0);
}
"""

FRAG = """
#version 330
in vec3 v_nrm;
in vec2 v_uv;
in vec3 v_world;
uniform sampler2D u_albedo;
uniform vec3 u_light_dir;
uniform vec3 u_cam_pos;
out vec4 f_color;
void main() {
    vec4 albedo = texture(u_albedo, v_uv);
    if (albedo.a < 0.05) discard;
    vec3 n = normalize(v_nrm);
    vec3 l = normalize(u_light_dir);
    float ndl = max(dot(n, l), 0.0);
    float amb = 0.28;
    vec3 view = normalize(u_cam_pos - v_world);
    vec3 h = normalize(l + view);
    float spec = pow(max(dot(n, h), 0.0), 48.0) * 0.25;
    vec3 col = albedo.rgb * (amb + ndl * 0.85) + vec3(spec);
    f_color = vec4(col, albedo.a);
}
"""


def _look_at(eye, target, up):
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / max(np.linalg.norm(s), 1e-8)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    t = np.eye(4, dtype=np.float32)
    t[0, 3] = -eye[0]
    t[1, 3] = -eye[1]
    t[2, 3] = -eye[2]
    return m @ t


def _perspective(fovy_deg, aspect, znear, zfar):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (zfar + znear) / (znear - zfar)
    m[2, 3] = (2 * zfar * znear) / (znear - zfar)
    m[3, 2] = -1.0
    return m


class DrawMesh:
    def __init__(self, ctx, prog, sub: SubMesh, mesh_dir: str):
        import moderngl

        positions = [(p[0], p[2], -p[1]) for p in sub.positions]
        normals = [(n[0], n[2], -n[1]) for n in sub.normals]
        uvs = sub.uvs
        idx = np.asarray(sub.indices, dtype=np.uint32)
        vcount = len(positions)
        interleaved = np.zeros((vcount, 8), dtype=np.float32)
        interleaved[:, 0:3] = positions
        interleaved[:, 3:6] = normals
        interleaved[:, 6:8] = uvs
        self.vbo = ctx.buffer(interleaved.tobytes())
        self.ibo = ctx.buffer(idx.tobytes())
        self.vao = ctx.vertex_array(
            prog,
            [(self.vbo, "3f 3f 2f", "in_pos", "in_nrm", "in_uv")],
            self.ibo,
        )
        tex_path = resolve_texture_path(mesh_dir, sub.albedo) if sub.albedo else None
        if tex_path:
            w, h, pixels = load_rgba(tex_path)
        else:
            w, h, pixels = make_placeholder((170, 175, 185))
        self.texture = ctx.texture((w, h), 4, pixels)
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.texture.repeat_x = True
        self.texture.repeat_y = True


def _compute_bounds(mesh: TrainzMesh):
    pts = []
    for sub in mesh.submeshes:
        for p in sub.positions:
            pts.append((p[0], p[2], -p[1]))
    arr = np.asarray(pts, dtype=np.float64)
    mins = arr.min(axis=0)
    maxs = arr.max(axis=0)
    center = (mins + maxs) * 0.5
    radius = float(np.linalg.norm(maxs - mins) * 0.5)
    return center, max(radius, 0.05)


def run_viewer(path: str, width: int = 1280, height: int = 800) -> None:
    import moderngl
    import pygame

    mesh = parse_trainzmesh(path)
    print(f"Loaded {path}")
    for w in mesh.warnings:
        print(" ", w)
    for i, sub in enumerate(mesh.submeshes):
        print(
            f"  [{i}] {sub.name} fmt={sub.format} "
            f"verts={len(sub.positions)} tris={len(sub.indices)//3} "
            f"albedo={sub.albedo or '-'} mat={sub.material_type or '-'}"
        )

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE)
    pygame.display.set_caption(f"TrainzMesh Viewer — {os.path.basename(path)}")

    ctx = moderngl.create_context()
    ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)

    draw_list = [DrawMesh(ctx, prog, sub, mesh.directory) for sub in mesh.submeshes]
    center, radius = _compute_bounds(mesh)

    yaw = 0.6
    pitch = 0.35
    dist = radius * 2.8
    dragging = False
    last = (0, 0)
    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_r:
                    yaw, pitch, dist = 0.6, 0.35, radius * 2.8
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    dragging = True
                    last = event.pos
                elif event.button == 4:
                    dist = max(radius * 0.2, dist * 0.9)
                elif event.button == 5:
                    dist = min(radius * 40.0, dist * 1.1)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last[0]
                dy = event.pos[1] - last[1]
                last = event.pos
                yaw += dx * 0.005
                pitch = max(-1.4, min(1.4, pitch + dy * 0.005))
            elif event.type == pygame.VIDEORESIZE:
                width, height = max(event.w, 100), max(event.h, 100)
                ctx.viewport = (0, 0, width, height)

        eye = center + np.array(
            [
                dist * math.cos(pitch) * math.sin(yaw),
                dist * math.sin(pitch),
                dist * math.cos(pitch) * math.cos(yaw),
            ],
            dtype=np.float64,
        )
        view = _look_at(eye, center, np.array([0.0, 1.0, 0.0]))
        proj = _perspective(50.0, width / max(height, 1), max(0.01, radius * 0.01), radius * 80.0)
        model = np.eye(4, dtype=np.float32)
        mvp = proj @ view @ model

        ctx.clear(0.12, 0.13, 0.15)
        prog["m_mvp"].write(mvp.T.astype(np.float32).tobytes())
        prog["m_model"].write(model.T.astype(np.float32).tobytes())
        prog["u_light_dir"].value = (0.45, 0.85, 0.35)
        prog["u_cam_pos"].value = tuple(float(c) for c in eye)

        for dm in draw_list:
            dm.texture.use(0)
            prog["u_albedo"] = 0
            dm.vao.render()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def _write_obj(mesh: TrainzMesh, out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# trainz_studio.lib.trainzmesh_viewer export of {os.path.basename(mesh.path)}\n")
        vbase = 1
        for sub in mesh.submeshes:
            f.write(f"o {sub.name}\n")
            if sub.albedo:
                f.write(f"# albedo {sub.albedo}\n")
            for p in sub.positions:
                f.write(f"v {p[0]:.6f} {p[2]:.6f} {-p[1]:.6f}\n")
            for uv in sub.uvs:
                f.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")
            for n in sub.normals:
                f.write(f"vn {n[0]:.6f} {n[2]:.6f} {-n[1]:.6f}\n")
            idx = sub.indices
            for i in range(0, len(idx), 3):
                a = idx[i] + vbase
                b = idx[i + 1] + vbase
                c = idx[i + 2] + vbase
                f.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")
            vbase += len(sub.positions)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dump_obj = False
    if "--dump-obj" in argv:
        dump_obj = True
        argv.remove("--dump-obj")
    if not argv:
        print("Usage: python -m trainzmesh_viewer [--dump-obj] <file.trainzmesh>")
        print("       or drag a .trainzmesh onto run.command / run.bat")
        return 1
    path = argv[0]
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return 1
    if dump_obj:
        mesh = parse_trainzmesh(path)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        export_dir = os.path.join(root, "exports")
        os.makedirs(export_dir, exist_ok=True)
        out = os.path.join(export_dir, os.path.splitext(os.path.basename(path))[0] + ".obj")
        _write_obj(mesh, out)
        print(f"Wrote {out}")
        return 0
    try:
        run_viewer(path)
    except Exception as exc:
        print(f"Error: {exc}")
        raise
    return 0
