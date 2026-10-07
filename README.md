# MSTN Trainz Studio

HOME hub for **Mesh Studio** (FBX / `.trainzmesh` / `.im` preview), **Sounds Studio** (loop/QC/Fix), **Engine Tuner** (enginespec throttle curves + sim), and **Assets Tools** (native CDP/TZarc list, `.texture.txt` / `.lm.txt` writers, KUID hash — no external exe launch). Apple-style chrome, per-part PBR, lamps, honest write capabilities (below).

**Agent / chat continuation:** read [`HANDOFF.md`](HANDOFF.md) first. Cursor skill: `mstn-mesh-studio`.  
**Pre-rename backup:** `backups/26-10-05/mesh_studio-pre-trainz-studio/`

## Capability matrix

| What | Status |
|------|--------|
| Preview `.trainzmesh` / FBX / `.im` | **Yes** |
| Write mesh meta `two-sided` (Editor → Meshes · Double Sided) | **Yes** → `{mesh}.txt` |
| Write `.im` attachments (`ImDocument` Add/XYZ/Save + `.im.bak`) | **Yes** — Editor → Attachments |
| Write `.trainzmesh` binary (materials + a.*) | **Yes** — Editor Save in Studio (+ `.bak` once); no external MeshEditor |
| FBX attachment write | **No** — preview-only |
| Emissive boost / sun lighting | **Preview only** (does not write mesh) |
| Bake lamps → albedo + parameter | **Yes** — path-trace (+ CUDA if CuPy), sidecars in `baked_lamps/` |

## Run

**Windows (no console)**

```bat
trainz_studio\start.bat
trainz_studio\start.bat trainz_studio\fixtures\body.trainzmesh
```

Or double-click `start.vbs` for a silent launch. Use `start_debug.bat` when you need a console for traceback logs.

**macOS / Linux**

```bash
trainz_studio/start.sh
trainz_studio/start.sh trainz_studio/fixtures/body.trainzmesh
```

Needs **Assimp** for FBX: bundled DLL under `vendor/assimp/` (preferred), or Assimp CLI on `PATH`. `.trainzmesh` uses `lib/trainzmesh_viewer`.

## Texture view (per-part — not whole-mesh paint)

Selecting a texture **does not** slap one TGA onto every UV of the car.

1. **Texture view** dropdown: **All materials** | **Selected only**
2. Materials tree groups `*_albedo` / `*_normal` / `*_parameter` under one family
3. Select the **group** → all map stems · select a **child** → that map role only
4. **All materials** — every part draws its own albedo/normal/parameter
5. **Selected only** — only parts whose refs match selected stem(s) are drawn; others are hidden

**PBR mode** (3D HUD only): Lit | Albedo | Normal | Rough | Metal | AO

**UV / textures:** `.trainzmesh` loader undoes the parser’s `(u, 1-v)` → Trainz/D3D raw V (V=0 = top). Bitmaps upload **without** flip (matches OpenGL+Pillow). View/Settings → Flip texture V only if a map still looks inverted.

Right-click a texture row:

- Preview matching parts only
- Preview as Self-Illum (onetex)
- Open in Editor
- Force as albedo on selection (explicit; still stem-scoped, never whole mesh)
- Reveal file

## UI

- Soft glass chrome (semi-transparent panels) · logo floats on sidebar (no black plate)
- Sidebar (min 340): stats + logo · Scene / Mat / **Lamps** / Motion / Lights
- Center: welcome / full-size 3D (+ Editor dock) / Settings (no letterbox)
- Bottom floating pill: **Preview** | **Editor** | **Settings** + theme toggle
- **Editor** keeps 3D visible and opens a dock: Attachments · Meshes · Save (Studio-owned write)
- Theme switch applies on `QApplication` (does **not** freeze the GL viewer)
- Drop a mesh → determinate progress overlay (stage % + processEvents)
- Boot uses in-window glass overlay (Starting → Building → Ready) — no separate splash window; title bar / frost drag stay usable while warming; MeshView is created before first show so Windows does not recreate the HWND

## Layout (EXE-ready later — do not freeze yet)

```
trainz_studio/
  start.bat / start.vbs / start_debug.bat / start.sh
  __main__.py          # python -m trainz_studio → ui.app.main
  check.py             # smoke tests
  ui/                  # app, theme, editor, motion
  render/              # view3d, env, hdri
  lamps/               # discover + bake
  io/                  # loaders, scene, texture, texcache, anim, assimp
  util/                # hw threads
  scripts/             # fetch_hdris
  assets/  fixtures/  vendor/
  lib/                 # engine_tuner · im_editor · trainzmesh_viewer
  pack/                # PyInstaller — build.bat → dist/MSTN_TrainzStudio/
```

Ship: `pack\build.bat` → `trainz_studio\dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe` (see `pack/README.md`).

## Lamps (preview)

Sidebar **Lamps** tab:

- Auto-detect `m.onetex` / light-named stems on mesh open
- Omnidirectional / Spot / Wide — brightness, color, range, cone
- Self-glow on lamp surfaces + point/spot falloff onto the rest of the mesh
- **Moonlight** when Sun is off (cool fill so cabin lights read)
- Add from Mat selection · Rescan · gizmos · max 8 lamps

## Lighting

- **Array** (default): four directional lights (L/R/F/B) + soft top fill
- **Sun mode** (Lights tab): one directional sun (azimuth / elevation / intensity) + soft fill + yellow direction gizmo
- **Emissive boost** (Lights tab): 0–2 preview scale on parameter R (default 0.15) — does not write files
- `m.onetex` / materials without a parameter map get mild self-illumination

## Animations

On mesh open, scans for `*.kin`. Drop a `.kin` onto the window to append (`peek_kin`). Play/scrub only — bone transforms are **not** invented.

## Controls

- LMB drag: orbit (damped); **with `a.*` selected**: LMB moves attach · **Shift**=fine · **Alt+LMB**=orbit
- Arrows: walk forward / back / left / right
- MMB drag · PgUp / PgDn: height
- Wheel: dolly · **Ctrl+Wheel**: FOV lens (mm) · **Ctrl+Shift+Wheel**: fine FOV · **R** / Lights → Reset camera
- Bottom nav: click or **drag** across Preview / Editor / Settings (live)
- Click attachment: fly-to that point (Scene list read-only; hidden while Editor dock is open)
- **Editor** page: Attachments · Meshes · Save / Save As (`.im` / `.trainzmesh` in Studio)

## Formats

| Ext | Support |
|-----|---------|
| `.fbx` | mesh + UVs + `a.*` via assimp + sibling `.kin` list (attach write: no) |
| `.trainzmesh` | tzMF decode + Editor Meshes/Attachments **Save** (`io/tzmf_edit.py`) + `.kin` |
| `.im` | ATCH preview + Editor Attachments edit/save via `lib/im_editor` |
| `.kin` | JIRF peek: frame count + bone names; transforms not decoded yet |
| `.texture.txt` | validate + per-part filter (sidebar / family) |

## Self-check

```bash
cd c:/trs22
python -m trainz_studio.check
# or:
trainz_studio/.venv/Scripts/python.exe -m trainz_studio.check
```
