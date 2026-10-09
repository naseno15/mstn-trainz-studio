"""Assert-based self-check for trainz_studio loaders (no GUI)."""
from __future__ import annotations

import sys
import struct
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent  # trs22/
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np

from trainz_studio.io.anim import peek_kin, scan_kin_files
from trainz_studio.io.loaders import TRAINZMESH_MAGIC, load_any, load_fbx, parse_obj
from trainz_studio.io.scene import Attachment
from trainz_studio.io.texture import check_texture_txt, image_size, material_family, scan_folder, texture_stem
from trainz_studio.render.view3d import (
    aabb_wire_lines,
    attachment_gizmo_lines,
    fly_approach_dist,
    sun_dir_yup,
)

FIXTURES = HERE / "fixtures"


def test_fps_hud_text() -> None:
    """F3 HUD text formatter (QLabel body — no GL painter path)."""
    from trainz_studio.render.view3d import format_fps_hud_text

    assert format_fps_hud_text([], [], 0) == ""
    text = format_fps_hud_text([16.7], [16.7], 42)
    assert "fps" in text and "ms" in text and "#42" in text
    assert "\n" in text
    assert "idle" not in text
    idle = format_fps_hud_text([16.7], [16.7], 42, idle=True)
    assert "#42  idle" in idle


def test_fps_hud_top_right() -> None:
    """F3 chip sits on the clear viewport's top-right and dodges the Editor dock."""
    from trainz_studio.render.view3d import fps_hud_top_right

    x, y = fps_hud_top_right(1000, 200, margin=12, top=10)
    assert (x, y) == (788, 10)
    x2, y2 = fps_hud_top_right(1000, 200, margin=12, dock_left=700, top=10)
    assert (x2, y2) == (488, 10)
    x3, _y3 = fps_hud_top_right(
        1000, 200, margin=12, dock_left=180, left_min=160, top=10
    )
    assert x3 == 160


def test_mesh_key_hidden() -> None:
    """Scene table Show-off hides batches by mesh_key (empty key always draws)."""
    from trainz_studio.render.view3d import is_mesh_key_hidden

    hidden = {"cab.fbx", "int.im"}
    assert is_mesh_key_hidden("cab.fbx", hidden)
    assert not is_mesh_key_hidden("body.fbx", hidden)
    assert not is_mesh_key_hidden("", hidden)
    assert not is_mesh_key_hidden("cab.fbx", set())


def test_attachment_owner_and_hidden() -> None:
    """Multi-mesh a.* prefix maps to mesh_key; Atts-off hides that mesh's gizmos."""
    from trainz_studio.render.view3d import (
        attachment_owner_mesh_key,
        is_attachment_hidden,
    )

    keys = ["body.trainzmesh", "cab.fbx"]
    assert attachment_owner_mesh_key("body/a.bogie", keys) == "body.trainzmesh"
    assert attachment_owner_mesh_key("cab/a.lamp", keys) == "cab.fbx"
    assert attachment_owner_mesh_key("a.point", ["solo.im"]) == "solo.im"
    assert attachment_owner_mesh_key("a.point", keys) == ""
    hidden = {"cab.fbx"}
    assert is_attachment_hidden("cab/a.lamp", hidden, keys)
    assert not is_attachment_hidden("body/a.bogie", hidden, keys)
    assert not is_attachment_hidden("cab/a.lamp", set(), keys)


def test_highlight_pick() -> None:
    """Mesh row, mesh file, and Mat stem share one outline match."""
    from trainz_studio.render.view3d import highlight_pick

    door = dict(
        name="door.m.pbrmetal",
        mesh_key="body.trainzmesh",
        ref_stems={"door", "door_albedo"},
    )
    cab = dict(name="cab.m.onetex", mesh_key="cab.fbx", ref_stems={"cab"})
    assert highlight_pick(**door, names={"door.m.pbrmetal"}, stems=set(), mesh_keys=set())
    assert not highlight_pick(**cab, names={"door.m.pbrmetal"}, stems=set(), mesh_keys=set())
    assert highlight_pick(**cab, names=set(), stems=set(), mesh_keys={"cab.fbx"})
    assert not highlight_pick(**door, names=set(), stems=set(), mesh_keys={"cab.fbx"})
    assert highlight_pick(**door, names=set(), stems={"door_albedo"}, mesh_keys=set())
    assert not highlight_pick(
        name="", mesh_key="", ref_stems=set(), names=set(), stems=set(), mesh_keys=set()
    )


def test_face_orient_rgb() -> None:
    """Blender Face Orientation colors (blue front / red back)."""
    from trainz_studio.render.view3d import (
        FACE_ORIENT_BACK_RGB,
        FACE_ORIENT_FRONT_RGB,
        face_orient_rgb,
    )

    assert face_orient_rgb(True) == FACE_ORIENT_FRONT_RGB
    assert face_orient_rgb(False) == FACE_ORIENT_BACK_RGB
    assert FACE_ORIENT_FRONT_RGB[2] > FACE_ORIENT_FRONT_RGB[0]  # blue-ish
    assert FACE_ORIENT_BACK_RGB[0] > FACE_ORIENT_BACK_RGB[2]  # red-ish


def test_mesh_preview_argv() -> None:
    """--preview / --explorer-preview argv parser (no GUI)."""
    from trainz_studio.ui.mesh_preview import MESH_EXTS, parse_preview_argv, wants_preview

    assert ".trainzmesh" in MESH_EXTS and ".fbx" in MESH_EXTS and ".im" in MESH_EXTS
    assert wants_preview(["x", "--preview", "a.trainzmesh"])
    assert wants_preview(["x", "--explorer-preview", "a.fbx"])
    assert not wants_preview(["x", "a.trainzmesh"])
    fixture = FIXTURES / "body.trainzmesh"
    if not fixture.is_file():
        return
    opts = parse_preview_argv(["prog", "--preview", str(fixture)])
    assert opts["mode"] == "preview" and opts["path"] == fixture
    opts2 = parse_preview_argv(
        [
            "prog",
            "--explorer-preview",
            "--parent-hwnd",
            "0x100",
            "--rect",
            "0,0,320,240",
            str(fixture),
        ]
    )
    assert opts2["mode"] == "explorer"
    assert opts2["parent_hwnd"] == 0x100
    assert opts2["rect"] == (0, 0, 320, 240)
    try:
        parse_preview_argv(["prog", "--preview", str(FIXTURES / "nope.trainzmesh")])
        raise AssertionError("expected missing file")
    except ValueError:
        pass


def test_draw_batch_vbo_slots() -> None:
    """Indexed GPU buffers on DrawBatch (full Lit; shared verts + IBO)."""
    from trainz_studio.render.view3d import DrawBatch

    b = DrawBatch(
        verts=np.zeros((3, 8), dtype=np.float32),
        indices=np.array([0, 1, 2], dtype=np.uint32),
        color=(1.0, 1.0, 1.0),
        albedo=None,
        normal=None,
        parameter=None,
        name="t",
        albedo_ref="",
        normal_ref="",
        parameter_ref="",
        material_type="",
    )
    assert b.vbo is None and b.ibo is None and b.vcount == 0 and b.icount == 0
    assert b.indices.dtype == np.uint32 and b.indices.shape[0] == 3


def test_flatten_part_indexed() -> None:
    """Preview batches stay indexed (same look, less GPU vertex traffic)."""
    from trainz_studio.io.scene import MeshPart
    from trainz_studio.render.view3d import _flatten_part

    part = MeshPart(
        name="t",
        vertices=np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32
        ),
        indices=np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32),
        normals=np.array(
            [[0, 0, 1], [0, 0, 1], [0, 0, 1], [1, 0, 0]], dtype=np.float32
        ),
        uvs=np.zeros((4, 2), dtype=np.float32),
    )
    batch = _flatten_part(part, tri_budget=100)
    assert batch is not None
    assert batch.verts.shape == (4, 8)
    assert batch.indices.shape == (6,)
    # no texture paths → presence flags stay False (paintGL must not Path.is_file)
    assert batch.has_albedo is False and batch.has_normal is False and batch.has_parameter is False
    assert int(batch.indices[5]) == 3


def test_tiled_uv_chunk_is_kept() -> None:
    """UV repeat past ±32 must not drop the submesh (that shifted every later part)."""
    import struct

    from trainz_studio.lib.trainzmesh_viewer.parser import VertexFormat, _sample_ok

    stride = 32
    count = 4
    buf = bytearray(count * stride)
    for i in range(count):
        struct.pack_into("<3f", buf, i * stride, float(i), 0.0, 1.0)
        struct.pack_into("<3f", buf, i * stride + 12, 0.0, 0.0, 1.0)
        struct.pack_into("<2f", buf, i * stride + 24, 0.0, 48.0)
    fmt = VertexFormat(
        raw="S0_P3fN3fT02f",
        stride=stride,
        position_offset=0,
        normal_offset=12,
        uv_offset=24,
    )
    assert _sample_ok(bytes(buf), 0, count, stride, fmt)


def test_trainzmesh_decode() -> None:
    p = FIXTURES / "body.trainzmesh"
    assert p.is_file(), p
    assert p.read_bytes()[:4] == TRAINZMESH_MAGIC
    sc = load_any(p)
    assert sc.kind == "trainzmesh"
    assert sc.vertex_count > 1000, sc.vertex_count
    assert sc.face_count > 1000, sc.face_count
    assert any(p.uvs is not None and p.uvs.size for p in sc.parts)
    assert any(p.albedo_ref for p in sc.parts)
    # PBR maps when parser finds them on this fixture
    assert any(part.normal_ref or part.parameter_ref for part in sc.parts), (
        "body.trainzmesh should expose normal_ref and/or parameter_ref"
    )
    assert len(sc.attachments) > 0, "fixture should expose a.* from tzMF table"
    # Material block follows its chunk (gap 0). Index pairing put body_front
    # on the unnamed 848-vert piece and shifted every later part.
    counts = {part.name: int(part.vertices.shape[0]) for part in sc.parts}
    assert counts["rubber.m.pbrmetal"] == 4631
    assert counts["body_front.m.pbrmetal"] == 14760
    assert counts["body.m.pbrmetal"] == 7150
    unnamed = [part for part in sc.parts if str(part.name).startswith("mesh_")]
    assert len(unnamed) == 1 and int(unnamed[0].vertices.shape[0]) == 848


def test_obj_parse_with_uv() -> None:
    obj = """o box
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
f 1/1 2/2 3/3
f 1/1 3/3 4/4
"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "t.obj"
        path.write_text(obj)
        parts = parse_obj(path)
    assert len(parts) == 1
    assert parts[0].vertices.shape[0] >= 3
    assert parts[0].indices.shape[0] == 6
    assert parts[0].uvs is not None
    assert parts[0].uvs.shape[0] == parts[0].vertices.shape[0]


def test_obj_parse_roundtrip() -> None:
    obj = """o box
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3
f 1 3 4
"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "t.obj"
        path.write_text(obj)
        parts = parse_obj(path)
    assert len(parts) == 1
    assert parts[0].vertices.shape[0] == 4
    assert parts[0].indices.shape[0] == 6


def test_texture_stem() -> None:
    assert texture_stem("body_albedo.texture.txt") == "body_albedo"
    assert texture_stem("body_albedo.texture") == "body_albedo"
    assert texture_stem("foo.TGA") == "foo"
    assert texture_stem("bar.png") == "bar"
    assert texture_stem(Path("x/y/z.parameter.texture.txt")) == "z.parameter"
    # matching helper used by view filter
    assert texture_stem("Cab.texture.txt") == texture_stem("cab.tga")


def test_material_family() -> None:
    assert material_family("body_side_albedo") == ("body_side", "albedo")
    assert material_family("body_side_normal.texture.txt") == ("body_side", "normal")
    assert material_family("window-parameter") == ("window", "parameter")
    assert material_family("Cab.texture.txt") == ("cab", None)


def test_probe_image_and_pbr_sort() -> None:
    """Finder-style probe + PBR set ordering for Assets Texture table."""
    from PIL import Image

    from trainz_studio.io.texture import pbr_set_label, probe_image, sort_texture_paths

    assert pbr_set_label({None}) == "plain"
    assert pbr_set_label({"albedo", "normal"}) == "need parameter"
    assert pbr_set_label({"albedo", "normal", "parameter"}) == "PBR ✓"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        a = root / "body_albedo.png"
        n = root / "body_normal.png"
        p = root / "body_parameter.png"
        z = root / "solo.png"
        Image.new("RGBA", (32, 16), (10, 20, 30, 255)).save(a)
        Image.new("RGB", (32, 16), (0, 128, 255)).save(n)
        Image.new("L", (32, 16), 90).save(p)
        Image.new("RGB", (8, 8), (1, 2, 3)).save(z)

        pa = probe_image(a)
        assert pa.width == 32 and pa.height == 16
        assert pa.mode == "RGBA" and pa.channels == 4
        assert pa.file_bytes > 0 and not pa.error
        assert "RGBA" in pa.channel_label

        pn = probe_image(n)
        assert pn.mode == "RGB" and pn.channels == 3

        rows = sort_texture_paths([z, p, a, n])
        names = [r[0].name for r in rows]
        assert names[:3] == ["body_albedo.png", "body_normal.png", "body_parameter.png"]
        assert rows[0][3] == "PBR ✓"
        assert rows[-1][0].name == "solo.png"
        assert rows[-1][3] == "plain"


def test_stems_match_family() -> None:
    from trainz_studio.io.texture import stems_match

    # exact
    assert stems_match({"body_albedo"}, {"body_albedo"})
    # family: list row body_albedo ↔ mesh ref "body"
    assert stems_match({"body"}, {"body_albedo"})
    assert stems_match({"body_normal", "body_parameter"}, {"body_albedo"})
    assert not stems_match({"roof"}, {"body_albedo"})
    assert not stems_match(set(), {"body"})
    assert not stems_match({"body"}, set())


def test_i18n_catalogs_and_fonts() -> None:
    """Lang catalogs + bundled Noto families (no MainWindow)."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.i18n import (
        LANG_ORDER,
        apply_language_font,
        ensure_ui_fonts,
        family_for,
        g,
        set_language,
        t,
    )
    from trainz_studio.ui.i18n import catalog_en, catalog_id, catalog_ja, catalog_th

    app = QApplication.instance() or QApplication([])
    del app
    assert set(LANG_ORDER) == {"en", "th", "ja", "id"}
    keys = set(catalog_en.STRINGS)
    assert keys == set(catalog_th.STRINGS) == set(catalog_ja.STRINGS) == set(catalog_id.STRINGS)
    assert "Lang" in keys and "File" in keys
    for gid in catalog_en.GLOSSARY:
        assert gid in catalog_th.GLOSSARY
        assert gid in catalog_ja.GLOSSARY
        assert gid in catalog_id.GLOSSARY
    from PySide6.QtGui import QFont, QFontInfo

    from trainz_studio.ui.i18n import ui_font

    ensure_ui_fonts()
    assert family_for("en") == "Noto Sans"
    assert "Thai Looped" in family_for("th")
    assert "CJK" in family_for("ja") or "JP" in family_for("ja")
    en_font = ui_font("en", 13)
    assert en_font.families()[:1] == ["Noto Sans"]
    assert "Noto Sans CJK JP" in en_font.families()
    assert "Noto Sans Thai Looped" in en_font.families()
    en = QFontInfo(en_font)
    assert en.family() == "Noto Sans" and en.weight() == 400
    assert "Thin" not in en.styleName() and "Condensed" not in en.styleName()
    en_bold = QFontInfo(ui_font("en", 13, QFont.Weight.Bold))
    assert en_bold.family() == "Noto Sans" and en_bold.weight() == 700
    assert "Thai Looped" in QFontInfo(ui_font("th", 13)).family()
    set_language("en", persist=False)
    assert t("File") == "File"
    set_language("th", persist=False)
    assert t("File") != "File"
    assert "VE39" in g("ve39.name") or "ve39" in g("ve39.name").lower()
    tip = g("ve39.tip")
    assert len(tip) > 20
    assert "VE37" in g("rules.tip") or "power" in g("rules.tip").lower()
    set_language("ja", persist=False)
    assert t("File") != "File"
    set_language("id", persist=False)
    assert t("Lang")  # Bahasa / etc.
    apply_language_font("id")
    from trainz_studio.ui.theme import font_stack, stylesheet, palette as theme_palette

    assert "Noto Sans" in font_stack("id")
    assert "CJK" in font_stack("th")
    assert "CJK" in font_stack("ja") or "JP" in font_stack("ja")
    sheet = stylesheet(theme_palette("dark"))
    assert "font-family:" in sheet and "Noto" in sheet
    set_language("en", persist=False)


def test_ve_rules_pack() -> None:
    """Multi-VE texture/config rules scan + safe fixes (no GUI)."""
    from PIL import Image

    from trainz_studio.io.ve_rules import (
        catalog_image,
        fix_finding,
        scan_asset_folder,
        scan_config,
        scan_image,
        scan_lm_txt,
        scan_sound,
        scan_texture_folder,
        summarize_reports,
    )
    from trainz_studio.io.lm import write_lm_txt, LmFile, LmMesh

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # VE37 + VE39
        solid = root / "body_albedo.png"
        Image.new("RGB", (100, 50), (10, 20, 30)).save(solid)
        r = scan_image(solid)
        codes = set(r.codes)
        assert 37 in codes and 39 in codes, codes
        assert r.status.startswith("VE")
        # VE65 orphan
        folder_reports = scan_texture_folder(root)
        assert any(65 in fr.codes for fr in folder_reports), folder_reports
        # fix PoT + VE39 + texture.txt
        for f in r.findings:
            if f.fixable:
                ok, msg = fix_finding(f, bak=True)
                assert ok, (f, msg)
        # after pot+ve39, re-scan — 65 still until texture_txt fix
        cat = catalog_image(solid)
        assert "path" in cat and cat["dims"]
        # config rules
        cfg = root / "config.txt"
        cfg.write_text(
            'kind "traincar"\n'
            "trainz-build 2.4\n"
            'light 1\n'
            'mesh-table\n{\n  default\n  {\n    mesh "missing.im"\n  }\n}\n',
            encoding="utf-8",
        )
        cr = scan_config(cfg)
        assert 48 in cr.codes and 44 in cr.codes and 30 in cr.codes, cr.codes
        # lm.txt
        lm_path = root / "body.lm.txt"
        write_lm_txt(
            lm_path,
            LmFile(meshes=[LmMesh(width=1.0, name="ghost.im")]),
        )
        lr = scan_lm_txt(lm_path)
        assert 30 in lr.codes or 84 in lr.codes or 161 in lr.codes, lr.codes
        folder_all = scan_asset_folder(root)
        assert folder_all
        summ = summarize_reports(folder_all)
        assert "line" in summ and summ["hits"] >= 1
        # VE102 wav
        wav = root / "beep.wav"
        wav.write_bytes(b"not-a-wav")
        assert 102 in scan_sound(wav).codes


def test_param_map_and_bake_denoise() -> None:
    """Parameter channel ops + bake denoise engine (OpenCV path, no Save)."""
    from PIL import Image

    from trainz_studio.io.bake_denoise import (
        DenoiseSettings,
        compose_with_alpha,
        denoise_image,
        oidn_available,
    )
    from trainz_studio.io.param_map_edit import (
        apply_fill,
        apply_offset,
        apply_scale,
        channel_stats,
        paint_dab,
        save_parameter,
    )
    from trainz_studio import PKG_ROOT

    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[..., 0] = 10
    rgba[..., 1] = 80
    rgba[..., 2] = 200
    rgba[..., 3] = 0
    filled = apply_fill(rgba, {"A"}, 255)
    assert int(filled[0, 0, 3]) == 255 and int(filled[0, 0, 1]) == 80
    off = apply_offset(filled, {"G"}, 20)
    assert int(off[0, 0, 1]) == 100
    scaled = apply_scale(off, {"B"}, 0.5)
    assert int(scaled[0, 0, 2]) == 100
    paint_dab(scaled, {"R"}, 8, 8, 3, 200, hardness=1.0, opacity=1.0)
    assert int(scaled[8, 8, 0]) == 200
    st = channel_stats(scaled)
    assert st["G"][2] == 100.0

    # speckled gray bake → OpenCV denoise keeps shape; OIDN optional
    noise = np.random.default_rng(0).integers(40, 220, (32, 32), dtype=np.uint8)
    bgr = np.dstack([noise, noise, noise])
    out, engine = denoise_image(
        bgr,
        DenoiseSettings(strength="light", prefer_oidn=False, preserve_black=False),
    )
    assert out.shape[:2] == bgr.shape[:2]
    assert engine.startswith("opencv")
    assert oidn_available() == (PKG_ROOT / "vendor" / "oidn" / "bin" / "oidnDenoise.exe").is_file()
    rgba_prev = compose_with_alpha(out, None)
    assert rgba_prev.shape[2] == 4 and int(rgba_prev[0, 0, 3]) == 255

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "param.png"
        Image.fromarray(scaled, mode="RGBA").save(src)
        save_parameter(src, scaled, bak=True)
        assert src.with_suffix(".png.bak").is_file()


def test_tex_map_edit_channels_and_bak() -> None:
    """Maps viewer: channel mute + Trainz sibling .bak on first save."""
    from PIL import Image

    from trainz_studio.io.tex_map_edit import (
        TexMapSession,
        denoise_rgba,
        invert_channels,
        view_channels,
    )
    from trainz_studio.ui.assets.tex_map_panel import family_role_paths

    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[..., 0] = 200
    rgba[..., 1] = 100
    rgba[..., 2] = 50
    rgba[..., 3] = 255
    solo_r = view_channels(rgba, r=True, g=False, b=False, a=True)
    assert int(solo_r[0, 0, 0]) == 200 and int(solo_r[0, 0, 1]) == 200
    muted = view_channels(rgba, r=True, g=False, b=True, a=False)
    assert int(muted[0, 0, 1]) == 0 and int(muted[0, 0, 3]) == 255
    inv = invert_channels(rgba, (True, False, False, False))
    assert int(inv[0, 0, 0]) == 55 and int(inv[0, 0, 1]) == 100
    # speckled → denoise must run and keep alpha
    speck = rgba.copy()
    speck[0, 0, 0] = 0
    dn = denoise_rgba(speck, strength=50, role="albedo")
    assert dn.shape == speck.shape and int(dn[1, 1, 3]) == 255
    flat_n = np.full((8, 8, 4), (128, 128, 255, 255), dtype=np.uint8)
    dn_n = denoise_rgba(flat_n, strength=40, role="normal")
    n = dn_n[..., :3].astype(np.float32) / 255.0 * 2.0 - 1.0
    assert float(np.sqrt(np.sum(n**2, axis=-1)).mean()) > 0.95

    paths = [
        Path("body_albedo.tga"),
        Path("body_normal.tga"),
        Path("body_parameter.tga"),
        Path("other_albedo.tga"),
    ]
    maps = family_role_paths(paths, "body")
    assert set(maps) == {"albedo", "normal", "parameter"}

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "body_normal.png"
        Image.fromarray(rgba, mode="RGBA").save(src)
        sess = TexMapSession.open(src, role="normal")
        sess.apply(invert_channels(sess.pixels, (False, True, False, False)))
        sess.save(bak=True)
        bak = src.with_suffix(src.suffix + ".bak")
        assert bak.is_file() and src.is_file()
        # second save must not clobber .bak
        first_bak = bak.read_bytes()
        sess.apply(invert_channels(sess.pixels, (True, False, False, False)))
        sess.save(bak=True)
        assert bak.read_bytes() == first_bak


def test_image_prep_and_ve39() -> None:
    """Resize → _prep + VE39 uniform noise fix (no GUI)."""
    from PIL import Image

    from trainz_studio.io.image_prep import (
        calculate_target_size,
        detect_map_mode,
        process_image,
        resize_normal_map,
    )
    from trainz_studio.io.ve39 import fix_ve39, is_uniform_color

    assert calculate_target_size(1000, 500, "max", max_dim=512) == (512, 256)
    assert calculate_target_size(300, 300, "pot", pot_down=True) == (256, 256)
    assert calculate_target_size(800, 600, "percentage", percent=50.0) == (400, 300)
    assert calculate_target_size(10, 20, "exact", target_w=64, target_h=32) == (64, 32)
    assert detect_map_mode("body_normal.png") == "normal"
    assert detect_map_mode("roof_parameter.tga") == "parameter"

    # normal re-normalize: flat (0,0,1) packed stays unit-ish after resize
    flat = Image.fromarray(
        np.full((32, 32, 3), (128, 128, 255), dtype=np.uint8), mode="RGB"
    )
    out_n = resize_normal_map(flat, (16, 16), Image.Resampling.BILINEAR)
    arr = np.asarray(out_n, dtype=np.float32)
    n = arr / 255.0 * 2.0 - 1.0
    lengths = np.sqrt(np.sum(n**2, axis=-1))
    assert float(lengths.mean()) > 0.95

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        solid = root / "solid_albedo.png"
        Image.new("RGB", (64, 64), (40, 80, 120)).save(solid)
        ok, dest, msg = process_image(solid, resize_mode="max", max_dim=32)
        assert ok and dest == root / "_prep" / "solid_albedo.png", (ok, dest, msg)
        with Image.open(dest) as im:
            assert im.size == (32, 32)

        with Image.open(solid) as im:
            assert is_uniform_color(im)[0] is True
        fixed, fmsg = fix_ve39(solid, bak=True)
        assert fixed and "fixed" in fmsg, fmsg
        assert solid.with_suffix(".png.bak").is_file()
        with Image.open(solid) as im:
            assert is_uniform_color(im)[0] is False
        skip, smsg = fix_ve39(solid, bak=True)
        assert not skip and "not uniform" in smsg


def test_merge_lamp_packs() -> None:
    from trainz_studio.lamps import Lamp, merge_lamp_packs, pack_for_gpu

    a = pack_for_gpu(
        [Lamp(stem="a", enabled=True, brightness=0.5, pos=(0, 1, 0), range_m=1.0)]
    )
    b = pack_for_gpu(
        [Lamp(stem="b", enabled=True, brightness=0.8, pos=(2, 1, 0), range_m=2.0)]
    )
    m = merge_lamp_packs(a, b)
    assert int(m["count"]) == 2
    assert float(m["pos"][1, 0]) == 2.0
    assert m["glow"]  # surface glow keys present for both stems
    assert any(k.endswith("a") or k == "a" for k in m["glow"])
    assert any(k.endswith("b") or k == "b" for k in m["glow"])


def test_resolve_primary() -> None:
    from trainz_studio.io.texture import resolve_primary_image

    r = check_texture_txt(FIXTURES / "sample_albedo.texture.txt")
    img = resolve_primary_image(r)
    assert img is not None
    assert img.name == "sample_albedo.png"


def test_fbx_bumper() -> None:
    p = FIXTURES / "bumper.fbx"
    assert p.is_file(), p
    sc = load_fbx(p)
    assert sc.kind == "fbx"
    assert sc.vertex_count > 1000
    assert sc.face_count > 1000
    assert len(sc.parts) >= 1
    b = sc.bounds()
    assert b is not None
    mins, maxs = b
    assert np.all(maxs > mins)


def test_attachment_axes() -> None:
    a = Attachment("a.test", (1.0, 2.0, 3.0))
    ex, ey, ez = a.axes_end(1.0)
    assert np.allclose(ex, (2, 2, 3))
    assert np.allclose(ey, (1, 3, 3))
    assert np.allclose(ez, (1, 2, 4))


def test_aabb_wire_lines() -> None:
    mins = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    maxs = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    lines = aabb_wire_lines(mins, maxs, color=(1.0, 0.5, 0.0))
    assert lines.shape == (24, 6)  # 12 edges × 2 endpoints
    assert lines.dtype == np.float32
    # first edge: (0,0,0) → (1,0,0)
    assert np.allclose(lines[0, :3], [0, 0, 0])
    assert np.allclose(lines[1, :3], [1, 0, 0])
    assert np.allclose(lines[0, 3:], [1.0, 0.5, 0.0])


def test_attachment_gizmo_glow() -> None:
    att = Attachment(name="a.bog1", pos=(1.0, 2.0, 3.0))
    plain = attachment_gizmo_lines(att, selected=False, dist=20.0)
    sel = attachment_gizmo_lines(att, selected=True, dist=20.0)
    assert plain.shape == (6, 6)  # 3 axes × 2 ends
    assert sel.shape == (6, 6)  # shafts only; cones/cube are solids
    assert sel.dtype == np.float32
    # selected axes are warmer on X
    assert float(sel[0, 3]) >= float(plain[0, 3])
    from trainz_studio.render.view3d import attachment_gizmo_solids

    assert attachment_gizmo_solids(att, selected=True, move_mode=False, dist=20.0).size == 0
    solids = attachment_gizmo_solids(att, selected=True, move_mode=True, dist=20.0)
    assert solids.ndim == 2 and solids.shape[1] == 6
    assert solids.shape[0] >= 36  # 3 cones + cube


def test_pick_attachment_index() -> None:
    from trainz_studio.render.view3d import (
        pick_attachment_index,
        project_world_to_screen,
        _look_at_mat,
        _perspective_mat,
    )

    eye = np.array([0.0, 0.0, 10.0], dtype=np.float64)
    target = np.zeros(3, dtype=np.float64)
    view = _look_at_mat(eye, target, np.array([0.0, 1.0, 0.0]))
    proj = _perspective_mat(45.0, 1.0, 0.1, 100.0)
    mvp = proj @ view
    atts = [
        Attachment("a.a", (0.0, 0.0, 0.0)),
        Attachment("a.b", (2.0, 0.0, 0.0)),
    ]
    hit0 = project_world_to_screen(mvp, atts[0].pos, 200, 200)
    assert hit0 is not None
    sx, sy, _z = hit0
    assert pick_attachment_index(atts, mvp, sx, sy, 200, 200, radius_px=8) == 0
    assert pick_attachment_index(atts, mvp, 0, 0, 200, 200, radius_px=2) == -1


def test_glow_billboard_mesh() -> None:
    from trainz_studio.render.view3d import glow_billboard_mesh

    centers = np.asarray([[0.0, 1.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float32)
    colors = np.asarray([[1.0, 0.5, 0.2], [0.2, 0.6, 1.0]], dtype=np.float32)
    radii = np.asarray([0.5, 1.0], dtype=np.float32)
    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    verts, idx = glow_billboard_mesh(centers, colors, radii, right, up)
    assert verts.shape == (8, 8)  # 2 quads × 4 corners
    assert idx.shape == (12,)  # 2 quads × 2 tris × 3
    assert np.allclose(verts[0, 3:6], [1.0, 0.5, 0.2])
    # first corner of first quad: center + (-r,-r) in right/up
    assert np.allclose(verts[0, 0:3], [-0.5, 0.5, 0.0], atol=1e-5)


def test_sun_dir_yup() -> None:
    # Viewport is Trainz Z-up (sun_dir_yup aliases sun_dir_zup)
    # el=90° → +Z; az=0 el=0 → +Y; az=90 el=0 → +X
    x, y, z = sun_dir_yup(0.0, 90.0)
    assert abs(z - 1.0) < 1e-6
    assert abs(x) < 1e-6 and abs(y) < 1e-6
    x0, y0, z0 = sun_dir_yup(0.0, 0.0)
    assert abs(x0) < 1e-6 and abs(y0 - 1.0) < 1e-6 and abs(z0) < 1e-6
    x90, y90, z90 = sun_dir_yup(90.0, 0.0)
    assert abs(x90 - 1.0) < 1e-6 and abs(y90) < 1e-6 and abs(z90) < 1e-6


def test_fly_approach_dist_stable() -> None:
    # hopping a.* must not shrink dolly (old cozy ×0.62 per nearby click)
    d = 4.5
    assert fly_approach_dist(d, approach=True) == d
    assert fly_approach_dist(d, approach=False) == d
    assert fly_approach_dist(1.2, approach=True) == 1.2
    assert fly_approach_dist(20.0, approach=True) == 20.0


def test_orbit_yaw_follows_drag() -> None:
    """LMB drag-right (+yaw) must move a +X landmark right on screen — not invert."""
    import math

    from trainz_studio.render.view3d import (
        WORLD_UP,
        _look_at_mat,
        _perspective_mat,
        project_world_to_screen,
    )

    def eye_at(yaw_deg: float, pitch_deg: float, dist: float = 10.0) -> np.ndarray:
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        return np.array(
            [
                dist * math.cos(pitch) * math.sin(yaw),
                dist * math.cos(pitch) * math.cos(yaw),
                dist * math.sin(pitch),
            ],
            dtype=np.float64,
        )

    def sx_of(yaw_deg: float) -> float:
        eye = eye_at(yaw_deg, 25.0)
        target = np.zeros(3, dtype=np.float64)
        mvp = _perspective_mat(45.0, 1.0, 0.05, 5000.0) @ _look_at_mat(
            eye, target, WORLD_UP
        )
        hit = project_world_to_screen(mvp, (1.0, 0.0, 0.0), 400, 400)
        assert hit is not None
        return float(hit[0])

    # Same sign as mouseMoveEvent: drag right → +yaw
    assert sx_of(40.0) > sx_of(35.0)


def test_arrow_walk_is_ground_forward() -> None:
    """Up/Down walk along camera look on XY. Left/Right stay horizontal strafe.

    Z is up. Flattening Y (the old bug) made Up slide in XZ instead of forward.
    """
    import math

    from trainz_studio.render.view3d import WORLD_UP, horizontal_walk_dirs

    yaw = math.radians(35.0)
    pitch = math.radians(25.0)
    look = -np.array(
        [
            math.cos(pitch) * math.sin(yaw),
            math.cos(pitch) * math.cos(yaw),
            math.sin(pitch),
        ],
        dtype=np.float64,
    )
    look_n = look / np.linalg.norm(look)
    right = np.cross(look_n, WORLD_UP)
    right = right / np.linalg.norm(right)
    forward, right_h = horizontal_walk_dirs(look, right)
    assert abs(forward[2]) < 1e-9 and abs(right_h[2]) < 1e-9
    assert abs(float(np.dot(forward, right_h))) < 1e-6
    # Default view looks mostly along −Y; Up must keep that, not collapse to X.
    assert forward[1] < -0.7
    assert abs(float(np.dot(forward[:2], look[:2] / np.linalg.norm(look[:2])))) > 0.99
    straight = horizontal_walk_dirs(np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 0.0]))
    assert abs(straight[0][2]) < 1e-9


def test_screen_delta_to_world() -> None:
    from trainz_studio.render.view3d import screen_delta_to_world

    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    d = screen_delta_to_world(10.0, 0.0, dist=100.0, right=right, up=up, fine=False)
    assert abs(d[0] - 10.0 * 100.0 * 0.0016) < 1e-9
    assert abs(d[1]) < 1e-12 and abs(d[2]) < 1e-12
    # screen-down (+dy) → world −up
    d2 = screen_delta_to_world(0.0, 10.0, dist=100.0, right=right, up=up, fine=False)
    assert abs(d2[1] + 10.0 * 100.0 * 0.0016) < 1e-9
    fine = screen_delta_to_world(10.0, 0.0, dist=100.0, right=right, up=up, fine=True)
    assert abs(fine[0] - d[0] * 0.1) < 1e-9


def test_screen_delta_along_axis() -> None:
    from trainz_studio.render.view3d import screen_delta_along_axis

    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    # drag right along +X axis → +X world
    d = screen_delta_along_axis(
        10.0, 0.0, np.array([1.0, 0.0, 0.0]), dist=100.0, right=right, up=up
    )
    assert abs(d[0] - 10.0 * 100.0 * 0.0016) < 1e-9
    assert abs(d[1]) < 1e-12 and abs(d[2]) < 1e-12
    # drag along Y axis with vertical mouse — screen-down maps to −Y on axis unit
    d2 = screen_delta_along_axis(
        0.0, 10.0, np.array([0.0, 1.0, 0.0]), dist=100.0, right=right, up=up
    )
    # sy of +Y axis = -1, so t = dy * sy = 10 * -1 = -10 → delta = +Y * (-10 * s)
    assert abs(d2[1] + 10.0 * 100.0 * 0.0016) < 1e-9


def test_pick_translate_handle() -> None:
    from trainz_studio.render.view3d import (
        pick_translate_handle,
        project_world_to_screen,
        _look_at_mat,
        _perspective_mat,
    )

    eye = np.array([0.0, 0.0, 10.0], dtype=np.float64)
    target = np.zeros(3, dtype=np.float64)
    view = _look_at_mat(eye, target, np.array([0.0, 1.0, 0.0]))
    proj = _perspective_mat(45.0, 1.0, 0.1, 100.0)
    mvp = proj @ view
    att = Attachment("a.p", (0.0, 0.0, 0.0))
    hit = project_world_to_screen(mvp, att.pos, 200, 200)
    assert hit is not None
    sx, sy, _z = hit
    assert pick_translate_handle(att, mvp, sx, sy, 200, 200, dist=10.0) == "free"
    # +X axis tip should pick "x"
    from trainz_studio.render.view3d import gizmo_axis_length

    tip = att.axes_end(gizmo_axis_length(10.0, selected=True, move_mode=True))[0]
    hit_x = project_world_to_screen(mvp, tip, 200, 200)
    assert hit_x is not None
    assert (
        pick_translate_handle(
            att, mvp, hit_x[0], hit_x[1], 200, 200, dist=10.0, free_radius_px=4.0
        )
        == "x"
    )
    assert pick_translate_handle(att, mvp, 0, 0, 200, 200, dist=10.0) is None


def test_attachment_gizmo_move_mode() -> None:
    from trainz_studio.render.view3d import attachment_gizmo_solids, gizmo_axis_length

    att = Attachment(name="a.bog1", pos=(0.0, 0.0, 0.0))
    plain = attachment_gizmo_lines(att, selected=True, move_mode=False, dist=20.0)
    move = attachment_gizmo_lines(att, selected=True, move_mode=True, dist=20.0)
    assert plain.shape == move.shape == (6, 6)
    # move-mode full axis (incl. tip) is longer than view shafts
    assert gizmo_axis_length(20.0, selected=True, move_mode=True) > gizmo_axis_length(
        20.0, selected=True, move_mode=False
    )
    solids = attachment_gizmo_solids(att, selected=True, move_mode=True, dist=20.0)
    assert solids.shape[0] > 0
    # tip of +X cone reaches near full axis length
    tip_x = float(gizmo_axis_length(20.0, selected=True, move_mode=True))
    assert float(np.max(solids[:, 0])) > tip_x * 0.85
    assert float(np.linalg.norm(move[1, :3])) > float(np.linalg.norm(plain[1, :3])) * 0.9


def test_env_presets() -> None:
    from trainz_studio.render.env import ENVIRONMENTS, env_keys, get_env

    assert "harbor" in env_keys()
    assert "station" in env_keys()
    e = get_env("lake")
    assert e.label == "Lake"
    assert len(e.sky_top) == 3
    assert "mountains" in ENVIRONMENTS


def test_hdri_assets() -> None:
    from trainz_studio.render.hdri import list_hdri_assets, load_hdri_rgba8

    assets = list_hdri_assets()
    assert len(assets) >= 8, len(assets)
    a = assets[0]
    assert a.path.is_file(), a.path
    # prefer real .hdr when twin jpg exists
    assert a.path.suffix.lower() == ".hdr" or not a.path.with_suffix(".hdr").is_file()
    w, h, px, meta = load_hdri_rgba8(a.path, max_w=256)
    assert w > 0 and h > 0
    assert len(px) == w * h * 4
    assert "exposure" in meta
    assert "sun_az" in meta and "sun_el" in meta
    assert -90.0 <= meta["sun_el"] <= 90.0


def test_hdri_sun_dir_roundtrip() -> None:
    from trainz_studio.render.hdri import dir_to_az_el, equirect_pixel_to_dir
    from trainz_studio.render.view3d import sun_dir_zup

    # zenith pixel mid-top → mostly +Y (equirect is Y-up)
    dx, dy, dz = equirect_pixel_to_dir(64, 0, 128, 64)
    assert dy > 0.9
    # sun_dir_zup → Y-up basis → dir_to_az_el (HDRI Y-up → Z-up az/el)
    for az, el in ((0.0, 45.0), (90.0, 10.0), (225.0, 60.0)):
        x, y, z = sun_dir_zup(az, el)
        az2, el2 = dir_to_az_el(x, z, -y)  # Z-up → Y-up components
        assert abs(az2 - az) < 1e-3 or abs(az2 - az + 360) < 1e-3 or abs(az2 - az - 360) < 1e-3
        assert abs(el2 - el) < 1e-3


def test_auto_exposure() -> None:
    import numpy as np
    from trainz_studio.render.hdri import auto_exposure

    black = np.zeros((8, 8, 3), dtype=np.float32)
    assert auto_exposure(black) == 1.0
    mid = np.full((8, 8, 3), 0.22, dtype=np.float32)
    exp = auto_exposure(mid, target=0.22)
    assert 0.9 <= exp <= 1.1
    bright = np.full((8, 8, 3), 4.0, dtype=np.float32)
    assert auto_exposure(bright) < 1.0


def test_fade_stack_no_opacity() -> None:
    """Stack page switch must not leave QGraphicsOpacityEffect (buries chrome)."""
    from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget

    from trainz_studio.ui.motion import fade_stack_to

    app = QApplication.instance() or QApplication([])
    stack = QStackedWidget()
    stack.addWidget(QLabel("a"))
    stack.addWidget(QLabel("b"))
    fade_stack_to(stack, 1)
    assert stack.currentIndex() == 1
    assert stack.graphicsEffect() is None
    del app


def test_boot_prewarms_gl_before_show() -> None:
    """First MeshView must be built before showMaximized (Win32 HWND flash)."""
    import inspect

    from trainz_studio.ui import boot
    from trainz_studio.ui.app import LoadingOverlay, MainWindow
    from trainz_studio.ui.title_chrome import begin_frameless_move

    src = inspect.getsource(boot.main)
    assert "prewarm_mesh_gl" in src
    assert src.index("prewarm_mesh_gl") < src.index("showMaximized")
    # Remaximize after frost hide — early HWND / drag must not leave restored.
    assert src.rindex("showMaximized") > src.index("_hide_overlay")
    assert hasattr(MainWindow, "prewarm_mesh_gl")
    assert hasattr(MainWindow, "_raise_overlay_chrome")
    assert callable(getattr(LoadingOverlay, "mousePressEvent", None))
    assert callable(begin_frameless_move)
    assert begin_frameless_move(None) is False
    assert "preload_progress" in src
    assert "overlay.log" in src
    warm = inspect.getsource(MainWindow.warmup_hub_studios)
    assert "_expose_hub_page" not in warm
    assert "_ensure_sounds_host" not in warm
    assert "_ensure_trainzutil_host" not in warm
    assert "_finish_build_cover" in inspect.getsource(MainWindow._ensure_sounds_host)


def test_boot_overlay_log_and_easing_bar() -> None:
    """Boot card names the call, and the bar target is ahead of the eased fill."""
    from PySide6.QtWidgets import QApplication, QWidget

    from trainz_studio.ui.app import LoadingOverlay
    from trainz_studio.util.preload import _HUB_MODULES, preload_progress

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    overlay = LoadingOverlay(host)
    overlay.log("import trainz_studio.ui.engine")
    overlay.set_stage("Calling build_sounds_studio", 62)
    text = overlay.log_text()
    assert "import trainz_studio.ui.engine" in text
    assert "Calling build_sounds_studio" in text
    from trainz_studio.util.preload import boot_log, set_boot_logger

    lines: list[str] = []
    set_boot_logger(lines.append)
    boot_log("Mesh · EditorWorkspace")
    assert any("EditorWorkspace" in line and "s  " in line for line in lines)
    set_boot_logger(None)
    assert overlay.bar.value() == 62
    assert overlay.bar.shown() < 62
    from PySide6.QtWidgets import QSizePolicy

    assert overlay._card.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
    assert overlay.log_view.maximumHeight() <= 92
    _name, _done, total = preload_progress()
    assert total == len(_HUB_MODULES)
    host.deleteLater()
    del app


def test_hub_reveal_overlay_plays() -> None:
    """Hub reveal covers with a pixmap and finishes without stacking opacity on parent."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication, QWidget

    from trainz_studio.ui.motion import HUB_DIR_LEFT, HubRevealOverlay

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(320, 200)
    host.show()
    ov = HubRevealOverlay(host)
    pm = QPixmap(320, 200)
    pm.fill(QColor("#223344"))
    done = {"ok": False}
    loop = QEventLoop()

    def _done() -> None:
        done["ok"] = True
        loop.quit()

    ov.setGeometry(host.rect())
    ov.play(pm, direction=HUB_DIR_LEFT, label="Mesh Studio", ms=50, on_done=_done)
    assert ov.isVisible()
    QTimer.singleShot(800, loop.quit)  # safety
    loop.exec()
    assert done["ok"]
    assert not ov.isVisible()
    assert host.graphicsEffect() is None
    host.close()
    del app


def test_damped_scroll_passes_when_table_cant_scroll() -> None:
    """Empty/short side tables must not eat wheel (outer sidebar scroll needs it)."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QListWidget

    from trainz_studio.ui.app import _DampedScrollFilter

    app = QApplication.instance() or QApplication([])
    view = QListWidget()
    view.resize(200, 120)
    filt = _DampedScrollFilter(view)
    wheel = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    # no items → bar max==min → filter must not consume
    assert filt.eventFilter(view.viewport(), wheel) is False
    view.removeEventFilter(filt)
    view.viewport().removeEventFilter(filt)
    view.deleteLater()
    app.processEvents()


def test_celestial_sphere_mesh() -> None:
    from trainz_studio.render.view3d import sun_corona_shell, uv_sphere_colored

    sun = uv_sphere_colored((0, 0, 0), 1.0, kind="sun", segments=8, rings=6)
    assert sun.ndim == 2 and sun.shape[1] == 6
    assert sun.shape[0] >= 8 * 6 * 6
    moon = uv_sphere_colored((1, 2, 3), 2.0, kind="moon", segments=10, rings=6)
    assert moon.shape[1] == 6
    # moon verts offset from center
    assert float(moon[:, 0].mean()) > 0.5
    glow = sun_corona_shell((0, 0, 0), 1.0, intensity=1.0)
    assert glow.shape[0] > 0


def test_island_light_positions() -> None:
    """Disconnected bulbs → one cast each; long connected tube → one center."""
    from trainz_studio.lamps import discover_lamps, island_light_positions
    from trainz_studio.io.scene import MeshPart, Scene

    # two separate triangles far apart, same part / same onetex
    v = np.array(
        [
            [0, 1, 0],
            [0.2, 1, 0],
            [0, 1, 0.2],
            [3, 1, 0],
            [3.2, 1, 0],
            [3, 1, 0.2],
        ],
        dtype=np.float32,
    )
    idx = np.array([0, 1, 2, 3, 4, 5], dtype=np.uint32)
    part = MeshPart(
        name="lights",
        vertices=v,
        indices=idx,
        albedo_ref="cabin_bulb",
        material_type="m.onetex",
    )
    anchors = island_light_positions(part)
    assert len(anchors) == 2, anchors
    xs = sorted(a[0] for a in anchors)
    assert xs[0] < 1.0 and xs[1] > 2.0, xs
    lamps = discover_lamps(Scene(source="t", kind="x", parts=[part]))
    assert len(lamps) == 2
    assert abs(lamps[0].pos[0] - lamps[1].pos[0]) > 1.0

    # long connected strip must stay ONE point (no axis split every ~0.55 m)
    xs = np.linspace(0.0, 4.0, 9)
    strip_v = []
    strip_i = []
    for i, x in enumerate(xs):
        strip_v.extend([[x, 1.0, 0.0], [x, 1.0, 0.15]])
    for i in range(len(xs) - 1):
        a = i * 2
        strip_i.extend([a, a + 1, a + 2, a + 1, a + 3, a + 2])
    tube = MeshPart(
        name="tube",
        vertices=np.asarray(strip_v, dtype=np.float32),
        indices=np.asarray(strip_i, dtype=np.uint32),
        albedo_ref="lightkuay",
        material_type="m.onetex",
    )
    one = island_light_positions(tube)
    assert len(one) == 1, one
    assert abs(one[0][0] - 2.0) < 0.35, one
    # under the strip (Y min was 1.0)
    assert one[0][1] < 1.0, one
    assert abs(one[0][1] - (1.0 - 0.03)) < 1e-3, one


def test_multi_mesh_keys() -> None:
    from trainz_studio.lamps import discover_lamps, glow_key, pack_for_gpu
    from trainz_studio.io.scene import MeshPart, Scene

    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    idx = np.array([0, 1, 2], dtype=np.uint32)
    a = MeshPart(
        name="bulb_a",
        vertices=v,
        indices=idx,
        albedo_ref="cabin_light",
        material_type="m.onetex",
        mesh_key="body.fbx",
    )
    b = MeshPart(
        name="bulb_b",
        vertices=v + 2.0,
        indices=idx,
        albedo_ref="cabin_light",
        material_type="m.onetex",
        mesh_key="cab.fbx",
    )
    # two bulbs same texture on same mesh → two cast points
    c = MeshPart(
        name="bulb_c",
        vertices=v + 4.0,
        indices=idx,
        albedo_ref="cabin_light",
        material_type="m.onetex",
        mesh_key="body.fbx",
    )
    sc = Scene(source="x", kind="multi", parts=[a, b, c])
    lamps = discover_lamps(sc)
    assert len(lamps) == 3, len(lamps)
    assert len({L.part_id for L in lamps}) == 3
    for L in lamps:
        L.enabled = True
    packed = pack_for_gpu(lamps)
    assert packed["count"] == 3
    # surface glow still one key per mesh+stem
    glow = packed["glow"]
    assert glow_key("body.fbx", "cabin_light") in glow
    assert glow_key("cab.fbx", "cabin_light") in glow
    # cast positions must differ (not one average)
    p0 = tuple(packed["pos"][0])
    p1 = tuple(packed["pos"][1])
    p2 = tuple(packed["pos"][2])
    assert len({p0, p1, p2}) == 3


def test_zup_vectorized() -> None:
    from trainz_studio.io.loaders import _zup_to_yup

    a = np.array([[1.0, 2.0, 3.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    b = _zup_to_yup(a)
    assert b.shape == (2, 3)
    np.testing.assert_allclose(b[0], [1.0, 3.0, -2.0])


def test_lerp_pill_rect() -> None:
    """Nav scrub pill tracks x between adjacent button rects."""
    from PySide6.QtCore import QRect

    from trainz_studio.ui.motion import (
        PILL_SLIDE_MS,
        SCRUB_LERP,
        lerp_pill_rects,
        nearest_index_at_x,
    )

    assert PILL_SLIDE_MS >= 380
    assert 0.05 < SCRUB_LERP < 0.3
    assert lerp_pill_rects([], 0).isNull()
    one = [QRect(10, 0, 40, 20)]
    assert lerp_pill_rects(one, 99) == QRect(10, 0, 40, 20)
    rects = [QRect(0, 0, 40, 20), QRect(50, 0, 40, 20), QRect(100, 0, 40, 20)]
    c0 = rects[0].center().x()
    c1 = rects[1].center().x()
    mid = lerp_pill_rects(rects, (c0 + c1) / 2)
    assert abs(mid.x() - 25) <= 1 and mid.width() == 40
    assert lerp_pill_rects(rects, 0).x() == 0
    assert lerp_pill_rects(rects, 999).x() == 100
    assert nearest_index_at_x(rects, c1) == 1
    assert nearest_index_at_x(rects, 0) == 0


def test_rounded_table_rows_install() -> None:
    """Studio tables get rounded-row delegate via enable_smooth_scroll."""
    from PySide6.QtCore import QStringListModel, Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QListView, QTableWidget

    app = QApplication.instance() or QApplication([])
    del app
    from trainz_studio.ui.smooth_scroll import enable_smooth_scroll, enable_smooth_table
    from trainz_studio.ui.table_chrome import (
        ROW_RADIUS,
        RoundedRowDelegate,
        _paint_selection_bubble,
        _row_rect,
        _view_column_count,
    )

    t = QTableWidget(2, 3)
    t.setObjectName("pkgFinder")
    t.horizontalHeader().setObjectName("pkgFinderHeader")
    enable_smooth_table(t)
    assert getattr(t, "_rounded_rows_installed", False)
    assert isinstance(t.itemDelegate(), RoundedRowDelegate)
    assert t.horizontalHeader().objectName() == "pkgFinderHeader"
    assert t.palette().color(QPalette.ColorRole.Highlight).alpha() == 0
    enable_smooth_table(t)  # idempotent
    assert isinstance(t.itemDelegate(), RoundedRowDelegate)
    assert _view_column_count(t) == 3
    # Must not touch model.columnCount (PySide binding traps differ by model type)
    _row_rect(t, t.model().index(0, 0))
    assert ROW_RADIUS >= 12.0
    # bubble painter must accept a normal row rect (smoke)
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRect

    img = QImage(80, 40, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    _paint_selection_bubble(p, QRect(4, 4, 72, 32))
    p.end()

    lv = QListView()
    lv.setModel(QStringListModel(["a", "b"]))
    enable_smooth_scroll(lv)
    assert _view_column_count(lv) == 1
    _row_rect(lv, lv.model().index(0, 0))


def test_short_glass_tip() -> None:
    from trainz_studio.ui.motion import short_glass_tip

    assert short_glass_tip("") == ""
    assert short_glass_tip("Open CDP") == "Open CDP"
    assert short_glass_tip("Open CDP — เปิดไฟล์ .cdp") == "Open CDP"
    assert short_glass_tip("Pack – long note") == "Pack"


def test_glass_tip_wraps_long_text() -> None:
    """Long VE39 tips must wrap — not one giant horizontal strip."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.motion import GlassTipBubble

    _ = QApplication.instance() or QApplication([])
    tip = GlassTipBubble()
    long = (
        "Scan listed images for near-uniform RGBA (same as Packages Finder). "
        "Uniform hits show as VE39 with a hex swatch in the Status column."
    )
    tip.set_tip(long)
    max_w = GlassTipBubble._MAX_INNER + GlassTipBubble._PAD_X * 2 + 2
    assert tip.width() <= max_w
    line_h = QFontMetrics(tip._font).height()
    assert tip.height() > line_h + GlassTipBubble._PAD_Y * 2 + GlassTipBubble._CARET


def test_qt_tooltip_uses_glass_bubble() -> None:
    """setToolTip must pop a GlassTipBubble and not the native flat tip."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    from trainz_studio.ui.motion import GlassTipBubble, install_button_hover_chrome

    app = QApplication.instance() or QApplication([])
    chrome = install_button_hover_chrome(app)
    win = QWidget()
    win.resize(320, 200)
    btn = QPushButton("Save", win)
    btn.setToolTip("Write the file — extra note")
    btn.setGeometry(40, 80, 80, 28)
    win.show()
    app.processEvents()
    pos = btn.rect().center()
    ev = QHelpEvent(QEvent.Type.ToolTip, pos, btn.mapToGlobal(pos))
    assert app.sendEvent(btn, ev) is True
    tip = getattr(win, "_icon_glass_tip", None)
    assert isinstance(tip, GlassTipBubble)
    assert tip.isVisible()
    assert tip._text == "Write the file"
    assert chrome._qt_tip_owner is btn
    chrome.clear()
    assert not tip.isVisible()
    win.close()


def test_button_hover_chrome_install() -> None:
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.motion import (
        _SKIP_BUTTON_LIFT,
        clear_button_hover_chrome,
        install_button_hover_chrome,
    )

    app = QApplication.instance() or QApplication([])
    chrome = install_button_hover_chrome(app)
    assert chrome is install_button_hover_chrome(app)  # idempotent
    assert "navBtn" in _SKIP_BUTTON_LIFT
    assert "titleNavBtn" in _SKIP_BUTTON_LIFT
    assert "navIconBtn" in _SKIP_BUTTON_LIFT
    clear_button_hover_chrome()  # must not throw when nothing hovered


def test_animate_window_quit() -> None:
    """Quit uses compositor opacity — not QGraphicsOpacityEffect on the window."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QWidget

    from trainz_studio.ui.motion import animate_window_quit

    app = QApplication.instance() or QApplication([])
    win = QWidget()
    win.resize(320, 200)
    win.show()
    done = {"ok": False}

    def _finish() -> None:
        done["ok"] = True
        loop.quit()

    loop = QEventLoop()
    animate_window_quit(win, _finish, ms=80)
    # Watchdog only — after the full suite the GUI queue can take >600ms to start this 80ms fade.
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert done["ok"]
    assert win.graphicsEffect() is None
    win.close()
    win.deleteLater()


def test_crash_dialog_quit_flag() -> None:
    """Live error OK quits; previous-session warning only dismisses."""
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.crash_dialog import _GlassCrashDialog

    app = QApplication.instance() or QApplication([])
    log = Path(".")
    err = _GlassCrashDialog(
        title="t", summary="s", detail="d", log_path=log, kind="error", quit_on_ok=True
    )
    warn = _GlassCrashDialog(
        title="t", summary="s", detail="d", log_path=log, kind="warning", quit_on_ok=False
    )
    assert err._quit_on_ok is True
    assert warn._quit_on_ok is False
    assert err.ok, [str(item) for item in err._view.errors()]
    assert warn.ok
    err.deleteLater()
    warn.deleteLater()
    del app


def test_status_toast_save_detect() -> None:
    """Save / progress / drop helpers for overlay toast bubbles."""
    from trainz_studio.ui.status_toast import (
        StudioStatusBar,
        format_drop_detail,
        is_save_notice,
        parse_progress_pct,
        toast_rest_y,
        _short_progress_detail,
        _toast_lines,
    )

    assert is_save_notice("Saved mesh.trainzmesh")
    assert is_save_notice("Project saved · demo.mtzs")
    assert is_save_notice("Wrote 3 file(s) → out")
    assert is_save_notice("Exported → config.txt")
    assert is_save_notice("บันทึกแล้ว — CDP")
    assert not is_save_notice("Autosaved · demo.mtzs")
    assert not is_save_notice("Edited — unsaved")
    assert not is_save_notice("Save .trainzmesh failed")
    assert not is_save_notice("Applied — Save to write")
    assert parse_progress_pct("Loading mesh… 42%") == 42
    assert parse_progress_pct("Export 100%") == 100
    assert parse_progress_pct("no percent here") is None
    assert format_drop_detail([type("P", (), {"name": "a.fbx"})()]) == "a.fbx"
    from pathlib import Path

    assert "b.im" in format_drop_detail([Path("a.fbx"), Path("b.im")])
    # Compact: under topbar vs centered when no bar.
    assert toast_rest_y(800, 40, 72) == 72
    assert toast_rest_y(800, 40, None) == (800 - 40) // 2
    assert _short_progress_detail("Baking lamps", "Baking lamps… 55%") == ""
    assert _short_progress_detail("Load", "Load · stage B") == "Load · stage B"
    assert _short_progress_detail(
        "Done", "Handing off · 4\ntextures ready 100%"
    ) == "Handing off · 4 textures ready"
    assert _toast_lines("Done", "Handing off · 4 textures ready 100%") == (
        "Done",
        "Handing off · 4 textures ready",
    )
    from PySide6.QtWidgets import QApplication, QWidget

    from trainz_studio.ui.status_toast import GlassToastBubble

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(900, 600)
    bubble = GlassToastBubble(
        host, kind="save", title="Saved", detail="config.txt", ms=0
    )
    app.processEvents()
    assert bubble.width() >= 300
    assert bubble.height() >= 48
    assert bubble._title.height() >= 14
    assert bubble._detail.height() >= 14
    bubble.deleteLater()
    host.deleteLater()
    bar = StudioStatusBar()
    noticed: list[str] = []
    prog: list[tuple[str, int]] = []
    bar.save_noticed.connect(noticed.append)
    bar.progress_noticed.connect(lambda m, p: prog.append((m, p)))
    bar.showMessage("Saved ok.im")
    assert noticed == ["Saved ok.im"]
    cleared: list[str] = []
    bar.progress_cleared.connect(cleared.append)
    bar.showMessage("Baking lamps… 55%")
    assert prog and prog[-1][1] == 55
    assert noticed == ["Saved ok.im"]  # % line is progress, not save
    bar.showMessage("Loaded mesh — done")  # no % → must clear sticky progress
    assert cleared == ["Loaded mesh — done"]
    bar.showMessage("Theme: dark")
    assert len(cleared) == 1  # only after a progress run
    assert len(bar.history) == 4
    bar.deleteLater()
    del app


def test_ease_out_cubic() -> None:
    from trainz_studio.render.view3d import ease_out_cubic

    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    assert ease_out_cubic(-1.0) == 0.0
    assert ease_out_cubic(2.0) == 1.0
    mid = ease_out_cubic(0.5)
    assert 0.5 < mid < 1.0  # ease-out is ahead of linear at mid


def test_theme_no_qwidget_blanket() -> None:
    from trainz_studio.ui.theme import palette, stylesheet

    css = stylesheet(palette("dark"))
    assert "QOpenGLWidget" in css
    assert "QMainWindow, QWidget" not in css
    assert palette("dark").accent == "#ff5a1f"
    assert "QWidget#loadingOverlay" in css
    assert "QFrame#loadingCard" in css
    # boot veil is painted — sheet must stay transparent (no solid splash panel)
    assert "loadingOverlay" in css and "background: transparent" in css
    # depth layer tokens + well/raise applied to nav / tables / pills
    p = palette("dark")
    assert p.well_fill and p.raise_hi and p.raise_lo
    assert "QFrame#bottomNav" in css and "QFrame#sideTabStrip" in css
    assert "QFrame#navPill" in css and "qlineargradient" in css
    assert "QPushButton#navIconBtn" in css
    assert "QPushButton#iconBtn" in css
    assert "Material Icons" in css
    assert "QListWidget, QTreeWidget" in css
    assert "QTreeWidget#engineTable" in css
    assert "studioTableHeader" in css or "engineTableHeader" in css
    # hairline grid on list/table items
    assert "border-bottom: 1px solid" in css
    # rounded table chrome — QSS leaves selection transparent (delegate paints pill)
    assert "border-top-left-radius: 12px" in css
    assert "QTableWidget::item:selected" in css or "item:selected" in css
    # light sheet must retint panel edge (was hardcoded dark)
    light_css = stylesheet(palette("light"))
    assert palette("light").glass in light_css
    assert "QLabel {" in light_css
    # shell / GL hosts follow palette bg (was hardcoded #000 → mixed light UI)
    assert "QWidget#glHost" in light_css
    assert "QWidget#appShell" in light_css
    assert palette("light").bg in light_css
    assert "qt_scrollarea_viewport" in css
    # opaque table/header fills (rgba sections painted white on Windows)
    assert "#252b33" in css  # dark header_fill
    assert "QTextEdit" in css
    assert "QTableWidget" in css
    assert "QTableCornerButton::section" in css
    # plain buttons: no accent edge on hover (looked like an orange focus ring)
    hover_idx = css.find("QToolButton:hover, QPushButton:hover")
    assert hover_idx >= 0
    hover_block = css[hover_idx : hover_idx + 280]
    assert f"border-top: 1px solid {p.accent}" not in hover_block


def test_theme_palette_sets_base_both_modes() -> None:
    """Incomplete QPalette left Windows light Base → white slabs in dark theme."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QScrollArea

    from trainz_studio.ui.frost import prepare_frost_scroll
    from trainz_studio.ui.theme import _theme_qpalette, palette

    app = QApplication.instance() or QApplication([])
    dark_p = _theme_qpalette(palette("dark"))
    light_p = _theme_qpalette(palette("light"))
    assert dark_p.color(QPalette.ColorRole.Base).name() != "#ffffff"
    # Soft gray stage — not paper white (layer depth / raised buttons need contrast).
    assert light_p.color(QPalette.ColorRole.Base).name() == "#e8ebf0"
    assert dark_p.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base).name() != "#ffffff"
    area = QScrollArea()
    area.setObjectName("sideScroll")
    body = __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()
    area.setWidget(body)
    prepare_frost_scroll(area)
    assert area.viewport() is not None
    assert area.viewport().autoFillBackground() is False
    assert body.autoFillBackground() is False
    area.deleteLater()
    del app


def test_pbr_hud_not_squeezed() -> None:
    """Compact Lit…AO HUD clears paint_glass_chip shadow air (not a flat strip)."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.app import PBR_HUD_BTN_H, PBR_HUD_H, PBR_HUD_MIN_W, SegmentedControl

    app = QApplication.instance() or QApplication([])
    hud = SegmentedControl(compact=True)
    hud.adjustSize()
    assert hud.height() == PBR_HUD_H
    assert PBR_HUD_H >= 54
    assert PBR_HUD_BTN_H >= 32
    # glass chip: top5 + bot12 — plate must stay taller than the buttons
    assert PBR_HUD_H - 5 - 12 >= PBR_HUD_BTN_H
    assert max(hud.sizeHint().width(), PBR_HUD_MIN_W) >= PBR_HUD_MIN_W
    for b in hud._buttons:
        assert b.height() == PBR_HUD_BTN_H
        assert b.minimumWidth() >= 58
    m = hud.layout().contentsMargins()
    assert m.left() >= 12 and m.right() >= 12
    assert m.bottom() >= m.top()  # extra bottom for shadow fade
    hud.deleteLater()
    del app


def test_float_chrome_bookends() -> None:
    """Floating capsule: pages split left/right of centered Home (Theme is top menu)."""
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

    from trainz_studio.ui.float_chrome import (
        FLOAT_NAV_HEIGHT,
        FLOAT_NAV_HEIGHT_TALL,
        HOME_GAP,
        HOME_GAP_TALL,
        NAV_ICON_SIDE,
        NAV_ICON_SIDE_TALL,
        make_home_button,
        mount_center_icon_nav,
        mount_page_only_nav,
        split_page_btns,
    )

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    lay = QHBoxLayout(host)
    home = make_home_button(host)
    pages = [QPushButton("A"), QPushButton("B"), QPushButton("C")]
    for b in pages:
        b.setObjectName("navBtn")
    left, right = mount_center_icon_nav(lay, home_btn=home, page_btns=pages)

    assert FLOAT_NAV_HEIGHT == 72
    assert FLOAT_NAV_HEIGHT_TALL >= 84
    assert HOME_GAP >= 14
    assert HOME_GAP_TALL >= HOME_GAP
    assert NAV_ICON_SIDE_TALL > NAV_ICON_SIDE
    assert home.width() == NAV_ICON_SIDE
    assert left == pages[:2] and right == pages[2:]
    assert split_page_btns(pages) == (pages[:2], pages[2:])
    # Order: A, B, gap, Home, gap, C
    assert lay.itemAt(0).widget() is pages[0]
    assert lay.itemAt(lay.count() - 1).widget() is pages[2]
    tall_home = make_home_button(host, side=NAV_ICON_SIDE_TALL)
    assert tall_home.width() == NAV_ICON_SIDE_TALL

    # Top sub-nav: page labels only (no Home/Theme)
    top = QWidget()
    top_lay = QHBoxLayout(top)
    sub = [QPushButton("Texture"), QPushButton("Mesh Ops")]
    got = mount_page_only_nav(top_lay, sub)
    assert got == sub
    assert top_lay.itemAt(1).widget() is sub[0]
    assert top_lay.itemAt(2).widget() is sub[1]

    from trainz_studio.ui.assets.nav import AssetsPageNav, AssetsSubNav
    from trainz_studio.ui.assets.studio import AssetsStudioHost

    assert AssetsPageNav.SUITE_PAGES["assets"][0] == (
        "packages",
        "config",
        "kuid",
        "export",
    )
    from trainz_studio.io.cdp_export import _self_check as _cdp_export_check
    from trainz_studio.ui.assets.kuid import extract_kuids

    _cdp_export_check()
    pasted = "<kuid:1:2>,<kuid:3:4> <kuid:5:6>\n<kuid:1:2>"
    assert [k.format() for k in extract_kuids(pasted)] == [
        "<kuid:1:2>",
        "<kuid:3:4>",
        "<kuid:5:6>",
    ]
    assert AssetsPageNav.SUITE_PAGES["texmesh"][0] == (
        "meshops",
        "texture",
        "parameter",
        "denoise",
    )
    assert AssetsPageNav.SUITE_PAGES["texmesh"][1] == (
        "Mesh\nLods",
        "Texture\nParams",
        "Texture\nEditor",
        "Texture\nDenoiser",
    )
    assert AssetsSubNav.PAGES == ("meshops", "texture", "parameter", "denoise")

    # Right props dock is a main-split sibling of left sidebar (not under path/nav).
    assets = AssetsStudioHost(on_home=lambda: None, on_theme=lambda: None)
    assert assets._main_split.indexOf(assets.sidebar) == 0
    qml = getattr(assets, "_assets_view", None)
    assert qml is not None and assets._assets_bridge.page == "packages"
    assert isinstance(assets._assets_bridge._page, str)
    assets._assets_bridge.setViewerPane(0)
    assert assets._assets_bridge.dockOn
    if qml is None:
        assert assets._main_split.indexOf(assets._right_dock_host) == 2
    # Texture · Mesh Lods · Editor · Denoiser · Packages Viewer
    assert assets._right_dock.count() == 5
    # Packages owns the dock by default (full-height Viewer, Mesh Editor style).
    assert not assets._right_dock_host.isHidden()
    assert assets._right_dock.currentIndex() == assets._pkg_dock_index
    assert (
        assets._right_dock.indexOf(assets.packages_page.viewer_panel)
        == assets._pkg_dock_index
    )
    lay = assets.packages_page.viewer_panel.layout()
    assert lay is not None
    assert (lay.contentsMargins().left(), lay.contentsMargins().top()) == (28, 24)
    assets._on_page("config")
    # Settle without waiting on the silk dock lerp (no event-loop pump here).
    assets._dock_animating = False
    assets._sync_right_dock(animate=False)
    assert assets._right_dock_host.isHidden()
    assets.set_suite("texmesh")
    assert assets._suite == "texmesh"
    assert assets._page == "texmesh"
    assert not assets._right_dock_host.isHidden()
    assets._on_page("meshops")
    assert assets._right_dock.currentIndex() == 1
    assets._on_page("parameter")
    assert assets._sub_page == "parameter"
    assert hasattr(assets, "param_page")
    assert assets._right_dock.currentIndex() == 2
    assert not assets._right_dock_host.isHidden()
    assets._on_page("denoise")
    assert assets._sub_page == "denoise"
    assert hasattr(assets, "denoise_page")
    assert assets._right_dock.currentIndex() == 3
    assert not assets._right_dock_host.isHidden()
    assets.set_suite("assets")
    assert assets._page == "packages"
    assert not assets._right_dock_host.isHidden()
    assert assets._right_dock.currentIndex() == assets._pkg_dock_index
    assets.deleteLater()

    host.deleteLater()
    top.deleteLater()
    del app


def test_float_title_bar_chrome() -> None:
    """Inset glass title bar: traffic lights + menus + drop animation hooks."""
    from PySide6.QtCore import QPoint, QSize, Qt
    from PySide6.QtGui import QAction, QFontMetrics
    from PySide6.QtWidgets import QApplication, QMainWindow, QMenu

    from trainz_studio.ui.title_chrome import (
        MENU_BTN_H,
        TITLE_BAR_H,
        TITLE_CONTENT_INSET,
        TITLE_MARGIN,
        FloatTitleBar,
        GlassDropMenu,
        TrafficLights,
        edge_at,
    )

    app = QApplication.instance() or QApplication([])
    win = QMainWindow()
    win.resize(900, 600)
    bar = FloatTitleBar(win, mode="dark")
    assert bar.height() == TITLE_BAR_H
    assert TITLE_CONTENT_INSET > TITLE_BAR_H
    assert isinstance(bar.lights, TrafficLights)
    assert set(bar._btns) == {"File", "Edit", "View", "Tools", "Theme", "Lang"}
    assert getattr(bar, "_hover_bubble", None) is not None
    assert all(not b.isCheckable() for b in bar._btns.values())
    assert all(b.objectName() == "titleNavBtn" for b in bar._btns.values())
    # Descender room: fixed height must clear font height after compact pad.
    lang = bar._btns["Lang"]
    fm = QFontMetrics(lang.font())
    assert MENU_BTN_H >= fm.height() + 8, (MENU_BTN_H, fm.height())
    assert lang.height() == MENU_BTN_H

    file_m = QMenu("File", win)
    file_m.addAction(QAction("Open…", win))
    file_m.addSeparator()
    file_m.addAction(QAction("Quit", win))
    edit_m = QMenu("Edit", win)
    edit_m.addAction(QAction("Undo", win))
    bar.bind_menus(
        {
            "File": file_m,
            "Edit": edit_m,
            "View": QMenu("View", win),
            "Theme": QMenu("Theme", win),
            "Lang": QMenu("Lang", win),
        }
    )
    bar.reposition(win)
    assert bar.x() == TITLE_MARGIN and bar.y() == TITLE_MARGIN
    assert bar.width() <= win.width() - TITLE_MARGIN * 2

    drop = GlassDropMenu(win)
    drop.set_theme(True)
    drop.populate(file_m)
    assert len(drop._items) == 2  # Open + Quit (separator skipped)
    edges = edge_at(QPoint(2, 100), QSize(800, 600))
    assert edges is not None
    assert edges & Qt.Edge.LeftEdge == Qt.Edge.LeftEdge

    bar.set_theme("light")
    bar.deleteLater()
    drop.deleteLater()
    win.deleteLater()
    del app


def test_material_icons_font() -> None:
    """Bundled Material Icons must load; Home/Theme glyphs resolve."""
    from PySide6.QtWidgets import QApplication, QPushButton

    from trainz_studio.ui.icons import (
        GLYPHS,
        apply_icon,
        ensure_material_icons,
        font_path,
        set_home_icon,
        set_theme_toggle_icon,
    )

    assert font_path().is_file()
    app = QApplication.instance() or QApplication([])
    assert ensure_material_icons()
    assert GLYPHS["home"] and GLYPHS["save"] and GLYPHS["folder_open"]
    assert GLYPHS["lock"] and GLYPHS["palette"]
    for key in ("layers", "graphic_eq", "tune", "inventory_2", "upload_file"):
        assert GLYPHS[key], key
    btn = QPushButton()
    set_home_icon(btn)
    assert btn.objectName() == "navIconBtn"
    assert btn.text() == GLYPHS["home"]
    set_theme_toggle_icon(btn, "dark")
    assert btn.text() == GLYPHS["light_mode"]
    act = QPushButton()
    apply_icon(act, "save", tip="Save", kind="accent")
    assert act.objectName() == "accentIconBtn"
    act.deleteLater()
    btn.deleteLater()
    del app


def test_mode_pie_glass_reveal() -> None:
    """Tab ModePie opens with glass reveal + bubbles; commit returns key and closes."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QWidget

    from trainz_studio.ui.app import ModePie
    from trainz_studio.ui.frost import set_glass_dark

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(640, 480)
    host.show()
    app.processEvents()
    pie = ModePie(
        (("Wire", "wire"), ("Solid", "solid"), ("Material", "mat"), ("Rendered", "rend")),
        title="Shading",
        default_hover=3,
        parent=host,
    )
    set_glass_dark(pie, True)
    pie.popup_at(host.mapToGlobal(QPoint(320, 240)))
    app.processEvents()
    assert pie.isVisible()
    assert pie._tick.isActive()
    assert len(pie._bubbles) >= 8
    # Drive reveal mid-open and ensure paint does not throw.
    pie._reveal = 0.85
    img = QImage(host.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    pie.render(img, QPoint())
    assert pie._sector_at(QPoint(int(pie._cx), int(pie._cy) - 80)) == 0
    mode = pie.commit()
    assert mode == "rend"
    # Close anim keeps widget visible briefly; finish must hide.
    pie._finish_close()
    assert not pie.isVisible()
    assert not pie._tick.isActive()
    host.close()
    host.deleteLater()
    del app


def test_home_glass_hub() -> None:
    """HOME builds frost studio cards + warm hover bubble (no accentBtn tiles)."""
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from trainz_studio.ui.home import HomeStudioCard, build_home_page
    from trainz_studio.ui.motion import HoverBubble

    app = QApplication.instance() or QApplication([])
    hits: list[str] = []
    page = build_home_page(
        logo=QLabel("L"),
        on_mesh=lambda: hits.append("mesh"),
        on_sounds=lambda: hits.append("sounds"),
        on_engine=lambda: hits.append("engine"),
        on_assets=lambda: hits.append("assets"),
        on_texmesh=lambda: hits.append("texmesh"),
        on_trainzutil=lambda: hits.append("trainzutil"),
        on_drop=lambda _p: None,
        theme_mode="dark",
    )
    cards = page.findChildren(HomeStudioCard)
    assert len(cards) == 6
    assert page.findChildren(QPushButton) == []
    assert cards[0]._icon_lab.width() >= 64
    titles = [c._title_src for c in cards]
    assert "Assets Tools" in titles and "Texture & Mesh Lods" in titles
    host = page._card_host
    bubble = getattr(host, "_hover_bubble", None)
    assert isinstance(bubble, HoverBubble)
    assert bubble._warm is True
    # One row: all cards share the same top after layout.
    page.resize(1280, 800)
    page.show()
    app.processEvents()
    tops = {c.geometry().top() for c in cards}
    assert len(tops) == 1, tops
    cards[0]._animate_lift(cards[0]._LIFT_PX)
    assert cards[0]._lift_anim is not None
    cards[0]._on_click()
    assert hits == ["mesh"]
    cards[4]._on_click()
    assert hits == ["mesh", "texmesh"]
    page.set_theme("light")
    assert page._theme == "light"
    page.close()
    page.deleteLater()
    del app


def test_hover_bubble_row_slide() -> None:
    """Bubble maps to host coords and keeps one continuous slide across rows."""
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

    from trainz_studio.ui.motion import HoverBubbleController, attach_hover_bubble, stop_pop

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    lay = QVBoxLayout(host)
    a = QPushButton("A")
    b = QPushButton("B")
    a.setFixedSize(120, 40)
    b.setFixedSize(120, 40)
    lay.addWidget(a)
    lay.addSpacing(40)
    lay.addWidget(b)
    host.resize(200, 200)
    host.show()
    bubble = attach_hover_bubble(
        host, (a, b), radius=12.0, pad=2, hide_ms=120, pop_on_arrive=False
    )
    ctl = host._hover_ctl
    assert isinstance(ctl, HoverBubbleController)
    ra = ctl._target_rect(a)
    rb = ctl._target_rect(b)
    assert ra.topLeft() == a.mapTo(host, QPoint(0, 0)) + QPoint(-2, -2)
    assert rb.y() > ra.y()
    ctl._move_to(a)
    assert bubble.isVisible()
    g0 = QRect(bubble.geometry())
    ctl._move_to(b)
    # Mid-slide geometry must still be animating toward B — not hidden/teleported.
    assert bubble.isVisible()
    assert getattr(bubble, "_slide_anim", None) is not None
    stop_pop(bubble)
    host.close()
    host.deleteLater()
    del app
    del g0


def test_theme_warm_cache() -> None:
    """Boot precache must leave both mode sheets/palettes ready for snappy Theme toggle."""
    from trainz_studio.ui.theme import (
        _QPAL_CACHE,
        _SHEET_CACHE,
        palette,
        stylesheet,
        warm_theme_cache,
    )

    from trainz_studio.ui.theme import theme_assets_ready

    warm_theme_cache()
    # Sheets are keyed mode:lang (font stack follows Lang); palettes stay mode-only.
    assert any(k.startswith("dark") for k in _SHEET_CACHE)
    assert any(k.startswith("light") for k in _SHEET_CACHE)
    assert "dark" in _QPAL_CACHE and "light" in _QPAL_CACHE
    assert theme_assets_ready()
    a = stylesheet(palette("dark"))
    b = stylesheet(palette("dark"))
    assert a is b
    assert len(a) > 500
    assert "Noto" in a
    # Toggle path must not re-polish every widget (was 2–5s hitch).
    import inspect

    from trainz_studio.ui.theme import apply_theme

    src = inspect.getsource(apply_theme)
    assert "rebind_font" in src
    assert "for w in app.allWidgets()" not in src


def test_frost_clears_on_set_dark() -> None:
    """Theme flip must drop stale frost plates (old blur under new tint = mixed)."""
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.frost import FrostGlassFrame

    app = QApplication.instance() or QApplication([])
    frame = FrostGlassFrame()
    pm = QPixmap(64, 64)
    pm.fill(QColor("#112233"))
    frame.set_frost(pm, dark=True)
    assert frame._frost is not None
    frame.set_dark(False)
    assert frame._dark is False
    assert frame._frost is None
    frame.deleteLater()
    del app


def test_frost_shadow_room() -> None:
    """Panel/chip shadow must reserve fade room inside the widget (no hard clip)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.float_chrome import FLOAT_NAV_HEIGHT
    from trainz_studio.ui.frost import (
        FROST_CONTENT_MARGINS,
        FrostGlassFrame,
        paint_soft_shadow,
    )
    from trainz_studio.ui.title_chrome import TITLE_BAR_H

    l, t, r, b = FROST_CONTENT_MARGINS
    assert l >= 24 and r >= 24 and t >= 20 and b >= 26
    assert FLOAT_NAV_HEIGHT >= 70
    assert TITLE_BAR_H >= 58

    app = QApplication.instance() or QApplication([])
    frame = FrostGlassFrame()
    frame.resize(200, 320)
    img = QImage(frame.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    frame.render(img)  # paintEvent soft-shadow path must not throw
    assert not img.isNull()

    p = QPainter(img)
    assert p.isActive()
    paint_soft_shadow(
        p,
        QRectF(20, 20, 160, 260),
        radius=14.0,
        dark=True,
        clip=QRectF(1, 1, 198, 318),
        max_spread=14.0,
        layers=14,
    )
    p.end()
    frame.deleteLater()
    del app


def test_old_meta_cache_is_a_hit() -> None:
    """A 3-field author cache must not reopen the tzarc. That reopen stuttered the app."""
    import json
    import struct

    from trainz_studio.io.trainz_install import scan_archive_meta

    root = Path(tempfile.mkdtemp(prefix="mstn-tu-meta-"))
    packed = bytearray(b"TZac")
    packed += struct.pack(">I", 1)
    payload = 'author "Boonnop"\ntrainz-build 4.6\nusername "キハ40"\n'.encode("utf-8")
    name = b"config.txt"
    packed += struct.pack(">I", 1)
    packed += bytes([len(name)]) + name + struct.pack(">Q", len(payload))
    packed += b"\x00\x00\x00\x00"
    packed += payload
    tzarc = root / "local" / "hash-00" / "kuid 9 9.tzarc"
    tzarc.parent.mkdir(parents=True)
    tzarc.write_bytes(packed)
    cache = root / "meta-old.json"
    cache.write_text(
        json.dumps({"<kuid:9:9>": ["Boonnop", "4.6", tzarc.stat().st_mtime_ns]}),
        encoding="utf-8",
    )
    seen: list[tuple] = []
    scan_archive_meta(
        [root],
        on_batch=lambda authors, builds, names, finished: seen.append((authors, builds, names, finished)),
        cache_path=cache,
    )
    assert any(batch[0].get("<kuid:9:9>") == "Boonnop" for batch in seen)
    assert all(batch[2].get("<kuid:9:9>", "") == "" for batch in seen)
    from trainz_studio.io.trainz_install import _read_cores
    from trainz_studio.util.hw import cpu_count

    assert _read_cores(10_000) == cpu_count()


def test_trainz_install_scan() -> None:
    """Zip members become install jobs. Unsafe paths and a missing launcher stay out."""
    import io
    import tempfile
    import zipfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from trainz_studio.io.trainz_install import (
        decode_status,
        launcher_blocked,
        scan_nested_zip,
        scan_path,
        stage_job,
        trainzutil_under_common,
    )
    from trainz_studio.ui.trainzutil_host import TrainzUtilHost

    app = QApplication.instance() or QApplication([])
    del app
    root = Path(tempfile.mkdtemp(prefix="mstn-tu-test-"))
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as nested:
        nested.writestr("wagon/config.txt", 'kuid <kuid:1:3>\n')
    with zipfile.ZipFile(root / "pack.zip", "w") as zf:
        zf.writestr("loco/config.txt", 'kuid <kuid:1:2>\n')
        zf.writestr("loco/body.im", b"x")
        zf.writestr("extra.cdp", b"cdp-bytes")
        zf.writestr("../evil.cdp", b"nope")
        zf.writestr("nested.zip", inner.getvalue())
    scanned = scan_path(root / "pack.zip")
    kinds = {job.kind for job in scanned.jobs}
    assert {"zip-folder", "zip-cdp", "zip-nested"} <= kinds
    assert all(".." not in job.member for job in scanned.jobs)
    folder = next(job for job in scanned.jobs if job.kind == "zip-folder")
    kind, staged = stage_job(folder, root / "stage")
    assert kind == "folder"
    assert (staged / "config.txt").is_file()
    nested_job = next(job for job in scanned.jobs if job.kind == "zip-nested")
    inside = scan_nested_zip(nested_job.source, nested_job.chain, nested_job.member)
    assert any(job.kind == "zip-folder" and job.member == "wagon" for job in inside)
    common = root / "steamapps" / "common"
    (common / "Trainz A New Era").mkdir(parents=True)
    (common / "Trainz A New Era" / "TrainzUtil.exe").write_bytes(b"")
    (common / "Trainz Railroad Simulator 2022").mkdir()
    newer = common / "Trainz Railroad Simulator 2022" / "TrainzUtil.exe"
    newer.write_bytes(b"")
    (common / "Some Other Game").mkdir()
    (common / "Some Other Game" / "TrainzUtil.exe").write_bytes(b"")
    assert trainzutil_under_common(common) == newer
    assert trainzutil_under_common(root / "missing") is None
    from trainz_studio import REPO_ROOT
    from trainz_studio.io.trainz_install import trainz_data_dir

    assert trainz_data_dir() == REPO_ROOT
    from trainz_studio.io.trainz_install import parse_installation_data_path

    sample = "; <NULL> : getinstallationdatapath\n  + <NULL> : D:\\Games\\Trainz Data\nOK\n"
    assert parse_installation_data_path(sample) == Path(r"D:\Games\Trainz Data")
    assert parse_installation_data_path("- <NULL> : Invalid command syntax: nope") is None
    from trainz_studio.io.trainz_install import task_outcome

    ok, line = task_outcome("  + <NULL> : Saved\nOK (0 Errors, 0 Warnings)\n")
    assert ok and line == "Saved"
    bad, err = task_outcome("- <NULL> : VE197\nOK (1 Errors, 0 Warnings)\n")
    assert not bad and err == "VE197"
    from trainz_studio.io.trainz_install import classify_trainz_line

    assert classify_trainz_line("  - <NULL> : VE197 missing") == ("error", "VE197 missing")
    assert classify_trainz_line("  + <NULL> : Saved") == ("ok", "Saved")
    assert classify_trainz_line("  ! <NULL> : obsolete kuid") == ("warn", "obsolete kuid")
    assert classify_trainz_line("OK (0 Errors, 1 Warnings)")[0] == "warn"
    assert classify_trainz_line("Running…") == ("normal", "Running…")
    from trainz_studio.io.trainz_install import parse_installed_library

    listed = parse_installed_library(
        "\n".join(
            [
                '+ <kuid:1:2> : abcdeFgILmop : VE : Broken loco',
                '+ <kuid2:3:4:1> : aBcdefGIlmopuXY : TK : Good track',
                '- <kuid:9:9> : Unknown KUID: <kuid:9:9>',
                '+ <kuid:8:8> : abcdefgLmop : MESH : Not installed',
            ]
        )
    )
    assert [row.name for row in listed] == ["Broken loco", "Good track"]
    assert listed[0].faulty and not listed[1].faulty
    from trainz_studio.io.trainz_install import read_library_cache, write_library_cache

    fake_exe = root / "TrainzUtil.exe"
    fake_exe.write_bytes(b"")
    write_library_cache(fake_exe, listed, root=root / "cache")
    cached = read_library_cache(fake_exe, root=root / "cache")
    assert [row.kuid for row in cached] == [row.kuid for row in listed]
    assert cached[0].faulty and cached[1].name == "Good track"
    assert read_library_cache(root / "missing.exe", root=root / "cache") == []
    from trainz_studio.io.trainz_install import config_credits

    credits = config_credits(
        "\n".join(
            [
                '  ; <NULL> : trainz-build                            4.6',
                '  ; <NULL> : author                                  "Boonnop"',
                '  ; <NULL> : organisation                            "SMT (Srt Mods Trainz)"',
                '  ; <NULL> : username                                "Not the author"',
            ]
        )
    )
    assert credits == "Boonnop · SMT (Srt Mods Trainz) · 4.6"
    from trainz_studio.io.trainz_install import tidy_trainzutil

    assert tidy_trainzutil("  ; <NULL> : installed, faulty") == "installed, faulty"
    from trainz_studio.io.trainz_install import read_install_pulse

    pct, status, seen = read_install_pulse("Installing <kuid:1:2>", 0, 4)
    assert seen == 1 and pct == 8 + int(1 / 4 * 87) and "kuid" in status
    pct, status, seen = read_install_pulse("Installing 40%", 1, 4)
    assert pct == 40 and seen == 2
    assert read_install_pulse("hello", 1, 4)[0] is None
    from trainz_studio.io.trainz_install import _encrypt_self_check

    _encrypt_self_check()
    assert launcher_blocked("- Trainz is not running.")
    assert "not installed" in decode_status("+ <kuid:1:2> : iEAb : name")
    up = decode_status("+ <kuid:1:2> : IEAb : name")
    assert "not installed" not in up and "installed" in up
    host = TrainzUtilHost(on_home=lambda: None, start_probe=False)
    assert host.ok, [str(err) for err in host._view_quick.errors()]
    assert host._bridge.page == "library"
    library = host._bridge._library
    library.set_assets(listed)
    library.toggle_picked(listed[0].kuid)
    assert library.selected_kuids() == [listed[0].kuid]
    assert "1 selected" in library.summary()
    library.toggle_picked(listed[1].kuid)
    assert [card["kuid"] for card in host._bridge._detail_cards] == library.selected_kuids()
    assert len(host._bridge._detail_cards) == 2
    host.focus_asset(listed[1].kuid)
    assert host._bridge._detail_kuid == listed[1].kuid
    assert len(host._bridge._detail_cards) == 2
    library.set_visible_picked(False)
    assert host._bridge._detail_cards == []
    from trainz_studio.io.trainz_install import category_is_enginespec, config_in_editing

    assert category_is_enginespec("TR;CMP;ESPC")
    assert not category_is_enginespec("TR;TV;LOC;DIES")
    editing = root / "editing" / "openasset"
    editing.mkdir(parents=True)
    (editing / "config.txt").write_text('kuid <kuid:972300:100075>\nkind "enginespec"\n', encoding="utf-8")
    assert config_in_editing(root / "editing", "<kuid:972300:100075>") == editing / "config.txt"
    assert config_in_editing(root / "editing", "<kuid:1:2>") is None
    from trainz_studio.io.trainz_install import asset_browse_dir

    assert asset_browse_dir(root, "<kuid:972300:100075>", {}) == editing
    assert asset_browse_dir(root, "<kuid:1:2>", {}) is None
    shot = editing / "$screenshot$.jpg"
    shot.write_bytes(b"\xff\xd8\xff" + b"x" * 40)
    from trainz_studio.io.trainz_install import archive_index, asset_cover_path

    assert asset_cover_path(root, "<kuid:972300:100075>") == shot
    index_root = Path(tempfile.mkdtemp(prefix="mstn-tu-cover-"))
    bucket = index_root / "local" / "abcd"
    bucket.mkdir(parents=True)
    (bucket / "kuid 9 9.tzarc").write_bytes(b"not-a-tzarc")
    assert archive_index(index_root)["<kuid:9:9>"] == bucket / "kuid 9 9.tzarc"
    assert asset_cover_path(index_root, "<kuid:9:9>", archive_index(index_root)) is None
    from trainz_studio.io.trainz_install import thumbnail_image_names

    text = 'thumbnails\n{\n  image "panel.png"\n}\nmesh-table\n{\n  image "nope.jpg"\n}\n'
    assert thumbnail_image_names(text.encode()) == ["panel.png"]

    def _pair(name: str, kind: int, payload: bytes) -> bytes:
        raw_name = name.encode() + b"\x00"
        body = bytes([len(raw_name)]) + raw_name + bytes([kind]) + payload
        return struct.pack("<I", len(body)) + body

    image = _pair("image", 3, b"thumbnail.png\x00")
    slot = _pair("0", 0, image)
    thumbs = _pair("thumbnails", 0, slot)
    chump = b"ACS$\x01\x00\x00\x00" + struct.pack("<I", len(thumbs)) + thumbs
    assert thumbnail_image_names(chump) == ["thumbnail.png"]
    from trainz_studio.io.trainz_install import kuid_from_archive_name, read_asset_dates, status_bits

    assert kuid_from_archive_name("kuid 1144998 100169.tzarc") == "<kuid:1144998:100169>"
    assert kuid_from_archive_name("kuid2 124060 21035 3.tzarc") == "<kuid2:124060:21035:3>"
    assert kuid_from_archive_name("kuid 1144998 100002 MSTN KIHA") == "<kuid:1144998:100002>"
    from trainz_studio.io.trainz_install import find_asset_backups

    backup_root = root / "data"
    day = backup_root / "backups" / "26-10-09"
    day.mkdir(parents=True)
    (day / "kuid 1144998 100079 MSTN KIHA_1").mkdir()
    (day / "kuid 1144998 100079.tzarc_99").write_bytes(b"abc")
    (day / "kuid 1 2 other").mkdir()
    (day / "s6gh667q216").mkdir()
    (backup_root / "backups" / "not-a-day").mkdir()
    copies = find_asset_backups(backup_root, "<kuid:1144998:100079>")
    assert len(copies) == 2
    assert {row.kind for row in copies} == {"Folder", "tzarc"}
    assert find_asset_backups(backup_root, "10007")[0].kuid == "<kuid:1144998:100079>"
    assert len(find_asset_backups(backup_root, "KIHA")) == 1
    assert find_asset_backups(backup_root, "") and all("s6gh" not in row.name for row in find_asset_backups(backup_root, ""))
    assert all(row.kind != "Folder" or "s6gh" not in row.name for row in find_asset_backups(backup_root, "kuid"))
    assert status_bits("abcdefgILmopuXY", open_for_edit=True)[0] == "Edit"
    bucket = root / "original" / "hash-00"
    bucket.mkdir(parents=True)
    (bucket / "kuid 1 2.tzarc").write_bytes(b"orig")
    local_bucket = root / "local" / "hash-00"
    local_bucket.mkdir(parents=True)
    (local_bucket / "kuid 1 2.tzarc").write_bytes(b"local")
    dates = read_asset_dates([root])
    assert "<kuid:1:2>" in dates["installed"] and "<kuid:1:2>" in dates["modified"]
    assert dates["sizes"]["<kuid:1:2>"] > 0
    library.set_assets(listed)
    library.set_dates(dates["installed"], dates["modified"], {})
    library.set_sort("name")
    assert [row.name for row in library._rows] == ["Broken loco", "Good track"]
    library.set_query("ood tra")
    assert [row.name for row in library._rows] == ["Good track"]
    library.set_query("")
    library.set_sort("status")
    assert library._rows[0].faulty
    library.set_dates({}, {"<kuid:1:2>": 10, "<kuid2:3:4:1>": 40}, {})
    library.set_sort("modified")
    assert library.sort_mark() == "modified:desc"
    assert library._rows[0].kuid == "<kuid2:3:4:1>"
    library.begin_drag_pick(library._rows[0].kuid)
    library.drag_pick(library._rows[1].kuid)
    assert set(library.selected_kuids()) == {"<kuid:1:2>", "<kuid2:3:4:1>"}
    library.click_pick(library._rows[0].kuid, shift=False, ctrl=False)
    library.click_pick(library._rows[1].kuid, shift=True, ctrl=False)
    assert set(library.selected_kuids()) == {"<kuid:1:2>", "<kuid2:3:4:1>"}
    library.click_pick(library._rows[0].kuid, shift=False, ctrl=True)
    assert library.selected_kuids() == ["<kuid:1:2>"]
    library.click_pick(library._rows[1].kuid, shift=False, ctrl=False)
    assert library.selected_kuids() == ["<kuid:1:2>"]
    from trainz_studio.io.trainz_install import dependency_kuids

    assert dependency_kuids(
        "+ <kuid:1:2>\n+ <kuid:9:9>\n+ <kuid:1:2>",
        skip="<kuid:1:2>",
    ) == ["<kuid:9:9>"]
    from trainz_studio.io.trainz_install import author_and_build, category_label
    from trainz_studio.io.tzarc import read_tzarc_config

    import time

    assert category_label("TR;CMP;ESPC") == "Engine Spec"
    assert category_label("SLIB") == "Script Library"
    assert category_label("BD;RRD;SY;SCEN") == "Building · Railroad"
    assert category_label("TR;TV;LOC;DIES;LOCO") == "Locomotive · Diesel"
    assert category_label("SY;SCEN") == "Scenery"
    assert category_label("TX;NEV;TXGRP;CMP") == "Texture · General · Texture Group"
    assert author_and_build('author "Boonnop"\ntrainz-build 4.6\n') == ("Boonnop", "4.6")
    from trainz_studio.io.trainz_install import author_label

    assert author_label("NightNyZ15", "5") == "NightNyZ15"
    assert author_label("3.7", "3.7") == ""
    assert author_label("3.7", "") == ""
    assert author_label("3801", "4.6") == "3801"
    from trainz_studio.io.trainz_install import credit_from_config_bytes

    def _chump_text(name: str, value: str) -> bytes:
        payload = value.encode("utf-8") + b"\x00"
        name_b = name.encode("utf-8") + b"\x00"
        pair_len = len(name_b) + 2 + len(payload)
        return struct.pack("<I", pair_len) + bytes([len(name_b)]) + name_b + bytes([3]) + payload

    soup_body = _chump_text("inside", "nope")
    soup_name = b"mesh-table\x00"
    soup = struct.pack("<I", len(soup_name) + 2 + len(soup_body)) + bytes([len(soup_name)]) + soup_name + bytes([0]) + soup_body
    body = soup + _chump_text("username", "キハ40") + _chump_text("author", "Boonnop") + _chump_text("trainz-build", "4.6")
    chump = b"ACS$" + struct.pack("<III", 1, 0, len(body)) + body
    assert credit_from_config_bytes(chump) == ("Boonnop", "4.6")
    from trainz_studio.io.trainz_install import config_identity

    assert config_identity(chump)[2] == "キハ40"
    assert config_identity('username "キハ40系"\n'.encode("utf-8"))[2] == "キハ40系"
    assert config_identity('username "キハ40系"\n'.encode("utf-16"))[2] == "キハ40系"
    assert credit_from_config_bytes(b'author "Boonnop"\ntrainz-build 4.6\n') == ("Boonnop", "4.6")

    packed = bytearray(b"TZac")
    packed += struct.pack(">I", 1)
    payload = 'author "Boonnop"\ntrainz-build 4.6\nusername "キハ40"\n'.encode("utf-8")
    name = b"config.txt"
    packed += struct.pack(">I", 1)
    packed += bytes([len(name)]) + name + struct.pack(">Q", len(payload))
    packed += b"\x00\x00\x00\x00"
    packed += payload
    tzarc = root / "local" / "hash-00" / "kuid 9 9.tzarc"
    tzarc.write_bytes(packed)
    assert read_tzarc_config(tzarc) == payload
    seen: list[tuple] = []
    from trainz_studio.io.trainz_install import scan_archive_meta

    scan_archive_meta(
        [root],
        on_batch=lambda authors, builds, names, finished: seen.append((authors, builds, names, finished)),
        cache_path=root / "meta.json",
    )
    assert any(batch[0].get("<kuid:9:9>") == "Boonnop" for batch in seen)
    assert any(batch[2].get("<kuid:9:9>") == "キハ40" for batch in seen)
    assert seen[-1][3] is True
    library.merge_meta({"<kuid2:3:4:1>": "Boonnop"}, {"<kuid2:3:4:1>": "4.6"})
    library.set_query("boonnop")
    assert [row.kuid for row in library._rows] == ["<kuid2:3:4:1>"]
    library.set_query("4.6")
    assert library._rows[0].kuid == "<kuid2:3:4:1>"
    from trainz_studio.io.trainz_install import LibraryAsset
    from PySide6.QtCore import Qt

    old = library._rows[0]
    tagged = LibraryAsset(old.kuid, old.name, old.flags, "TR;CMP;ESPC", old.faulty)
    library._all = [tagged if item.kuid == old.kuid else item for item in library._all]
    library.set_query("4.6")
    label = library.data(library.index(0, 0), int(Qt.ItemDataRole.UserRole) + 4)
    assert label == "Engine Spec"
    library.set_query("engine spec")
    assert library._rows[0].kuid == "<kuid2:3:4:1>"
    stamp = time.mktime(time.strptime("2020-05-02 08:30", "%Y-%m-%d %H:%M"))
    library.set_dates({"<kuid2:3:4:1>": stamp}, {}, {})
    library.set_query("2020-05-02")
    assert [row.kuid for row in library._rows] == ["<kuid2:3:4:1>"]
    library.set_query("")
    library.merge_names({"<kuid:1:2>": "キハ40"})
    assert library.name_for("<kuid:1:2>") == "キハ40"
    library.set_assets([LibraryAsset("<kuid:1:2>", "MSTN | ??40? |", "IL", "YL", False)])
    assert library.name_for("<kuid:1:2>") == "キハ40"
    host.shutdown()
    host.deleteLater()


def test_qml_shell_loads() -> None:
    """Phase-1 HOME + title QML must compile and expose the studios."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.qml_host import QmlHomeHost, QmlTitleBar

    app = QApplication.instance() or QApplication([])
    home = QmlHomeHost(
        on_mesh=lambda: None,
        on_sounds=lambda: None,
        on_engine=lambda: None,
        on_assets=lambda: None,
        on_texmesh=lambda: None,
        on_trainzutil=lambda: None,
        on_drop=lambda _paths: None,
    )
    assert home.ok
    ids = [c["studioId"] for c in home._bridge._cards]
    assert ids == ["mesh", "sounds", "engine", "assets", "texmesh", "trainzutil"]
    bar = QmlTitleBar()
    assert bar.ok
    labels = [m["label"] for m in bar._bridge._menus]
    assert labels[:6] == ["File", "Edit", "View", "Tools", "Theme", "Lang"]
    home.deleteLater()
    bar.deleteLater()
    del app


def test_qml_sounds_loads() -> None:
    """Sounds page QML loads and the clip list bridge accepts a row."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.sounds.studio import SoundsStudioHost

    app = QApplication.instance() or QApplication([])
    host = SoundsStudioHost(on_home=lambda: None)
    assert host._bridge is not None
    assert host._view.status().name == "Ready"

    class _Item:
        def text(self) -> str:
            return "[OK] clip.wav"

    host.library.addItem(_Item())
    assert host._bridge.clip_labels() == ["[OK] clip.wav"]
    host.deleteLater()
    del app


def test_qml_engine_loads() -> None:
    """Engine Tuner QML chrome loads; center pages are QML, graphs stay canvases."""
    import json

    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.engine.studio import EngineTunerHost

    app = QApplication.instance() or QApplication([])
    host = EngineTunerHost(on_home=lambda: None)
    assert host._eng_bridge is not None
    assert host._engine_view.status().name == "Ready"
    assert host._split.isHidden()
    bag = json.loads(host._eng_bridge.centerJson)
    assert len(bag["notches"]) == 9
    assert "motor" in bag["bags"] and "stats" in bag["sim"]
    host._eng_bridge.setPage("simulation")
    assert host._stack.currentIndex() == 1
    host._eng_bridge.setSim("mass", "120")
    assert host.sim_panel.mass.value() == 120
    host._eng_bridge.addParam("motor")
    assert any(k.startswith("new_key_") for k in host.motor_editor.data)
    host.deleteLater()
    del app


def test_qml_assets_loads() -> None:
    """Assets Tools QML chrome loads; suite nav still drives the widget stack."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.assets.studio import AssetsStudioHost

    app = QApplication.instance() or QApplication([])
    host = AssetsStudioHost(on_home=lambda: None)
    assert host._assets_bridge is not None
    assert host._assets_view.status().name == "Ready"
    assert host._assets_bridge.page == "packages"
    assert host._assets_bridge.dockOn
    assert host._assets_bridge.centerTitle
    from PySide6.QtWidgets import QLabel

    heads = [lab for lab in host._stack.findChildren(QLabel) if lab.objectName() == "pageHead"]
    assert heads and all(not lab.isVisible() for lab in heads)
    host._assets_bridge.setPage("config")
    assert host._stack.currentIndex() == 1
    assert host._assets_bridge.dockOn is False
    assert "chump" in host._assets_bridge.centerTip
    host.set_suite("texmesh")
    assert host._assets_bridge.navTall
    assert host._assets_bridge.page == "texture"
    assert host._assets_bridge.centerKind == "split"
    assert host._texmesh_lifted
    host._assets_bridge.setPage("meshops")
    assert host._assets_bridge.page == "meshops"
    assert host._assets_bridge.centerKind == "split"
    host._assets_bridge.setPage("parameter")
    assert host._assets_bridge.centerKind == "canvas"
    host._assets_bridge.setPage("denoise")
    assert host._assets_bridge.centerKind == "canvas"
    host.deleteLater()
    del app


def test_frost_motion_lod() -> None:
    """Silk slides: bake plate once, blit while lod, full glass after end."""
    from PySide6.QtGui import QColor, QImage, QPixmap
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.frost import FrostGlassFrame

    app = QApplication.instance() or QApplication([])
    frame = FrostGlassFrame()
    frame.resize(180, 240)
    pm = QPixmap(64, 64)
    pm.fill(QColor("#334455"))
    frame.set_frost(pm, dark=True)
    frame.begin_motion_lod()
    assert frame.in_motion_lod()
    assert frame._lod_pm is not None and not frame._lod_pm.isNull()
    img = QImage(frame.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    frame.render(img)
    assert not img.isNull()
    # Mid-slide frost update must not drop lod plate.
    pm2 = QPixmap(64, 64)
    pm2.fill(QColor("#556677"))
    frame.set_frost(pm2, dark=True)
    assert frame.in_motion_lod()
    frame.end_motion_lod()
    assert not frame.in_motion_lod()
    assert frame._lod_pm is None
    frame.deleteLater()
    del app


def test_scroll_wheel_reaches_child() -> None:
    """Wheel on a child inside the scroll body must move the bar."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout, QWidget

    from trainz_studio.ui.smooth_scroll import enable_smooth_scroll_area

    app = QApplication.instance() or QApplication([])
    area = QScrollArea()
    area.resize(180, 80)
    body = QWidget()
    lay = QVBoxLayout(body)
    child = QLabel("tall")
    child.setMinimumHeight(400)
    lay.addWidget(child)
    area.setWidgetResizable(True)
    area.setWidget(body)
    enable_smooth_scroll_area(area)
    area.show()
    QTest.qWait(40)
    bar = area.verticalScrollBar()
    assert bar.maximum() > 0
    ev = QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    assert area._damped_scroll.eventFilter(child, ev) is True  # type: ignore[attr-defined]
    QTest.qWait(280)
    assert bar.value() > 0
    area.deleteLater()
    app.processEvents()


def test_editor_wheel_scrolls_not_combo() -> None:
    """Wheel over a guarded combo moves the dock and leaves the index alone."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

    from trainz_studio.ui.mesh_prop_tree import guard_inputs
    from trainz_studio.ui.smooth_scroll import enable_smooth_scroll_area

    app = QApplication.instance() or QApplication([])
    area = QScrollArea()
    area.resize(180, 80)
    body = QWidget()
    lay = QVBoxLayout(body)
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    lay.addWidget(combo)
    filler = QWidget()
    filler.setMinimumHeight(400)
    lay.addWidget(filler)
    area.setWidgetResizable(True)
    area.setWidget(body)
    enable_smooth_scroll_area(area)
    guard_inputs(body)
    area.show()
    QTest.qWait(40)
    bar = area.verticalScrollBar()
    assert bar.maximum() > 0
    ev = QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    assert area._damped_scroll.eventFilter(combo, ev) is True  # type: ignore[attr-defined]
    QTest.qWait(280)
    assert bar.value() > 0
    assert combo.currentIndex() == 0
    area.deleteLater()
    app.processEvents()


def test_smooth_scroll_filter() -> None:
    from PySide6.QtWidgets import QApplication, QTreeWidget

    from trainz_studio.ui.smooth_scroll import DEFAULT_COAST, enable_smooth_table

    app = QApplication.instance() or QApplication([])
    tree = QTreeWidget()
    tree.setHeaderLabels(["a", "b"])
    enable_smooth_table(tree)
    assert tree.objectName() == "engineTable"
    assert hasattr(tree, "_damped_scroll")
    assert DEFAULT_COAST >= 0.95
    tree.deleteLater()
    app.processEvents()


def test_cuda_texel_chunk_size() -> None:
    """VRAM-aware chunking shrinks near full, grows when free."""
    from trainz_studio.lamps.bake import (
        _BYTES_PER_SAMPLE,
        _CHUNK_MIN,
        _vram_headroom,
        cuda_texel_chunk_size,
    )

    total = 12 * 1024**3  # 12 GB like RTX 3060
    head = _vram_headroom(total)
    # comfortable free → large chunk (capped)
    free_ok = head + 2 * 1024**3
    n_ok = cuda_texel_chunk_size(free_ok, total, scene_bytes=64 * 1024**2, n_samples=10**7)
    assert n_ok >= _CHUNK_MIN
    # near floor → tiny / zero
    free_low = head + _BYTES_PER_SAMPLE * 1000
    n_low = cuda_texel_chunk_size(free_low, total, scene_bytes=0, n_samples=10**7)
    assert n_low < n_ok
    # exhausted → 0 (triggers CPU fallback)
    assert cuda_texel_chunk_size(64 * 1024**2, total, scene_bytes=32 * 1024**2) == 0


def test_bake_lamps_tiny() -> None:
    """Path-trace bake writes albedo+parameter sidecars (draft / CPU)."""
    from trainz_studio.lamps.bake import BakeSettings, bake_lamps_to_textures, build_bvh, build_world
    from trainz_studio.lamps import Lamp
    from trainz_studio.io.scene import MeshPart, Scene

    # floor quad + elevated lamp tri
    floor_v = np.array(
        [[0, 0, 0], [2, 0, 0], [2, 0, 2], [0, 0, 2]], dtype=np.float32
    )
    floor_uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    floor_n = np.array([[0, 1, 0]] * 4, dtype=np.float32)
    floor_i = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    lamp_v = np.array([[0.9, 1.2, 0.9], [1.1, 1.2, 0.9], [1.0, 1.2, 1.1]], dtype=np.float32)
    lamp_i = np.array([0, 1, 2], dtype=np.uint32)
    floor = MeshPart(
        name="floor",
        vertices=floor_v,
        indices=floor_i,
        normals=floor_n,
        uvs=floor_uv,
        albedo_ref="cabin_floor_albedo",
        parameter_ref="cabin_floor_parameter",
        material_type="m.pbrmetal",
    )
    bulb = MeshPart(
        name="cabin_light",
        vertices=lamp_v,
        indices=lamp_i,
        albedo_ref="cabin_light",
        material_type="m.onetex",
    )
    sc = Scene(source="t", kind="x", parts=[floor, bulb])
    lamps = [
        Lamp(
            stem="cabin_light",
            part_id="cabin_light",
            pos=(1.0, 1.15, 1.0),
            brightness=3.0,
            range_m=4.0,
            enabled=True,
        )
    ]
    world = build_world(sc, lamps)
    assert world.v0.shape[0] >= 3
    bvh = build_bvh(world)
    assert bvh.nodes.shape[0] >= 1
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "baked_lamps"
        result = bake_lamps_to_textures(
            sc,
            lamps,
            out,
            settings=BakeSettings.from_quality(
                "draft",
                prefer_cuda=False,
                max_res=64,
                spp_direct=4,
                spp_gi=0,
                ao_spp=4,
                ao_radius=0.5,
            ),
        )
        assert not result.cancelled
        assert result.written, result.issues
        albs = [p for p in result.written if p.name.endswith("_albedo.png")]
        assert albs, result.written
        assert albs[0].is_file() and albs[0].stat().st_size > 100


def test_bake_contact_ao_cross_mesh() -> None:
    """Seat-like overhang darkens floor AO — proves multi-mesh occluders."""
    from trainz_studio.lamps.bake import _ao_texel, build_bvh, build_world
    from trainz_studio.lamps import Lamp
    from trainz_studio.io.scene import MeshPart, Scene

    floor_v = np.array(
        [[0, 0, 0], [2, 0, 0], [2, 0, 2], [0, 0, 2]], dtype=np.float32
    )
    floor_uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    floor_n = np.array([[0, 1, 0]] * 4, dtype=np.float32)
    floor_i = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    seat_v = np.array(
        [
            [0.7, 0.08, 0.7],
            [1.3, 0.08, 0.7],
            [1.3, 0.08, 1.3],
            [0.7, 0.08, 1.3],
        ],
        dtype=np.float32,
    )
    seat_i = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    floor = MeshPart(
        name="floor",
        vertices=floor_v,
        indices=floor_i,
        normals=floor_n,
        uvs=floor_uv,
        albedo_ref="floor_albedo",
        mesh_key="int",
    )
    seat = MeshPart(
        name="seat",
        vertices=seat_v,
        indices=seat_i,
        normals=np.array([[0, -1, 0]] * 4, dtype=np.float32),
        mesh_key="cab",
    )
    sc = Scene(source="t", kind="x", parts=[floor, seat])
    lamps = [Lamp(stem="x", part_id="x", pos=(1, 2, 1), brightness=1.0, enabled=True)]
    world = build_world(sc, lamps)
    bvh = build_bvh(world)
    under = _ao_texel(
        np.array([1.0, 0.0, 1.0]),
        np.array([0.0, 1.0, 0.0]),
        world,
        bvh,
        spp=48,
        radius=0.5,
        ix=10,
        iy=10,
    )
    open_c = _ao_texel(
        np.array([0.15, 0.0, 0.15]),
        np.array([0.0, 1.0, 0.0]),
        world,
        bvh,
        spp=48,
        radius=0.5,
        ix=2,
        iy=2,
    )
    assert under < open_c - 0.08, (under, open_c)


def test_lamp_discover_and_pack() -> None:
    from trainz_studio.lamps import Lamp, discover_lamps, pack_for_gpu, MAX_LAMPS
    from trainz_studio.io.scene import MeshPart, Scene

    v = np.array([[0, 1, 0], [1, 1, 0], [0, 1, 1]], dtype=np.float32)
    idx = np.array([0, 1, 2], dtype=np.uint32)
    part = MeshPart(
        name="cabin_light",
        vertices=v,
        indices=idx,
        albedo_ref="cabin_light_albedo",
        material_type="m.onetex",
    )
    sc = Scene(source="t", kind="trainzmesh", parts=[part])
    lamps = discover_lamps(sc)
    assert lamps, "onetex part should become a lamp"
    assert lamps[0].enabled is False
    assert abs(lamps[0].brightness - 0.5) < 1e-6
    assert abs(lamps[0].range_m - 0.3) < 1e-6
    # off by default → nothing on GPU
    assert pack_for_gpu(lamps)["count"] == 0
    assert pack_for_gpu(lamps)["glow"] == {}
    lamps[0].enabled = True
    packed = pack_for_gpu(lamps)
    assert packed["count"] == 1
    assert packed["power"][0] > 0
    assert packed["range"][0] < 0.5  # allow short cast (0.3 m)
    assert any(k.endswith(lamps[0].stem) or k == lamps[0].stem for k in packed["glow"])
    # glow-only mode still works
    glow_only = pack_for_gpu(lamps, cast=False)
    assert glow_only["count"] == 0
    assert glow_only["glow"]
    lamps[0].enabled = False
    assert pack_for_gpu(lamps)["count"] == 0
    assert pack_for_gpu(lamps)["glow"] == {}
    L = Lamp(stem="manual", auto=False, enabled=True, brightness=3.0, mode="spot")
    assert pack_for_gpu([L])["mode"][0] > 1.5
    assert len(pack_for_gpu([L])["pos"]) == MAX_LAMPS


def test_attachment_from_dump_xml() -> None:
    from trainz_studio.io.loaders import load_attachments_from_dump

    xml = """<?xml version="1.0"?>
<ASSIMP format_id="1">
<Scene flags="0" postprocessing="0">
<Node name="RootNode">
  <Matrix4>1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1</Matrix4>
  <NodeList num="1">
    <Node name="a.lim">
      <Matrix4>1 0 0 2  0 1 0 3  0 0 1 4  0 0 0 1</Matrix4>
    </Node>
  </NodeList>
</Node>
</Scene>
</ASSIMP>
"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.xml"
        p.write_text(xml)
        atts = load_attachments_from_dump(p)
    assert len(atts) == 1
    assert atts[0].name == "a.lim"
    assert np.allclose(atts[0].pos, (2, 3, 4))


def test_undo_stack_unlimited() -> None:
    """Undo/redo grows without cap; coalesce keeps one baseline per label."""
    from trainz_studio.io.history import EditSnapshot, UndoStack

    h = UndoStack()
    assert not h.can_undo() and not h.can_redo()
    for i in range(50):
        h.push(
            EditSnapshot(
                label=f"step {i}",
                tzmf_z=EditSnapshot.pack_tzmf(bytes([i % 256])),
                tzmf_dirty=True,
                atts=[],
            )
        )
    assert h.depth() == (50, 0)
    # coalesce same label
    h.push(
        EditSnapshot("spin", EditSnapshot.pack_tzmf(b"\x01"), True, []),
        coalesce=True,
    )
    h.push(
        EditSnapshot("spin", EditSnapshot.pack_tzmf(b"\x02"), True, []),
        coalesce=True,
    )
    assert h.depth()[0] == 51
    cur = EditSnapshot("now", EditSnapshot.pack_tzmf(b"\xff"), True, [])
    prev = h.undo(cur)
    assert prev is not None and prev.label == "spin"
    assert h.can_redo()
    nxt = h.redo(EditSnapshot("x", EditSnapshot.pack_tzmf(b"\x00"), False, []))
    assert nxt is not None and nxt.unpack_tzmf() == bytearray(b"\xff")


def test_project_and_crash_backup() -> None:
    """*.mtzs + crash self-backup roundtrip."""
    import tempfile

    from trainz_studio.io.project import (
        PROJECT_SUFFIX,
        ProjectState,
        clear_crash_backup,
        has_crash_recovery,
        load_crash_backup,
        load_project,
        save_project,
        write_crash_backup,
    )

    assert PROJECT_SUFFIX == ".mtzs"
    clear_crash_backup()
    assert not has_crash_recovery()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mesh = root / "body.trainzmesh"
        mesh.write_bytes(b"tzMF" + b"\x00" * 20)
        state = ProjectState(
            mesh_paths=[str(mesh)],
            studio_page="editor",
            editor_tab="meshes",
            sel_att=2,
            sel_mesh=1,
            theme="dark",
            tzmf_dirty=True,
            buffer=b"tzMF" + b"\x11" * 20,
        )
        proj = save_project(root / "job.mtzs", state)
        assert proj.suffix == ".mtzs" and proj.is_file()
        loaded = load_project(proj)
        assert loaded.sel_att == 2 and loaded.editor_tab == "meshes"
        assert loaded.buffer == state.buffer
        write_crash_backup(state)
        assert has_crash_recovery()
        crash = load_crash_backup()
        assert crash is not None and crash.buffer == state.buffer
        clear_crash_backup()
        assert not has_crash_recovery()


def test_tzmf_material_patch() -> None:
    """MeshEditor material block: parse + patch color / specPower / texture."""
    live = (
        Path(__file__).resolve().parents[1]
        / "editing"
        / "kuid 1125787 100059 MSTN KIHA _ ______40"
        / "body"
        / "body.trainzmesh"
    )
    if not live.is_file():
        return
    from trainz_studio.io.tzmf_edit import (
        apply_material_edits,
        parse_attachment_records,
        parse_materials,
        set_attachment_yup,
    )

    data = bytearray(live.read_bytes())
    mats = parse_materials(data)
    assert len(mats) >= 8
    m0 = mats[0]
    assert m0.name == "hornblack.m.pbrmetal"
    assert abs(m0.spec_power - 25.0) < 1e-3
    data2 = apply_material_edits(
        bytearray(data),
        m0,
        color=(1.0, 0.0, 0.0, 1.0),
        spec_power=12.5,
        textures={"txAlbedo": "hornblack_albedo.TEXTURE"},
    )
    m2 = parse_materials(data2)[0]
    assert abs(m2.color[0] - 1.0) < 1e-5 and abs(m2.color[1]) < 1e-5
    assert abs(m2.spec_power - 12.5) < 1e-3
    assert next(t.value for t in m2.textures if t.key == "txAlbedo").endswith("TEXTURE")
    air = next(a for a in parse_attachment_records(data) if a.name == "a.airdryer")
    set_attachment_yup(data, air, pos_yup=(1.2, 0.5, -1.0))
    air2 = next(a for a in parse_attachment_records(data) if a.name == "a.airdryer")
    assert abs(air2.pos_yup[0] - 1.2) < 1e-5


def test_trainzmesh_attachments() -> None:
    """tzMF a.* table: length-prefixed name + BE pos/quat stay Trainz Z-up."""
    import struct

    from trainz_studio.io.loaders import parse_trainzmesh_attachments

    # Z-up pos kept as-is; identity quat → I₃
    name = b"a.bog0"
    blob = bytes([len(name)]) + name + struct.pack(">7f", 0.0, -7.2, 0.0, 0.0, 0.0, 0.0, 1.0)
    # pad + second point
    name2 = b"a.cab"
    blob += b"\x00\x00\xff\x7f\x7f\xff\xff"
    blob += bytes([len(name2)]) + name2 + struct.pack(">7f", 1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)
    atts = parse_trainzmesh_attachments(blob)
    assert [a.name for a in atts] == ["a.bog0", "a.cab"]
    assert np.allclose(atts[0].pos, (0.0, -7.2, 0.0), atol=1e-5)
    assert np.allclose(atts[1].pos, (1.0, 2.0, 3.0), atol=1e-5)
    assert np.allclose(atts[0].orient, (1, 0, 0, 0, 1, 0, 0, 0, 1), atol=1e-5)

    # Finite garbage (all 10000) is not an attachment — it used to fill Name.
    ghost = b"a.ghostname"
    junk = bytes([len(ghost)]) + ghost + struct.pack(">7f", *([10000.0] * 7))
    assert parse_trainzmesh_attachments(junk) == []
    from trainz_studio.io.tzmf_edit import parse_attachment_records

    assert parse_attachment_records(junk) == []

    # Live KIHA body when present: count + one known point vs sibling FBX
    live = (
        Path(__file__).resolve().parents[1]
        / "editing"
        / "kuid 1125787 100059 MSTN KIHA _ ______40"
        / "body"
        / "body.trainzmesh"
    )
    if live.is_file():
        from trainz_studio.io.loaders import load_any

        sc = load_any(live)
        assert len(sc.attachments) >= 90, len(sc.attachments)
        bog = next(a for a in sc.attachments if a.name == "a.bog0")
        assert np.allclose(bog.pos, (0.0, -7.2, 0.0), atol=1e-3)


def test_texcache_roundtrip() -> None:
    from trainz_studio.io.texcache import clear_cache, load_rgba, preload_textures

    png = FIXTURES / "sample_albedo.png"
    clear_cache()
    w1, h1, px1 = load_rgba(png, use_cache=True)
    assert w1 == 64 and h1 == 64 and len(px1) == 64 * 64 * 4
    # second hit must come from disk cache (same bytes)
    w2, h2, px2 = load_rgba(png, use_cache=True)
    assert (w2, h2) == (w1, h1) and px2 == px1
    got = preload_textures([str(png)])
    assert str(png) in got


def test_texture_fixtures() -> None:
    ok = check_texture_txt(FIXTURES / "sample_albedo.texture.txt")
    assert ok.ok, format_issues(ok)
    assert ok.primary_size == (64, 64)
    bad = check_texture_txt(FIXTURES / "bad_missing.texture.txt")
    assert not bad.ok
    assert any("missing" in i.message for i in bad.issues)
    reports = scan_folder(FIXTURES)
    assert len(reports) >= 2
    png = FIXTURES / "sample_albedo.png"
    assert image_size(png) == (64, 64)


def test_kin_scan() -> None:
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        # non-JIRF blob
        kin = folder / "idle.kin"
        kin.write_bytes(b"\x00\x01\x02KIN" + b"\x00" * 64)
        clips = scan_kin_files(folder)
        assert len(clips) == 1
        assert clips[0].name == "idle.kin"
        assert clips[0].frame_count == 0
        assert "jirf" in clips[0].note.lower()

        # Minimal JIRF: ANIMINFO frame_count=12, one BONE name
        # layout matches doorfront_scene.kin probe
        name = b"r.doorfront"
        bone = b"BONE" + b"\x00" * 4 + (0x64).to_bytes(4, "little")
        bone += len(name).to_bytes(4, "little") + name
        hdr = bytearray()
        hdr += b"JIRF" + b"\x00" * 4
        hdr += b"ANIMINFO" + b"\x00" * 4
        hdr += (0x0101).to_bytes(4, "little")  # version
        hdr += (0).to_bytes(4, "little")  # flags
        hdr += (12).to_bytes(4, "little")  # frames @28
        hdr += (60).to_bytes(4, "little")  # tick
        hdr += struct.pack("<f", 1.0)
        hdr += (1).to_bytes(4, "little")
        hdr += bone
        kin2 = folder / "doors.kin"
        kin2.write_bytes(bytes(hdr))
        clip = peek_kin(kin2)
        assert clip.frame_count == 12, clip.note
        assert clip.bone_names == ["r.doorfront"], clip.bone_names

    # Real KIHA door sample if present in backups
    sample = (
        Path(r"c:\trs22\backups\26-09-30")
        / "kuid 1125787 100060 MSTN KIHA _ ______40"
        / "door"
        / "doorfront_scene.kin"
    )
    if sample.is_file():
        real = peek_kin(sample)
        assert real.frame_count == 99, real.note
        assert "r.doorfront" in real.bone_names, real.bone_names


def _minimal_im_with_atch(atts: list) -> bytes:
    """Build a tiny JIRF/IDXM/.im with only an ATCH chunk (for ImDocument tests)."""
    from trainz_studio.lib.im_editor.core import Attachment, build_atch_payload

    payload = build_atch_payload(atts)
    out = bytearray()
    out += b"JIRF"
    out += b"\x00\x00\x00\x00"  # size patched later
    out += b"IDXM"
    out += b"ATCH"
    out += struct.pack("<I", len(payload))
    out += payload
    struct.pack_into("<I", out, 4, len(out) - 8)
    return bytes(out)


def test_im_fast_preview_geom() -> None:
    """Finder fast preview decodes a GEOM triangle out of a tiny .im."""
    from trainz_studio.io.loaders import load_any

    def jet(text: str) -> bytes:
        raw = text.encode("utf-8") + b"\0"
        pad = (4 - (len(raw) % 4)) % 4
        body = raw + (b"\0" * pad)
        return struct.pack("<I", len(body)) + body

    def chunk(tag: bytes, body: bytes) -> bytes:
        return tag + struct.pack("<I", len(body)) + body

    geom = bytearray()
    geom += struct.pack("<I", 201)
    geom += struct.pack("<I", 4)
    geom += struct.pack("<I", 0)
    geom += struct.pack("<f", 0.5)
    geom += struct.pack("<IIII", 3, 1, 3, 1)
    geom += struct.pack("<I", 1)
    geom += struct.pack("<I", 0)
    geom += struct.pack("<fffff", 0, 0, 0, 0, 0)
    geom += struct.pack("<fffff", 1, 0, 0, 1, 0)
    geom += struct.pack("<fffff", 0, 1, 0, 0, 1)
    geom += struct.pack("<HHH", 0, 1, 2)
    geom += struct.pack("<fff", 0, 0, 1) * 3
    geom += struct.pack("<fff", 0, 0, 1)
    matl = struct.pack("<I", 103) + jet("body.m.onetex")
    chnk = struct.pack("<II", 100, 0) + chunk(b"MATL", matl) + chunk(b"GEOM", bytes(geom))
    payload = b"IDXM" + chunk(b"CHNK", chnk)
    blob = b"JIRF" + struct.pack("<I", len(payload)) + payload
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "tri.im"
        path.write_bytes(blob)
        scene = load_any(path, preview_fast=True)
    assert scene.kind == "im"
    assert scene.vertex_count == 3
    assert scene.face_count == 1
    assert scene.parts[0].name == "body.m.onetex"
    assert float(scene.parts[0].vertices[1, 0]) == 1.0
    from trainz_studio.lib.im_editor.core import IDENTITY_ORIENT
    from trainz_studio.lib.im_editor.core import Attachment as ImAtt

    atch = _minimal_im_with_atch([ImAtt("a.cab", IDENTITY_ORIENT, (1.0, 2.0, 3.0))])
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "cab.im"
        path.write_bytes(atch)
        points = load_any(path, preview_fast=True)
    assert points.vertex_count == 0
    assert len(points.attachments) == 1
    assert points.attachments[0].name == "a.cab"
    assert points.attachments[0].pos == (1.0, 2.0, 3.0)


def test_im_document_add_remove() -> None:
    from trainz_studio.lib.im_editor.core import (
        IDENTITY_ORIENT,
        Attachment,
        ImDocument,
        parse_attachments,
    )

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "tiny.im"
        seed = [
            Attachment("a.origin", IDENTITY_ORIENT, (1.0, 2.0, 3.0)),
        ]
        path.write_bytes(_minimal_im_with_atch(seed))
        doc = ImDocument()
        doc.open(path)
        assert len(doc.atts) == 1
        idx = doc.add("a.new", pos=(0.5, 0.0, -1.0))
        assert idx == 1
        assert doc.atts[1].name == "a.new"
        assert doc.atts[1].pos == (0.5, 0.0, -1.0)
        try:
            doc.add("a.new")
            raise AssertionError("duplicate name should fail")
        except ValueError:
            pass
        doc.remove(0)
        assert [a.name for a in doc.atts] == ["a.new"]
        out = doc.save()
        assert out == path
        again = parse_attachments(path.read_bytes())
        assert len(again) == 1
        assert again[0].name == "a.new"
        assert again[0].pos == (0.5, 0.0, -1.0)


def test_named_two_sided_does_not_touch_other_parts() -> None:
    """Double Sided flags that material only — no full scene rebuild."""
    from trainz_studio.io.scene import MeshPart
    from trainz_studio.render.view3d import apply_named_two_sided

    body = MeshPart("body.m.pbrmetal", None, None)
    door = MeshPart("door.m.pbrmetal", None, None)
    batch_body = type("B", (), {"name": "body.m.pbrmetal", "two_sided": False})()
    batch_door = type("B", (), {"name": "door.m.pbrmetal", "two_sided": False})()
    n = apply_named_two_sided(
        [body, door], [batch_body, batch_door], "body.m.pbrmetal", True
    )
    assert n == 1
    assert body.two_sided is True and batch_body.two_sided is True
    assert door.two_sided is False and batch_door.two_sided is False
    short = MeshPart("air_hold", None, None)
    short_batch = type("B", (), {"name": "air_hold", "two_sided": False})()
    n2 = apply_named_two_sided(
        [short, door], [short_batch, batch_door], "air_hold.m.pbrmetal", True
    )
    assert n2 == 1 and short.two_sided is True and short_batch.two_sided is True
    assert door.two_sided is False


def test_mesh_meta_two_sided() -> None:
    from trainz_studio.io.mesh_meta import (
        mesh_meta_path,
        parse_two_sided_map,
        set_material_two_sided,
        write_two_sided,
        write_two_sided_many,
        write_two_sided_map,
    )
    from trainz_studio.io.scene import MeshPart
    from trainz_studio.io.mesh_meta import apply_meta_two_sided_to_parts

    assert mesh_meta_path(Path("a/b/cab.fbx")) == Path("a/b/cab.txt")
    text = set_material_two_sided("", "fence.m.pbrmetal", True)
    assert "two-sided 1" in text
    assert "fence.m.pbrmetal" in text
    mapping = parse_two_sided_map(text)
    assert mapping["fence.m.pbrmetal"] is True
    text2 = set_material_two_sided(text, "fence.m.pbrmetal", False)
    assert parse_two_sided_map(text2)["fence.m.pbrmetal"] is False
    # preserve other material when adding second
    text3 = set_material_two_sided(text2, "glass.m.glass", True)
    m3 = parse_two_sided_map(text3)
    assert m3["fence.m.pbrmetal"] is False
    assert m3["glass.m.glass"] is True

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mesh = root / "body.fbx"
        mesh.write_bytes(b"")
        meta = write_two_sided(root / "body.txt", "seat.m.onetex", True)
        assert meta.is_file()
        write_two_sided_many(
            meta, ["glass.m.glass", "door.m.pbrmetal"], True
        )
        both = parse_two_sided_map(meta.read_text(encoding="utf-8"))
        assert both["seat.m.onetex"] is True
        assert both["glass.m.glass"] is True
        assert both["door.m.pbrmetal"] is True
        write_two_sided_map(
            meta, {"glass.m.glass": False, "frame.m.pbrmetal": True}
        )
        mapped = parse_two_sided_map(meta.read_text(encoding="utf-8"))
        assert mapped["glass.m.glass"] is False
        assert mapped["frame.m.pbrmetal"] is True
        assert mapped["seat.m.onetex"] is True
        np = __import__("numpy")
        part = MeshPart(
            name="seat.m.onetex",
            vertices=np.zeros((3, 3), dtype="float32"),
            indices=np.array([0, 1, 2], dtype="uint32"),
        )
        other = MeshPart(
            name="body.m.pbrmetal",
            vertices=np.zeros((3, 3), dtype="float32"),
            indices=np.array([0, 1, 2], dtype="uint32"),
        )
        # no meta → off (not stuck on)
        assert apply_meta_two_sided_to_parts([part, other], None) == 0
        assert part.two_sided is False
        assert other.two_sided is False
        n = apply_meta_two_sided_to_parts([part, other], meta)
        assert n == 1
        assert part.two_sided is True
        assert other.two_sided is False  # only listed materials


def test_code_edit_trainzconfig_spans() -> None:
    """vscode-trainzscript-style scopes for config / texture.txt (no GUI)."""
    from trainz_studio.ui.code_edit import classify_trainzconfig_spans

    spans = classify_trainzconfig_spans("Primary=body.tga")
    assert any(s == "tag" and n == len("Primary") for _, n, s in spans)

    spans = classify_trainzconfig_spans('AlphaHint="opaque"')
    kinds = {s for _, _, s in spans}
    assert "tag" in kinds and "string" in kinds

    spans = classify_trainzconfig_spans('username  "My Asset"')
    kinds = {s for _, _, s in spans}
    assert "tag" in kinds and "string" in kinds

    spans = classify_trainzconfig_spans("kuid  <kuid:474195:100073>")
    kinds = {s for _, _, s in spans}
    assert "tag" in kinds and "kuid" in kinds

    spans = classify_trainzconfig_spans("offset  0.01")
    kinds = {s for _, _, s in spans}
    assert "tag" in kinds and "number" in kinds

    spans = classify_trainzconfig_spans("# freeze")
    assert spans and spans[0][2] == "comment"

    from trainz_studio.ui.code_edit import (
        classify_trainzscript_spans,
        syntax_for_filename,
    )

    assert syntax_for_filename("kiha_drive_logic.gs") == "trainzscript"
    assert syntax_for_filename("config.txt") == "trainzconfig"
    assert syntax_for_filename("body.texture.txt") == "trainzconfig"

    spans, in_block = classify_trainzscript_spans("/* head")
    assert in_block and spans and spans[0][2] == "comment"
    spans, in_block = classify_trainzscript_spans(" still */ class X", in_block_comment=True)
    assert not in_block
    kinds = {s for _, _, s in spans}
    assert "comment" in kinds and "keyword" in kinds and "class" in kinds

    spans, _ = classify_trainzscript_spans('include "gs.gs"')
    kinds = {s for _, _, s in spans}
    assert "keyword" in kinds and "string" in kinds

    spans, _ = classify_trainzscript_spans("define int STOP_NONE = 0;")
    kinds = {s for _, _, s in spans}
    assert "keyword" in kinds and "type" in kinds and "macro" in kinds and "number" in kinds

    spans, _ = classify_trainzscript_spans("  // gear")
    assert spans and spans[0][2] == "comment"


def test_editor_find_config_and_workspace() -> None:
    from trainz_studio.ui.editor import EditorWorkspace, find_config_txt

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mesh = root / "meshes" / "body.im"
        mesh.parent.mkdir(parents=True)
        mesh.write_bytes(b"")
        cfg = root / "config.txt"
        cfg.write_text("kuid 1 2\n", encoding="utf-8")
        found = find_config_txt(mesh, mesh.parent)
        assert found == cfg

    with tempfile.TemporaryDirectory() as td2:
        alone = Path(td2) / "x.im"
        alone.write_bytes(b"")
        assert find_config_txt(alone) is None

    # EditorWorkspace needs a QApplication
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    ws = EditorWorkspace()
    assert ws.tabs.count() == 2
    assert ws.texture is not None
    assert hasattr(ws, "meshes_page")
    assert hasattr(ws, "attachments_page")
    assert not any(w.objectName() == "sideTabStrip" for w in ws.findChildren(QWidget))
    assert ws._title.text() == "Attachs Editor"
    assert not hasattr(ws, "config")
    ws.set_im_writable(False)
    assert not ws.att_save_btn.isEnabled()
    ws.set_im_writable(True)
    assert ws.att_save_btn.isEnabled()
    ws.show_texture_tab()  # compat → Meshes
    assert ws.tabs.currentWidget() is ws.meshes_page
    ws.show_meshes_tab()
    assert ws.tabs.currentWidget() is ws.meshes_page
    assert ws._title.text() == "Meshes Editor"
    assert ws.current_mode() == "meshes"
    ws.show_attachments_tab()
    assert ws.tabs.currentIndex() == 0
    assert ws._title.text() == "Attachs Editor"
    assert ws.maximumWidth() == 520
    # Wheel must not step spins, combos, or sliders (including the inner line edit).
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    def _wheel() -> QWheelEvent:
        return QWheelEvent(
            QPointF(4, 4),
            QPointF(4, 4),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    combo = ws.meshes_page.detail.type_combo
    combo.setCurrentIndex(0)
    QApplication.sendEvent(combo, _wheel())
    assert combo.currentIndex() == 0
    spin = ws.meshes_page.detail.spec_power
    detail = ws.meshes_page.detail
    assert spin.minimumHeight() == detail.name_edit.minimumHeight() == 36
    assert spin.maximumWidth() > 200  # same column width as Name / texture fields
    assert detail.type_combo.minimumHeight() == 36
    assert detail.mat_color._swatch.minimumHeight() == 36
    assert detail.mat_color._swatch.text()  # palette glyph, not an empty square
    assert [ch.tag.text() for ch in detail.mat_color._channels] == ["R", "G", "B", "A"]
    chan = detail.mat_color._spins[0]
    assert chan.prefix() == ""
    shown = chan.lineEdit().text()
    assert shown.strip().lstrip("-").isdigit()
    assert chan.lineEdit().focusPolicy() != detail.mat_color._channels[0].tag.focusPolicy()
    from trainz_studio.ui.mesh_prop_tree import TextureSlotRow

    slot = TextureSlotRow("txAlbedo", "body.texture")
    assert slot._btn.property("mi_name") == "folder_open"
    assert slot._btn.text() != "…"
    locked = TextureSlotRow("txEnvBRDF", "$pbr-envbrdf", readonly=True)
    assert locked._btn.property("mi_name") == "lock"
    slot.deleteLater()
    locked.deleteLater()
    spin.setValue(2.5)
    QApplication.sendEvent(spin, _wheel())
    assert abs(spin.value() - 2.5) < 1e-6
    line = spin.lineEdit()
    assert line is not None
    QApplication.sendEvent(line, _wheel())
    assert abs(spin.value() - 2.5) < 1e-6
    loc0 = ws.attachments_page.detail.loc[0]
    assert loc0.maximumWidth() > 200  # same column as Name, not a 76px stub
    assert loc0.minimumHeight() == 36
    att = ws.attachments_page.detail
    att.name_edit.setText("ghost")
    att.loc[0].setValue(10000)
    att.clear()
    assert att.name_edit.text() == ""
    assert att.loc[0].value() == 0.0
    assert not att.isEnabled()
    # Noto label column + four color channels. Still far below the 480 dock.
    assert ws.meshes_page.detail.minimumSizeHint().width() <= 360
    assert ws.attachments_page.detail.minimumSizeHint().width() <= 300
    tex_combo = ws.texture._compression
    tex_idx = tex_combo.currentIndex()
    QApplication.sendEvent(tex_combo, _wheel())
    assert tex_combo.currentIndex() == tex_idx
    slider = ws.texture._emis
    slider_val = slider.value()
    QApplication.sendEvent(slider, _wheel())
    assert slider.value() == slider_val

    # Texture.txt helpers still available (hidden editor)
    with tempfile.TemporaryDirectory() as td3:
        tdir = Path(td3)
        tex = tdir / "body_albedo.texture.txt"
        tex.write_text("Primary=body.tga\nCompression=dxt5\n", encoding="utf-8")
        (tdir / "body.tga").write_bytes(b"")  # missing real TGA ok for list
        ws.texture.set_files([tex])
        assert ws.texture._list.count() == 1
        assert ws.texture.path == tex or ws.texture._list.currentRow() == 0
        from trainz_studio.ui.editor import _set_texture_txt_key, _parse_texture_txt_keys

        t2 = _set_texture_txt_key("Primary=a.tga\n", "Compression", "dxt1")
        assert "Compression=dxt1" in t2
        assert _parse_texture_txt_keys(t2)["Primary"] == "a.tga"
        assert hasattr(ws.texture, "two_sided_changed")
        ws.texture.set_two_sided_context(
            tdir / "body.txt", "body.m.pbrmetal", True, tip="test"
        )
        on, mat = ws.texture.two_sided_state()
        assert on is True
        assert mat == "body.m.pbrmetal"

    ws.deleteLater()

    # glass load bar clamp (same QApp)
    from trainz_studio.ui.app import GlassProgressBar, MainWindow, _compact_tip

    bar = GlassProgressBar()
    bar.setValue(-5)
    assert bar.value() == 0
    bar.setValue(140)
    assert bar.value() == 100
    bar.setValue(42)
    assert bar.value() == 42
    bar.deleteLater()

    from PySide6.QtWidgets import QLabel

    tip = QLabel("compact tip")
    _compact_tip(tip)
    assert tip.objectName() == "mutedTip"

    # Catch silent pythonw boot crashes (e.g. missing helpers in sidebar tabs).
    win = MainWindow()
    assert win.windowTitle().startswith("MSTN Trainz Studio")
    assert hasattr(win, "_hub")
    assert win._studio_mode == "home"
    assert win._chrome_ready is False  # HOME shell only at ctor
    win.ensure_studio_chrome()
    assert win._chrome_ready and win.editor is not None
    win._ensure_sounds_host()
    assert win._sounds_host is not None
    win._ensure_engine_host()
    assert win._engine_host is not None
    win._ensure_assets_host()
    assert win._assets_host is not None
    from trainz_studio.audio.classify import classify_path, partition_paths
    from pathlib import Path as _P

    assert classify_path(_P("a.fbx")) == "mesh"
    assert classify_path(_P("a.wav")) == "audio"
    assert classify_path(_P("a.mp4")) == "video"
    assert classify_path(_P("job.mtzs")) == "project"
    parts = partition_paths([_P("x.im"), _P("y.mp3"), _P("z.mtzs")])
    assert parts["mesh"] and parts["audio"] and parts["project"]
    win.close()
    win.deleteLater()
    _ = app  # keep alive for widget lifetime


def test_mat_names() -> None:
    """Mesh Ops material suffix check + FBX rename round-trip."""
    import tempfile

    from trainz_studio.io.mat_names import (
        apply_renames,
        check_mat_name,
        list_materials,
        scan_materials,
        suggested_mapping,
    )

    ok = check_mat_name("body.m.pbrmetal")
    assert ok.kind == "ok" and not ok.needs_fix
    miss = check_mat_name("body")
    assert miss.kind == "missing_suffix" and miss.suggested == "body.m.pbrmetal"
    typo = check_mat_name("door.m.pbrmetl")
    assert typo.needs_fix and typo.suggested == "door.m.pbrmetal"
    blend = check_mat_name("lamp.m.onetex.001")
    assert blend.kind == "blender_dup" and blend.suggested == "lamp.m.onetex"
    alias = check_mat_name("glow.m.stdonetex")
    assert alias.suggested == "glow.m.onetex"

    sample = (
        Path(__file__).resolve().parent.parent
        / "backups"
        / "26-10-03"
        / "kuid 1125787 100059 MSTN KIHA _ ______40"
        / "body"
        / "body.fbx"
    )
    if not sample.is_file():
        return
    names = list_materials(sample)
    assert "body.m.pbrmetal" in names
    issues = scan_materials(sample)
    assert all(i.kind == "ok" for i in issues)
    assert suggested_mapping(issues) == {}

    with tempfile.TemporaryDirectory(prefix="mat_names_") as tmp:
        dest = Path(tmp) / "body.fbx"
        dest.write_bytes(sample.read_bytes())
        n = apply_renames(
            dest,
            {"body.m.pbrmetal": "body_renamed.m.pbrmetal"},
            backup=True,
        )
        assert n == 1
        assert "body_renamed.m.pbrmetal" in list_materials(dest)
        assert "body.m.pbrmetal" not in list_materials(dest)
        assert dest.with_suffix(".fbx.bak-mat").is_file()
        n2 = apply_renames(
            dest,
            {"body_renamed.m.pbrmetal": "body.m.pbrmetal"},
            backup=False,
        )
        assert n2 == 1
        assert "body.m.pbrmetal" in list_materials(dest)


def test_assets_kuid_normalize() -> None:
    from trainz_studio.io import kuid_bin
    from trainz_studio.io.lm import LmFile, LmMesh, format_lm_txt, parse_lm_txt
    from trainz_studio.io.texture import default_texture_keys, format_texture_txt, parse_texture_txt
    from trainz_studio.ui.assets.kuid import count_kuids, extract_kuids, normalize_list

    text = "deps: <kuid:123:456> and kuid2:7:8:9 plus <kuid:123:456> again"
    ks = extract_kuids(text)
    assert len(ks) == 2
    assert ks[0].format() == "<kuid:123:456>"
    assert ks[1].format() == "<kuid2:7:8:9>"
    assert count_kuids(text) == 2
    assert normalize_list(text).splitlines() == ["<kuid:123:456>", "<kuid2:7:8:9>"]

    # CDPExplorer kuid-format.md: <kuid:474195:100073> packing
    raw = kuid_bin.pack_kuid(474195, 100073, None)
    assert kuid_bin.bytes_to_hex(raw) == "53 3C 07 00 E9 86 01 00"
    assert kuid_bin.bytes_to_kuid(raw) == "<kuid:474195:100073>"
    assert kuid_bin.hash_folder(raw) == "hash-06"
    # Doc hash-00 sample bytes
    assert kuid_bin.hash_folder(bytes.fromhex("9E C8 00 00 DD 8A 01 00")) == "hash-00"

    lm = LmFile(meshes=[LmMesh(0.3, "a.im"), LmMesh(1.0, "b.im")])
    body = format_lm_txt(lm)
    assert 'mesh("0.3")' in body and 'name="a.im"' in body
    back = parse_lm_txt(body)
    assert len(back.meshes) == 2 and back.meshes[0].name == "a.im"

    # Mesh Ops drop classifier (no GUI)
    from trainz_studio.ui.assets.studio import (
        _LM_MESH_EXTS,
        _lm_drop_paths,
        _lm_mesh_name_for_lm,
    )

    assert _LM_MESH_EXTS == {".trainzmesh", ".im", ".fbx"}
    assert _lm_mesh_name_for_lm(Path("hi.fbx")) == "hi.trainzmesh"
    assert _lm_mesh_name_for_lm(Path("body.im")) == "body.im"
    assert _lm_mesh_name_for_lm(Path("a.trainzmesh")) == "a.trainzmesh"

    # Name cell: narrow width hint + tall enough for title+subtitle (row 64).
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.assets.studio import _ElideLabel, _TEX_ROW_H, _TexNameCell

    _ = QApplication.instance() or QApplication([])
    assert _TEX_ROW_H >= 60
    assert _ElideLabel("main_mstn_pa_cursor_albedo.png").sizeHint().width() <= 40
    cell = _TexNameCell(
        "main_mstn_pa_cursor_albedo.png", "fam · PBR ✓", badge="A", color="#30d158"
    )
    assert cell.minimumSizeHint().width() <= 80
    assert cell.sizeHint().height() >= _TEX_ROW_H

    class _Url:
        def __init__(self, path: str) -> None:
            self._path = path

        def isLocalFile(self) -> bool:
            return True

        def toLocalFile(self) -> str:
            return self._path

    meshes, lms = _lm_drop_paths(
        [
            _Url(r"C:\a\body.im"),
            _Url(r"C:\a\body.lm.txt"),
            _Url(r"C:\a\skip.obj"),
            _Url(r"C:\a\hi.fbx"),
        ]
    )
    assert [p.name for p in meshes] == ["body.im", "hi.fbx"]
    assert [p.name for p in lms] == ["body.lm.txt"]

    from trainz_studio.io.texture import IMAGE_EXTS
    from trainz_studio.ui.assets.studio import _tex_drop_paths

    assert ".tga" in IMAGE_EXTS and ".png" in IMAGE_EXTS
    images, texts = _tex_drop_paths(
        [
            _Url(r"C:\a\body_albedo.tga"),
            _Url(r"C:\a\body_albedo.texture.txt"),
            _Url(r"C:\a\skip.obj"),
            _Url(r"C:\a\nmap.png"),
            _Url(r"C:\a\mask.bmp"),
        ]
    )
    assert [p.name for p in images] == ["body_albedo.tga", "nmap.png", "mask.bmp"]
    assert [p.name for p in texts] == ["body_albedo.texture.txt"]

    keys = default_texture_keys(primary="x.tga", usage="albedo", tile="st")
    txt = format_texture_txt(keys)
    assert "Primary=x.tga" in txt and "Tile=st" in txt and " = " not in txt
    assert parse_texture_txt(txt)["Primary"] == "x.tga"

    from trainz_studio.io.texture import keys_for_image

    alb = keys_for_image("body_albedo.tga", tile="st")
    assert alb["UsageHint"] == "albedo" and "NormalMapHint" not in alb
    nrm = keys_for_image("body_normal.png")
    assert nrm["UsageHint"] == "normal" and nrm["NormalMapHint"] == "normalmap"
    prm = keys_for_image("body_parameter.tga", compression="dxt5")
    assert prm["UsageHint"] == "parameter" and prm.get("Compression") == "dxt5"

    # config.chump round-trip (sample bumper library)
    from trainz_studio.io.chump import chump_to_text, read_chump, text_to_chump, write_chump

    sample = (
        Path(__file__).resolve().parents[1]
        / "backups"
        / "26-09-30"
        / "kuid 1125787 100056 MSTN KIHA _ ______40"
        / "config.chump"
    )
    if sample.is_file():
        raw = sample.read_bytes()
        ch = read_chump(sample)
        assert any(t.name == "kuid" for t in ch.root)
        text = chump_to_text(ch)
        assert "<kuid:1125787:100056>" in text
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "config.chump"
            write_chump(out, text_to_chump(text))
            # ponytail: wire may retype INT↔FLOAT (width/height); semantic round-trip is enough
            back = chump_to_text(read_chump(out))
            assert "<kuid:1125787:100056>" in back

    from trainz_studio.io.chump import encode_chump

    packed = encode_chump(text_to_chump('kuid  <kuid:1:2>\nkind  "traincar"\n'))
    shown = chump_to_text(read_chump(packed))
    assert "<kuid:1:2>" in shown and "traincar" in shown
    assert packed[:4] == b"ACS$"

    # TRS22 tzarc v2 (zlib chunks) — small backup sample
    from trainz_studio.io.tzarc import extract_tzarc, list_tzarc, open_tzarc

    tz = (
        Path(__file__).resolve().parents[1]
        / "backups"
        / "26-10-06"
        / "kuid 1144998 100255.tzarc"
    )
    if tz.is_file():
        idx = open_tzarc(tz)
        assert idx.version == 2
        names = list_tzarc(tz)
        assert "config.chump" in names
        with tempfile.TemporaryDirectory() as td:
            written = extract_tzarc(tz, Path(td))
            assert any(p.name == "config.chump" for p in written)
            chump = Path(td) / "config.chump"
            assert chump.read_bytes()[:4] == b"ACS$"

    # CDP pack / extract / size bands (LZSS level-0 store)
    from trainz_studio.io.cdp import (
        SIZE_HARD_MAX,
        SIZE_OK_MAX,
        SIZE_SOFT_MAX,
        browse_cdp,
        classify_size,
        extract_cdp,
        open_cdp,
        pack_asset_folders,
        remove_file,
    )
    from trainz_studio.io.cdp_lzss import _self_check, decode_binary_blob, make_binary_blob

    assert SIZE_OK_MAX == 500 * 1024 * 1024
    assert SIZE_SOFT_MAX == 800 * 1024 * 1024
    assert SIZE_HARD_MAX == 1024 * 1024 * 1024
    assert classify_size(100).band == "ok"
    assert classify_size(SIZE_OK_MAX + 1).band == "soft"
    assert classify_size(SIZE_SOFT_MAX + 1).band == "warn"
    assert classify_size(SIZE_HARD_MAX + 1).band == "refuse"
    blob = make_binary_blob(b"trainz-cdp")
    assert decode_binary_blob(blob) == b"trainz-cdp"
    _self_check()  # mode-0 bitstream u32 mask wrap + text decode
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        asset = root / "asset"
        asset.mkdir()
        (asset / "config.txt").write_text(
            'username  "PackTest"\nkind  "scenery"\nkuid  <kuid:9:99>\n',
            encoding="utf-8",
        )
        (asset / "data.bin").write_bytes(b"\x01\x02\x03\x04" * 8)
        cdp_path, verdict = pack_asset_folders([asset], root / "t.cdp")
        assert verdict.band == "ok"
        assert cdp_path.read_bytes()[:4] == b"ACS$"
        idx = open_cdp(cdp_path)
        assert len(idx.assets) == 1 and idx.assets[0].kuid == "<kuid:9:99>"
        out_dir = root / "extracted"
        written = extract_cdp(cdp_path, out_dir)
        assert any(p.name == "data.bin" for p in written)
        data = next(p for p in written if p.name == "data.bin")
        assert data.read_bytes() == b"\x01\x02\x03\x04" * 8
        from trainz_studio.io.cdp import load_cdp

        ch = load_cdp(cdp_path)
        nodes = browse_cdp(ch)
        assert nodes and remove_file(ch, nodes[0].kuid, "data.bin")


def format_issues(r) -> str:
    return "; ".join(f"{i.level}:{i.message}" for i in r.issues)


def test_loop_qc_and_fix() -> None:
    import tempfile
    from pathlib import Path

    import numpy as np

    from trainz_studio.audio.decode import load_mono_pcm16
    from trainz_studio.audio.export_wav import write_mono_pcm16
    from trainz_studio.audio.ffmpeg_cfg import ffmpeg_status, set_ffmpeg_path, get_ffmpeg_path
    from trainz_studio.audio.loop_fix import fix_loop, seamless_loop
    from trainz_studio.audio.loop_qc import analyze_mono, worst_severity
    from trainz_studio.ui.sounds.track_sim import (
        PHASE_A,
        PHASE_SEAM,
        TrackPair,
        next_phase_after_a_done,
    )

    sr = 44100
    t = np.linspace(0, 2.0 * np.pi * 40, sr * 2, endpoint=False)
    base = (np.sin(t) * 8000).astype(np.float64)
    base[: sr // 2] *= 2.2
    base[-(sr // 2) :] *= 0.35
    mono = np.clip(base, -32768, 32767).astype(np.int16)
    findings = analyze_mono(mono, sr, key="1.wav", treat_as="steady")
    kinds = {f.kind for f in findings}
    assert "uneven_loop" in kinds or "click" in kinds or worst_severity(findings) != "ok"

    xf = int(0.06 * sr)
    body = np.concatenate([mono.astype(np.float64), mono[:xf].astype(np.float64)])
    out = seamless_loop(body, xf)
    assert out.size == body.size - xf

    fixed, report = fix_loop(mono, sr)
    assert fixed.size > 0
    assert "steps" in report

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.wav"
        write_mono_pcm16(p, fixed, sr)
        loaded, lsr, _ = load_mono_pcm16(p)
        assert lsr == sr
        assert loaded.size == fixed.size

    pair = TrackPair(0, 1)
    assert pair.valid(2)
    assert not TrackPair(0, 0).valid(2)
    assert not TrackPair(0, 1).valid(1)
    assert next_phase_after_a_done(PHASE_A) == PHASE_SEAM
    assert "ffmpeg" in ffmpeg_status().lower()
    # don't clobber user setting permanently — only read
    _ = get_ffmpeg_path()
    _ = set_ffmpeg_path  # imported for coverage of module


def test_mesh_studio_nav_flanks_home() -> None:
    """Meshes Editor sits left of Home, Attachs Editor sits right. Equal button widths."""
    from PySide6.QtWidgets import QApplication

    from trainz_studio.ui.app import BottomNav

    app = QApplication.instance() or QApplication([])
    nav = BottomNav(None)
    assert nav._pages == ("preview", "meshes", "attachs", "settings")
    assert nav._left_btns == [nav.preview_btn, nav.meshes_btn]
    assert nav._right_btns == [nav.attachs_btn, nav.settings_btn]
    assert nav.meshes_btn.text() == "Meshes Editor"
    assert nav.attachs_btn.text() == "Attachs Editor"
    w = nav.meshes_btn.minimumWidth()
    assert w == nav.attachs_btn.minimumWidth() == nav.preview_btn.minimumWidth() == nav.settings_btn.minimumWidth()
    assert w >= 108
    nav.deleteLater()
    del app


def main() -> int:
    test_obj_parse_roundtrip()
    test_obj_parse_with_uv()
    test_attachment_axes()
    test_aabb_wire_lines()
    test_fps_hud_text()
    test_fps_hud_top_right()
    test_mesh_key_hidden()
    test_attachment_owner_and_hidden()
    test_highlight_pick()
    test_mesh_preview_argv()
    test_draw_batch_vbo_slots()
    test_flatten_part_indexed()
    test_attachment_gizmo_glow()
    test_glow_billboard_mesh()
    test_sun_dir_yup()
    test_fly_approach_dist_stable()
    test_orbit_yaw_follows_drag()
    test_arrow_walk_is_ground_forward()
    test_screen_delta_to_world()
    test_screen_delta_along_axis()
    test_pick_translate_handle()
    test_attachment_gizmo_move_mode()
    test_env_presets()
    test_hdri_assets()
    test_hdri_sun_dir_roundtrip()
    test_auto_exposure()
    test_celestial_sphere_mesh()
    test_fade_stack_no_opacity()
    test_boot_prewarms_gl_before_show()
    test_boot_overlay_log_and_easing_bar()
    test_hub_reveal_overlay_plays()
    test_assets_kuid_normalize()
    test_mat_names()
    test_frost_clears_on_set_dark()
    test_frost_shadow_room()
    test_frost_motion_lod()
    test_old_meta_cache_is_a_hit()
    test_qml_shell_loads()
    test_trainz_install_scan()
    test_qml_sounds_loads()
    test_qml_engine_loads()
    test_qml_assets_loads()
    test_damped_scroll_passes_when_table_cant_scroll()
    test_island_light_positions()
    test_multi_mesh_keys()
    test_zup_vectorized()
    test_theme_no_qwidget_blanket()
    test_theme_palette_sets_base_both_modes()
    test_theme_warm_cache()
    test_material_icons_font()
    test_mode_pie_glass_reveal()
    test_home_glass_hub()
    test_hover_bubble_row_slide()
    test_pbr_hud_not_squeezed()
    test_float_chrome_bookends()
    test_float_title_bar_chrome()
    test_animate_window_quit()
    test_crash_dialog_quit_flag()
    test_status_toast_save_detect()
    test_smooth_scroll_filter()
    test_scroll_wheel_reaches_child()
    test_editor_wheel_scrolls_not_combo()
    test_lamp_discover_and_pack()
    test_cuda_texel_chunk_size()
    test_bake_lamps_tiny()
    test_bake_contact_ao_cross_mesh()
    test_attachment_from_dump_xml()
    test_undo_stack_unlimited()
    test_project_and_crash_backup()
    test_tzmf_material_patch()
    test_trainzmesh_attachments()
    test_tiled_uv_chunk_is_kept()
    test_trainzmesh_decode()
    test_texture_fixtures()
    test_texcache_roundtrip()
    test_texture_stem()
    test_material_family()
    test_probe_image_and_pbr_sort()
    test_stems_match_family()
    test_image_prep_and_ve39()
    test_tex_map_edit_channels_and_bak()
    test_param_map_and_bake_denoise()
    test_ve_rules_pack()
    test_i18n_catalogs_and_fonts()
    test_merge_lamp_packs()
    test_resolve_primary()
    test_kin_scan()
    test_im_fast_preview_geom()
    test_im_document_add_remove()
    test_named_two_sided_does_not_touch_other_parts()
    test_mesh_meta_two_sided()
    test_code_edit_trainzconfig_spans()
    test_editor_find_config_and_workspace()
    test_mesh_studio_nav_flanks_home()
    from trainz_studio.util.hw import (
        bake_workers,
        cpu_count,
        decode_workers,
        hub_reveal_ms,
        is_low_end,
        prefer_instant_panels,
        prefer_light_boot_frost,
        prefer_short_hub_motion,
        summary,
    )
    from trainz_studio.util.preload import (
        _HUB_MODULES,
        hub_modules_ready,
        join_hub_module_preload,
        start_hub_module_preload,
    )

    assert cpu_count() >= 1
    assert 1 <= decode_workers() <= 24
    assert 1 <= bake_workers() <= 16
    assert "cpus=" in summary() and "low_end=" in summary()
    assert isinstance(is_low_end(), bool)
    assert prefer_instant_panels() == is_low_end()
    assert prefer_short_hub_motion() == is_low_end()
    assert prefer_light_boot_frost() == is_low_end()
    assert hub_reveal_ms(warm=True) >= 0
    if is_low_end():
        assert hub_reveal_ms(warm=True) == 0
    else:
        assert 200 <= hub_reveal_ms(warm=True) <= 400
    assert "trainz_studio.ui.trainzutil_host" in _HUB_MODULES
    start_hub_module_preload()
    assert join_hub_module_preload(timeout=30.0)
    assert hub_modules_ready()
    test_lerp_pill_rect()
    test_rounded_table_rows_install()
    test_short_glass_tip()
    test_glass_tip_wraps_long_text()
    test_qt_tooltip_uses_glass_bubble()
    test_button_hover_chrome_install()
    test_ease_out_cubic()
    test_loop_qc_and_fix()
    # FBX: bundled Assimp DLL preferred; CLI fallback
    from trainz_studio.io.assimp_dll import find_assimp_dll
    from trainz_studio.io.loaders import find_assimp

    if find_assimp_dll() or find_assimp():
        test_fbx_bumper()
    else:
        print("trainz_studio check: skip FBX (no Assimp DLL/CLI)")
    print("trainz_studio check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
