# MSTN Trainz Studio — continuation handoff

**Last updated:** 2026-10-08 (Asia/Bangkok) — QML right docks for Texture & Mesh

### QML Assets Tools (2026-10-08)

| Piece | Role |
|--------|------|
| `ui/qml/AssetsPage.qml` | Stage gradient, raised nav (Assets or Texture & Mesh Lods), sidebar + dock wells |
| `ui/qml/AssetsSide.qml` | Logo, page title, action buttons, CDP icon row. Packages queue stays a widget in the well |
| `ui/qml/AssetsViewer.qml` | Packages Viewer/Editor dock chrome. Preview stack stays a widget in the well |
| `ui/qml/AssetsDock.qml` | Mesh Lods, Texture Params, Texture Editor, Texture Denoiser. Maps canvas and Packages preview stay widgets in the well |
| `ui/assets/bridge.py` | Nav, actions, dock width, and the form the right dock paints |
| Buttons | Same `RaiseButton` / `GlassPlate` as Engine Tuner |
| Paint | Entering Texture & Mesh froze the page stack for the old dock lerp. QML skips that lerp and turns painting back on |
| Widget nav | Hidden while QML is up — one bottom bar |

### QML Engine Tuner (2026-10-08)

| Piece | Role |
|--------|------|
| `ui/qml/EnginePage.qml` | Sunk content well + raised nav (Tuner · Simulation · Parameters · Home · Auto Tune) |
| `EngineTunerHost._mount_qml` | Sidebar, throttle/sim/parameter editors, and Auto Tune drawer stay widgets inside the well |
| `ui/qml/EngineAuto.qml` | Right Auto Tune dock in QML. Hidden widget panel still runs Preview / Apply |
| Buttons | `RaiseButton.qml` is raised glass. Fields and tables use `SunkField.qml` (sunk). Keep that for every QML control |
| Warm | Sounds, Engine Tuner, Assets Tools, and Texture/Mesh are built and painted once before the boot cover drops |
| `ui/qml/GlassPlate.qml` | Soft multi-ring floor shadow + inner lip on the glass (Home, Sounds, title) |
| Fallback | Widget nav stays if the QML page fails to load |

### QML shell phase 1 (2026-10-08)

Studios (Mesh / Sounds / Engine / Assets / TexMesh) stay Qt Widgets. Only the hub home and the floating menu bar are Qt Quick so later pages can move one at a time.

| Piece | Role |
|--------|------|
| `ui/qml/HomePage.qml` | Same hub: logo, 5 studio cards, drop zone |
| `ui/qml/TitleBar.qml` + `MenuDrop.qml` | Traffic lights + File / Edit / View / Tools / Theme / Lang |
| `ui/qml_host.py` | Bridge. Menu rows still `QAction.trigger()` — shortcuts and logic stay in `app.py` |
| Fallback | If QML fails to load, widget `HomePage` / `FloatTitleBar` come back |
| Paint | Qt Quick uses the **software** scene graph so it stays visible beside the mesh `QOpenGLWidget` (shared desktop GL was a black HOME) |

Next phases: Engine Tuner, then Assets, Mesh Studio last. Layout stays as close as the widget version.

### QML Sounds Studio (2026-10-08)

| Piece | Role |
|--------|------|
| `ui/qml/SoundsPage.qml` | Clip list · QC · Track→Track · transport · Home |
| `SoundsStudioHost._try_qml` | Same import / play / fix / save logic; waveform stays a widget in the center well |
| Fallback | Widget layout if the QML page fails to load |

### Silk motion pipeline (2026-10-08)

Keep cinema glass look at rest; mid-slide paint must not re-run 14 soft-shadow rings every frame.

| Piece | Role |
|--------|------|
| `FrostGlassFrame.begin/end_motion_lod` | Bake full glass once → blit cache during dock/sidebar slide → Full glass on finish |
| `bake_frost_plate` | Offscreen full plate for lod |
| `_set_side_panel` / `_set_editor_dock` | `begin_motion_lod` before `animate_geometry`; `end_motion_lod` in on_done; no mid-slide frost re-grab |
| `animate_geometry` on_tick | Default **16ms** (~60Hz); low-end **32ms** (was 0 on normal PCs → layout storm) |
| `apple_pop_pill` | No-op while `_slide_anim` in flight (don't fight geometry) |
| Hub cover | Already one downscaled pixmap blit + opacity — no shadow rings |

### PBR HUD (Lit…AO) — un-squeeze (2026-10-08)

| Piece | Role |
|--------|------|
| Root cause | `paint_glass_chip` needs top5/bot12 shadow air; HUD was ~38px → plate ~21px (flat strip) |
| `PBR_HUD_H` / `PBR_HUD_BTN_H` | **56** / **34** (same air as bake bar) |
| Margins | `14,8,14,14` + spacing 4 — labels sit inside the glass plate |
| Width | min **420** (was 320 — crushed six labels) |
| Translucent | `WA_TranslucentBackground` so capsule shadow paints clean |

### Texture & Mesh Lods tools — nav + full-height editor docks (2026-10-08)

| Piece | Role |
|--------|------|
| Suite name | **Texture & Mesh Lods tools** (Home card · View menu · sidebar brand) |
| Bottom nav | **Mesh Lods · Texture Params** \| Home \| **Texture Editor · Texture Denoiser** (two-line; tall 88 + Home 48 + gap 22) |
| Other bars | Engine / Assets / Sounds stay height **72** · Home gap **16**; Mesh Studio shares tall Home treatment |
| Page ids | unchanged (`meshops` / `texture` / `parameter` / `denoise`) — labels + order only |
| Texture Editor / Texture Denoiser | Controls leave the mid page → full-height right dock (`editorDock`, Mesh Editor frost inset) |
| Right dock stack | 0 Texture Params · 1 Mesh Lods · 2 Texture Editor · 3 Texture Denoiser — open on every texmesh page |

### Boot — move during frost + no close/reopen on mesh GL warm (2026-10-08)

| Piece | Role |
|--------|------|
| Root cause (flash) | First `QOpenGLWidget` parented into an already-shown Win32 HWND recreates that platform window → looks like the app closed and reopened during warm |
| Fix (flash) | `MainWindow.prewarm_mesh_gl()` before `showMaximized()` — Mesh chrome + `MeshView` while hidden; Finder preview GL still idle after overlay (shares context) |
| Root cause (no drag) | Overlay card children ate clicks; Win32 `HTCAPTION` no-ops on frameless (broke title-bar drag that used `startSystemMove`) |
| Fix (drag) | `begin_frameless_move` prefers `startSystemMove`, Win32 `SC_MOVE` fallback; title label + overlay card mouse-transparent; title bar above frost |
| Root cause (not max) | Early HWND from GL prewarm / failed drag left window restored after frost |
| Fix (max) | `setWindowState(Maximized)` on first show + `showMaximized()` again after `_hide_overlay` |
| Boot order | `go_home` → `prewarm_mesh_gl` → `showMaximized` → dim cover (no frost) → Mesh warm → hide → idle Sounds/Engine/Assets → remmaximize |

### Packages Viewer — full-height right dock (2026-10-08)

| Piece | Role |
|--------|------|
| Before | Viewer lived inside Packages mid stack → squeezed above bottom nav |
| After | `viewer_panel` mounts on `AssetsStudioHost._right_dock` (index 4) — sibling of left sidebar, like Mesh Editor |
| Padding | `FROST_CONTENT_MARGINS` 28/24/28/30 · spacing 10 (`editorDock`) |
| Width | min **420** · default **560** · max **920**; expand grows dock / hides Finder |
| Config / KUID | right dock closes; texmesh docks stay indices 0–3 |

### Packages Finder — Edited mark + config Save (2026-10-08)

| Bug | Fix |
|-----|-----|
| Save on CDP `config.txt` was a stub → reopen looked “reset” | `_save_preview_text` → `replace_asset_config` |
| Temp bak only | `save_cdp` writes `*.cdp.bak` then deletes on success; Clear / Extract discards leftovers |
| Finder showed type badge only (T/F/I) — no edit state | orange **E** badge on edited file / parent folder / asset until **Save CDP…** |
| Track | `_dirty_paths` + `_dirty_assets` (cleared on Save / Clear / open CDP) |
| Engine Tuner button on every txt | was substring `"enginespec"` + cwd fallback → traincar kuid-table false positive; now only preview `config.txt` + parsed `looks_like_enginespec` |

### Packages Finder — descenders + selection bubble (2026-10-07)

| Bug | Fix |
|-----|-----|
| Flat Win `Highlight` under opaque name cell | translucent cell + AccentPill bubble in `table_chrome` |
| `g/y/p` clipped | **not** taller rows — (1) `::item` vertical pad was stealing cell height → `padding: 0 4px` (2) global `* { font-size: 13px }` overrode label fonts → explicit 12/11px + `ensurePolished` then `setFixedHeight(ascent+descent+2)` |
| Size `33.8…` | Size column **108** (was 88) |
| `_FINDER_ROW_H` | **48** again (64 was a wrong guess) |

### Texture right dock — padding + width (2026-10-07)

| Piece | Role |
|--------|------|
| `FROST_CONTENT_MARGINS` on Texture / Mesh Ops props | 28/24/28/30 — was 16px (content sat on glass edge) |
| Texture dock default | **1040** (max **1100**) — Mesh Ops stays 700 / 920 |
| `_dock_width_budget` | Texture always opens near-max; resize if already open |

### Parameter + Bake Denoise (2026-10-07)

| Piece | Role |
|--------|------|
| Bottom nav (texmesh) | see **Texture & Mesh Lods tools** section above (was Texture · Parameter · Denoise · Mesh Ops) |
| `io/param_map_edit.py` | m.pbrmetal RGBA ops · fill/offset/scale/B·C/mean/invert/overlay/paint |
| `ui/assets/param_page.py` | Texture Editor canvas · `tools_panel` mounts in right dock · Save overwrite (+ `.bak` once) |
| `io/bake_denoise.py` | OIDN RTLightmap → OpenCV NLM (+ guided/bilateral) · black UV lock |
| `ui/assets/denoise_page.py` | Texture Denoiser preview · `tools_panel` in right dock · Save overwrite |
| `vendor/oidn/bin` | Intel Open Image Denoise 2.5.1 Windows binaries (~75 MB) |
| Dep | `opencv-contrib-python-headless` (ximgproc; bilateral fallback if missing) |
| Maps tab | Mild Pillow denoise unchanged (albedo/normal polish) |

### Frost backdrop shadows — wider fade (2026-10-07)

Qt clips paint outside the widget, so 3-step shadow rings + tight insets cut the halo into a hard edge (sidebar bottom, title/nav capsules looked stepped/pixel-y).

| Piece | Role |
|--------|------|
| `ui/frost.py` `paint_soft_shadow` | ~12–14 thin rings, ease-out alpha, clamped inside widget |
| `FROST_CONTENT_MARGINS` | `(28, 24, 28, 30)` — Mesh/Editor/Assets/Engine side panels |
| Plate inset | Panels ~14/11/16 · chips ~8/5/12 (was ~4/3/6) |
| `TITLE_BAR_H` / `FLOAT_NAV_HEIGHT` | 60 / 72 — room for capsule bottom fade |

### Mesh Studio nav + Editor fields (2026-10-07)

Bottom capsule is symmetric: **Preview · Meshes Editor** | Home | **Attachs Editor · Settings**. The right dock no longer has an Attachments/Meshes tab strip — the nav picks the page. Legacy page id `editor` still opens whichever tab is already showing (old projects).

Meshes fields share one height (36) and one value column. Texture browse is a folder icon; `$pbr-env*` is a lock; color pick is a palette glyph on the swatch. Material / emissive / specular: R G B A are labels beside the box; the input is the 0–255 number only. Editor inputs are inset wells (dark top lip, light bottom edge) so the narrow color boxes read against the glass.

Attachs Location / Rotation are one axis per row, same width as Name. A tzMF byte hit is kept only when the quaternion is near unit length and the position is inside 10 km — a finite `10000` ghost no longer fills Name when the attachment list is empty.

### Double Sided — preview until Save (2026-10-07)

Checkbox used to emit a material edit, which rewrote tzMF and called `set_scene` (hang + camera home). The click flips cull on that material and redraws the viewport immediately (camera stays). It does **not** write `{mesh}.txt` until Editor **Save** / **Save As**.

Editor → Meshes: left Scene list rows have checkboxes. **Select all** + **Apply Double Sided (N)** turns cull off on the ticked names in the current preview (no camera reset). Those names are queued and written into `{mesh}.txt` only when Save is pressed.

### Editor dock chrome (2026-10-07)

Right Editor uses the same frost inset as the left sidebar (`FROST_CONTENT_MARGINS` 28/24/28/30). `editorTabStack` stays transparent so it does not paint a square black plate over the rounded glass. Width **480**.

### tzMF select showed the wrong piece (2026-10-07)

Selecting a mesh row outlined the **next** geometry. Materials were zipped by list index, but unnamed chunks sit between named ones, so `mats[i]` is not submesh `i`. Pair by chunk tail (`material.type_off == sub.tail_off`, gap 0). `body.trainzmesh`: `body_front` is the 14760-vert shell, not the 848-vert gap chunk.

Also: `_sample_ok` rejected tiled UVs outside ±32 and dropped that chunk (int V≈±52). Limit is now |UV| < 1e5.

### Faster boot + HOME fade (2026-10-08)

| Piece | Role |
|--------|------|
| Boot cover | **No frost grab** — dim overlay card only (grab+blur was a big first-paint tax) |
| Boot warm | Mesh chrome only under cover; Sounds/Engine/Assets via `_idle_warm_secondary_hubs` after HOME |
| `util/preload.py` | Background import of Editor/Sounds/Engine/Assets while MainWindow builds |
| Mesh GL | `prewarm_mesh_gl` **before** first show (HWND flash fix) |
| Hub transition | Soft fade + tiny popup lift (`HubRevealOverlay`) — no directional morph / caption |
| `hub_reveal_ms` | ~260–300ms (0 = skip on low-end) |
| View3D | Cam timer sleeps when hidden; **16ms while visible** (33ms idle was steppy) |
| Panel slide | motion_lod + `animate_geometry` on_tick **16ms** (32ms = low-end); see Silk section above |
| HOME cards | Instant lift on low-end (no per-card QVariantAnimation) |

### Faster boot + smoother UI (2026-10-07) — superseded above for boot/hub

| Piece | Role |
|--------|------|
| Cut | No 2nd theme/logo warm · throttle `processEvents` · one i18n snapshot |
| Assets GL | `warm_fast_preview_infra` idle after overlay hide (shares MeshView context) |

### Viewport arrow walk (2026-10-07)

| Key | Move |
|-----|------|
| ↑ ↓ | Forward / back along camera look, on the XY ground |
| ← → | Strafe |
| PgUp / PgDn | Elevation (±Z) |

World is Z-up. The old flatten zeroed **Y**, so Up slid in XZ. `horizontal_walk_dirs` zeros **Z**.

### Mesh pick outline (2026-10-07)

| Piece | Role |
|--------|------|
| Editor **Meshes** row | Orange triangle-edge frame on that part (no inflated shell — that drew the orange rings) |
| **Meshes in scene** row | Whole file by `mesh_key` (multi-select). Click only — refill does not fly the camera |
| Mat deselect | Restores the last mesh outline |

### Texture / Mesh right dock scroll (2026-10-07)

| Piece | Role |
|--------|------|
| `DampedScrollFilter` | Wheel on a child (not only the viewport) moves that scroll area |
| Mesh Ops props | Same `sideScroll` as Texture — fields were clipped with no bar |
| Nested scroll | Inner area that can still move keeps the wheel (code preview) |

### Low-spec UI / F3 / Preview dock (2026-10-07)

| Piece | Role |
|--------|------|
| Boot | Mesh under cover; Sounds/Engine/Assets idle after HOME (`_idle_warm_secondary_hubs`) — modules preloaded |
| `util/hw.py` | `is_low_end` / `prefer_instant_panels` / `prefer_short_hub_motion` / `prefer_light_boot_frost` / `hub_reveal_ms` (cpus≤4 or RAM≤8GiB; override `TRAINZ_STUDIO_LOW_END`) |
| F3 | Handled in `eventFilter` + `keyPressEvent` (hidden menuBar QAction was flaky); ShortcutOverride avoids double-toggle |
| FPS HUD | Glass chip, top-**right** of the clear viewport. Editor dock slides it left (`fps_hud_top_right`). F3 does **not** force idle GL redraws (that hitch was `update()` every 16ms). Chip is not a child of the GL widget. |
| Preview / Settings | Editor dock closes **instant** (`animated=False`) — slide-out left dock covering Preview on slow PCs |
| Dock width | Cap so ≥40% clear viewport; side panel `width//4` (was `//3`) |
| Anim | `animate_geometry` throttles `on_tick`; low-end skips panel slides + hub morph |

### Double Sided checkbox (2026-10-07)

| Piece | Role |
|--------|------|
| Default | `two_sided=False` (was always-on for cabin preview) |
| Source | Sibling `{mesh}.txt` `materials { name { two-sided 0\|1 } }` only |
| Write | Editor Save / Save As — toggle and Apply are preview only |
| No meta | Checkbox off · backface cull on (test: KIHA int `int.trainzmesh`) |
| UI | Editor Meshes · Double Sided + Texture two-sided row |

### Overlay toast bubble + footer status log (2026-10-08)

| Piece | Role |
|--------|------|
| `ui/status_toast.py` | `ToastHost` · `GlassToastBubble` · `StudioStatusBar` · status-log dialog |
| Bubble | Short wide chip · hangs under title bar · **center** when no topbar · slide-down + fade |
| Chrome | **Never** `#welcomeTitle` (theme 34px) — `#toastTitle` 12 / `#toastDetail` 10 · mark 18² · ≤2 lines · elide |
| Progress text | Title + `%` only — `_toast_lines` / `_short_progress_detail` strip `%` + newlines |
| Save | ✓ green · 5s · status `Saved`/`Wrote`/`Exported` (not Autosave/fail) |
| Drop | ↓ orange · shows file names (`hub.drop` from `_handle_dropped_paths`) |
| Progress | … blue · bar + `%` · sticky · load/bake · **finish** on 100% / plain status / hide overlay |
| Footer left | Clickable `#statusLogMsg` → frost **Status log** (ring buffer ~400) |

### HOME — Texture / Mesh Tools card (2026-10-07)

| Piece | Role |
|--------|------|
| Home cards | 5 in one row — Mesh · Sounds · Engine · **Assets** · **Texture / Mesh** |
| Assets Tools | Packages · Config · KUID only (`set_suite("assets")`) |
| Texture / Mesh | Texture · Parameter · Denoise · Mesh Ops (`set_suite("texmesh")`) — same `AssetsStudioHost` |
| Bottom nav | Suite-specific `AssetsPageNav` (no combined Texture/Mesh tab on Assets) |
| View menu | Assets Tools · Texture / Mesh Tools |

### Texture Maps Viewer / Editor (2026-10-07)

| Piece | Role |
|--------|------|
| Right dock | Wider on Texture (`560–920`, default `700`) |
| Side tabs | **Params** · **Maps** · **Resize** |
| `ui/assets/tex_map_panel.py` | Maps UI: hero preview stage · colored A/N/P + R/G/B/A chips · Adjust card · dbl-click solo · Expand |
| `io/tex_map_edit.py` | Channel view + Denoise + undo + Trainz save (`.bak` once) |
| Scope | Image edit only — `.texture.txt` still Params / Save .texture.txt |

### VE Rules pack — mesh / texture / config (2026-10-07)

| Piece | Role |
|--------|------|
| `io/ve_rules.py` | **App-wide** scanner (`scan_paths` / `scan_asset_folder` / VE102) |
| `ui/ve_dialog.py` | Shared report dialog for every studio |
| **Tools** menu | Ctrl+Shift+V current · Ctrl+Shift+R folder · fix · last report |
| Status bar **VE** | Click → last report (`VE OK` / `VE!`) |
| Auto-scan | Mesh open · Engine config · Sounds import · folder drop |
| Assets sidebars | Rules scan/fix still there (same engine) |
| Out of scope | Script compile (197/220), DLC featured, CM dependency DB |

**Ship:** v0.3.2 full onefile (HDRI + fonts + Assimp)  
**Owner chat:** continue from this handoff  
**Root:** `c:\trs22\trainz_studio\`  
**Backup (pre-rename):** `c:\trs22\backups\26-10-05\mesh_studio-pre-trainz-studio\`  
**Run:** `start.bat` / `start.vbs` (silent) · `start_debug.bat` (console) · `python -m trainz_studio` (cwd = `c:\trs22`)  
**EXE:** `trainz_studio\dist\MSTN_TrainzStudio.exe` (onefile, full assets) — rebuild: `pack\build.bat` · GitHub Release `v0.3.2`  
**Shell:** `pack\shell\register.ps1` (Open + Quick Preview + Explorer pane) · `unregister.ps1`  
**Smoke:** `python -m trainz_studio.check` from `c:\trs22` → expect `trainz_studio check: OK`

### Finder fast preview — warm with Assets Tools (2026-10-07)

| Piece | Role |
|--------|------|
| `PackagesPage.warm_fast_preview_infra` | Idle `_PreviewSurface` + `load_any` import during Assets boot warm |
| `_ensure_assets_host` | Calls infra warm right after Assets Tools build |
| Select mesh | Stage+parse overlaps GL ensure; when ready → solid preview opens (no 2nd click) |
| Leave mesh | `_drop_mesh_warm` so stale warm can't steal image/text pane |

### Orbit yaw — un-invert (2026-10-07)

| Piece | Role |
|--------|------|
| `view3d.mouseMoveEvent` | LMB: `yaw_vel += +dx` (was `−dx` — content moved opposite drag) |
| `check.test_orbit_yaw_follows_drag` | +yaw moves +X landmark right on screen |

### PBR HUD (Lit…AO) — top gap (2026-10-07)

| Piece | Role |
|--------|------|
| `_reposition_pbr_hud` | `y=4` inside chrome layer — was double-counting `TITLE_BAR_H` (layer already below `TITLE_CONTENT_INSET`) |

### Mesh Ops — material names + bottom log (2026-10-07)

| Piece | Role |
|--------|------|
| `io/mat_names.py` | Check ``*.m.pbrmetal`` / ``*.m.onetex`` (+ glass/clutter…) · typo / missing / Blender ``.001`` |
| Drop FBX / trainzmesh | Auto-scan → **lm.txt preview \| material log** twin (Texture layout) |
| Prompt | Bad names → Yes/No rename in file (``.fbx.bak-mat`` / trainzmesh ``.bak``) |
| Sidebar | **Scan materials** · **Fix material names…** |

### Quit animation + text descenders (2026-10-07)

| Piece | Role |
|--------|------|
| `animate_window_quit` | Compositor `windowOpacity` + slight shrink — **not** `QGraphicsOpacityEffect` on MainWindow/GL |
| `closeEvent` | Ignores first close → runs quit anim → `_quit_ready` then real close |
| `#titleNavBtn` | FloatTitleBar File/Edit/View/Theme/Lang — compact pad (was `#navBtn` 10px + h=32 → clipped **g**) |
| `#navBtn` / `#segBtn` / `#sideTab` | Lower vertical pad; PBR HUD seg 34px in 56px glass; shortcut/status bars 26px |

### Mesh Studio — clear + Show table (2026-10-07)

| Piece | Role |
|--------|------|
| Scene **Meshes in scene** | `QTableWidget` **Show \| Atts \| Mesh file** — Atts toggles a.* gizmos per mesh; multi-mesh Scene att list gets stem tabs |
| Show ticks | Per-file viewport draw — multi-check OK; unchecked → `View3D.set_hidden_mesh_keys` |
| **Clear meshes** | Sidebar + File menu (`Ctrl+Shift+Backspace`) — unload all for a fresh Open/drop |
| **Remove selected** | Drop checked rows only (extended row select) |
| Visible from 1+ mesh | Table no longer hidden for single-file loads |

### HOME glassmorphism — 2026-10-07

| Piece | Role |
|--------|------|
| `ui/home.py` `HomeGlassFrame` / `HomeStudioCard` | Painted frost plates (shadow · sheen · accent wash on hover) |
| Whole-card click | No fat orange `accentBtn` on HOME — soft “Open →” CTA |
| Material glyphs | Circular glass badge (`HomeIconBadge`) — `layers` · `graphic_eq` · `tune` · `inventory_2` |
| Layout | Five centered tiles in **one row** (card w=220, gap 16) — short tags, airier glass, logo without plate |
| Hover bubble | Warm glass bubble on `#homeCardHost` — slides along the row (`pop_on_arrive=False`) |
| Card lift | Soft `QVariantAnimation` lift (~260ms OutCubic) — painted plate + margins |
| No clip | Lift/shadow paint inside reserved `lift_room`/`shadow_room` (Qt clips paint outside the widget) |
| Drop zone | Same frost shell + dashed rail; accent when drag-over |
| Theme | `#homeBrand` / `#homeCard*` / transparent card shells in `theme.py` |
| Bubble fix | `HoverBubbleController` uses `mapTo(host)`; `stop_pop` before slide so row jumps don’t snap |

### Package location — 2026-10-07

Moved from `tools/trainz_studio/` → **`c:\trs22\trainz_studio/`** so `tools/` stays one-shots only.  
`REPO_ROOT` / `TOOLS_ROOT` in `__init__.py`: repo = package parent; `tools/` = sibling.

### Internal libs (`lib/`) — 2026-10-07

Internalized former sibling packages (no sys.path hacks):

| Path | Role |
|------|------|
| `lib/engine_tuner/` | enginespec `config_io` · `physics` · `throttle_round` · `autotune` · standalone `run.bat` |
| `lib/im_editor/` | `.im` ATCH parse/edit (`core`) + optional Tk UI |
| `lib/trainzmesh_viewer/` | tzMF `.trainzmesh` parser + texture resolve |

Imports: `trainz_studio.lib.engine_tuner.config_io`, `…lib.im_editor.core`, `…lib.trainzmesh_viewer.parser`.

### Assets — Texture / Mesh group + top sub-nav (2026-10-07)

| Piece | Role |
|--------|------|
| Split (later) | Home **Texture / Mesh** card owns Texture·Mesh Ops; Assets keeps Packages·Config·KUID |
| Top `AssetsSubNav` | Still on page for legacy assets→texmesh path; **hidden** in `texmesh` suite (bottom nav is enough) |
| `_PageSlideHost` | Horizontal slide when switching Texture ↔ Mesh Ops |
| Sidebar | Fade swap actions on page / sub-page change |
| Pill sync | Never `set_page(animate=False)` onto same page — was killing slide mid-flight |

### i18n — Lang menu (EN / TH / JA / ID) (2026-10-07)

| Piece | Role |
|--------|------|
| Menubar **Lang** | After File / Edit / View — English · ไทย · 日本語 · Bahasa Indonesia |
| `ui/i18n/` | `t()` / `g()` catalogs · `snapshot_and_apply` · Noto font swap · QSettings `ui/language` |
| Fonts | EN+TH → **Noto Sans Thai Looped** · JA → **Noto Sans CJK JP** · ID → **Noto Sans** (`assets/fonts/`) — Lang swap rebuilds QSS `* { font-family }` + rebases every widget (Material Icons skipped) |
| Swap motion | `animate_language_swap` fades text chrome only — **never** opacity on MainWindow / GL hosts |
| VE39 | Glossary IDs (`ve39.tip` / scan / fix) explain solid-texture rejection in every locale |
| Scope | All UI strings (menus, buttons, tooltips, glass tips, dialogs, status). Not source comments. |

### Material Icons — Home / Theme + action chrome (2026-10-07)

| Piece | Role |
|--------|------|
| `assets/fonts/MaterialIcons-Regular.ttf` | Bundled Google Material Icons (Apache-2.0) |
| `ui/icons.py` | `apply_icon` / `set_home_icon` / `set_theme_toggle_icon` |
| `ui/float_chrome.py` | Shared floating capsule — pages L/R · Home center |
| Mesh / Engine / Assets bottom nav | e.g. Preview·Editor \| 🏠 \| Settings |
| **Theme** on `FloatTitleBar` | File · Edit · View · **Theme** · Lang — Dark / Light / Ctrl+T |
| Bottom Theme icon removed | Click-through under translucent chrome — use top Theme menu |
| `_apply_theme_mode` | Use `self.setUpdatesEnabled` — `QApplication` has no such API (Qt ate the AttributeError → Theme looked dead) |
| `QStackedWidget` QSS + palette push | Transparent stack stamped black on Win; hub pages kept dark Window under light — opaque `{p.bg}` + hub palette push |
| Theme toggle snappy | No `allWidgets`/`setFont` on flip (double polish); frost/HOME/hosts deferred; boot `warm_theme_cache` + logos |
| `HoverBubble` (`ui/motion.py`) | Translucent hover follower; orange `AccentPill` = selection |
| `GlassTipBubble` + `attach_glass_tip` | Custom glass tip (`apply_icon`; native Qt tip off) — max ~260px wrap, 9pt Medium (was one-line 11pt DemiBold strip) |
| `ButtonHoverChrome` / `install_button_hover_chrome` | App-wide: soft hover bubble + `chromeLift` emboss only (no button geometry — layout stays still) |
| Top/bottom bars (Mesh/Engine/Assets/Sounds + PBR HUD / side tabs) | Hover bubble springs (OutBack + pop) under any menu item |
| Sounds `FloatActionBar` | Compact Home capsule (Theme is top menu) |
| PBR HUD / bake bar | Same capsule radius language (top / progress float) |
| `#navIconBtn` | Circular bookend icons (orange hover) |
| `#iconBtn` / `#accentIconBtn` | Save · Undo · Open folder · Delete · etc. |
| Menubar + page labels | **Text only** — no icons |

### Theme — opaque lists / headers / QTextEdit (2026-10-07)

| Change | Why |
|--------|-----|
| Opaque list+header fills (`#1a1f26` / `#252b33`) | `rgba` headers over Windows Base → white N0–N8 / Parameters / Queue |
| Style all `QTableWidget` + `QTextEdit` | Packages queue + Sounds Loop QC had no sheet |
| `_prepare_item_view` on smooth scroll | Viewport/header autofill fought QSS |
| `ui/table_chrome.py` rounded rows | AccentPill-style selection bubble + hover wash (Win QSS `::item` radii ignored) · hooked via `enable_smooth_scroll` · Highlight cleared on view |
| Header `:first`/`:last` top radii + view mask | Table face matches glass shell corners |

### Theme — white/black slabs (2026-10-07)

| Change | Why |
|--------|-----|
| `_theme_qpalette` fills Active/Inactive/Disabled | Empty `QPalette()` left Windows light Base → white Mesh Info / Auto Tune |
| `prepare_frost_scroll` disables viewport autofill | `QScrollArea` painted Base over frost |
| `findChildren(FrostGlassFrame)` on theme toggle | Engine sidebar + Autotune drawer missed attr-list retint |
| `#statsCard` uses `well_fill` | Inner cards follow theme instead of Base bleed |

### Packages — CDP pack / extract / browse (2026-10-06)

| Piece | Role |
|--------|------|
| `io/cdp_lzss.py` | LZSS decompress (cdptool MIT port) + level-0 store pack · `decode_asset_text` |
| `io/cdp.py` | pack folders · extract · browse tree · delete asset/file · size bands |
| `ui/assets/packages.py` | Finder mid column · `viewer_panel` (Viewer/Editor) for studio right dock; `queue_rail` in Assets sidebar |
| Queue | Table drop only (no dashed rail) + Remove/Clear in **left sidebar** · CDP/TZarc icon footer |
| Sidebar footer | Material icons + tooltips: Open/Pack/Extract CDP · TZarc · Copy KUIDs |
| Finder | hierarchical folders first · drill-in · folder size · styled list |
| Viewer dock | Viewer\|Editor toggle · title = mode + file · back + expand icons · A+/A− · Save CDP on action row · Mesh Editor frost inset |
| Expand / Restore | Hides Finder + grows studio right dock · Editor tab disabled for view-only files |
| Texture / Mesh dock | Right props ~600px (min 480) · silk open/shut (InOutCubic 560ms, freeze page paint, defer sidebar) |
| CodeEdit | global font pt · `enable_code_scroll` coast **0.78** · **middle-click toggle autoscroll** (move ↑↓ to scroll; middle/left/Esc/wheel stops) |
| LZSS fix | mode-0: u32 `mask` wrap + flag bits **span** words (`_FlagBits`) — was garbling `.lm.txt` / long text |
| Size bands | hard ≤1 GB · recommend ≤500 MB · soft warn ≤800 MB |
| Nested CDP | double-click `.cdp` inside files → open; ← Nested CDP |
| Pack wire | BINARY = u32 size + LZSS level 0 (Trainz-valid store) |

### Theme toggle — instant + coherent (2026-10-06)

| Change | Why |
|--------|-----|
| Removed window-grab `ThemeFadeOverlay` | Grab was slow; GL regions black → half light / half dark |
| Instant `_begin_theme_change` | No cover fade; apply QSS + retint in one shot |
| Clear frost plates on theme flip | Stale blur under new tint looked mixed |
| `#appShell` / `#glHost` follow palette bg | Hardcoded `#000` hosts kept black under light ink |
| `warm_theme_cache()` + `warm_logo_cache()` at boot | Pre-build dark/light QSS, QPalette, logos — Theme click only swaps |
| Defer host `set_theme` + frost re-grab | Engine/Sounds/Assets/CodeEdit off the click path (`QTimer.singleShot`) |

### Mesh Ops — drop rail · Save all · LM params (2026-10-06)

| Change | Why |
|--------|-----|
| Dashed drop rail + table accept | Visible `.trainzmesh` / `.im` / `.fbx` / `.lm.txt` target |
| Vertical 50/50 mesh table ↔ lm.txt preview | Balanced authoring |
| Wider right LM params (field cards) | offset / multiplier / cutoffs |
| calcPoint = segmented pills + accent slide | Same motion language as nav |
| Column **LOD** + **Save all…** | Unticked → one `.lm.txt` per mesh; ticked → one shared LOD file |
| Write beside drop folder when shared parent | Else pick destination directory |

### Texture.txt — drop rail · params sidebar (2026-10-06)

| Change | Why |
|--------|-----|
| Dashed drop rail + image list accept | `.tga` / `.png` / `.bmp` / `.jpg` / `.dds` / `.texture.txt` |
| Right **Texture Params** frost panel | Wide + collapsible splitter; Primary / Alpha + Tile / Usage / Normal / Compression |
| Preview \| Check/scan side-by-side | Was stacked under Images |
| **Save all…** | One `.texture.txt` per listed image; stem → albedo/normal/parameter (TXT Generator-style) |
| `keys_for_image` / `material_family` | PBR UsageHint + NormalMapHint from filename |
| Shared `_SegPills` (LM calcPoint + tex enums) | Same accent-slide motion as nav |
| Click list row → Primary + stem hints | albedo / normal / parameter auto |

### Texture — Image Prep + VE39 (2026-10-06)

| Piece | Role |
|--------|------|
| `io/image_prep.py` | Batch resize → sibling `_prep/` · % / exact / max / PoT · normal re-normalize · param linear |
| `io/ve39.py` | Uniform solid detect + noise-dot fix · one-time `.bak` then in-place |
| Texture right panel | Map / Resize / Format + spins · Flip green · PoT down |
| Sidebar | **Resize → _prep…** · **VE39 scan** · **VE39 fix…** (QThread, log in Check pane) |
| Skipped | File Generator (already native) · BatchFileRenamer · launch external exe |

### Texture — right side tabs + full-height panel (2026-10-07)

| Change | Why |
|--------|-----|
| Side tabs **Texture Params** \| **`Resize → _prep`** | Instant swap (no opacity fade — Win frost crash / invisible options) |
| Crash notify | Glass dialog (`ui/crash_dialog.py`) · `last_error.txt` · next-launch sheet · `fault.log` |
| Title **Batch Resize → _prep/** + tip | Clarifies non-destructive sibling `_prep/` output (VE39 stays separate) |
| Checkbox **Use these settings…** | Default OFF (opt-in) · Off → SegPills/spins dimmed/unclickable + sidebar Resize disabled |
| `_SegPills.changeEvent` | Child buttons follow enabled; `_pick` no-ops when disabled |
| Scroll `heightForWidth` + resize sync | Word-wrap tip under-measured → no scrollbar; remasure on dock width |

### Texture — Finder table · PBR sets · auto VE39 (2026-10-07)

| Piece | Role |
|--------|------|
| Images list → table | Name (A/N/P badge + set subtitle) · Dims · Ch · Size · Status |
| Role tint | albedo green · normal cyan · parameter orange row wash |
| PBR grouping | `sort_texture_paths` / `material_family` — family then albedo→normal→parameter |
| Drop onto table | Texture + Mesh Ops — empty/drag hint on table (small ext type) |
| Name elide | Middle-elide + tiny width hint; row height 64 so title+subtitle are not clipped vertically |
| Selection pill | Stronger orange wash + soft rim (was rim-only / black center) |
| Double-click row | Select whole PBR family (ExtendedSelection) |
| Auto catalog | On drop: `probe_image` + `scan_ve39` → Dims/Ch/Size/Status (OK / VE39 #hex) |
| `io/texture.py` | `ImageProbe` · `probe_image` · `pbr_set_label` · `sort_texture_paths` |

### Mesh Ops / Texture — params width (2026-10-06)

| Change | Why |
|--------|-----|
| Right params max uncapped · default ~520 | Drag as wide as needed |
| `setChildrenCollapsible(True)` | Drag splitter to the end → tuck panel away |

### CodeEdit — txt preview / editor (2026-10-06)

| Piece | Role |
|-------|------|
| `ui/code_edit.py` | VS Code-like gutter line numbers · Ctrl+F find · Ctrl+H replace · F3 / Shift+F3 |
| Syntax | [agmike/vscode-trainzscript](https://github.com/agmike/vscode-trainzscript): `trainzconfig` (txt) + `trainzscript` (`.gs` — comments/`include`/keywords/types/strings/numbers/ALL_CAPS/PascalCase/calls) |
| Wired | Packages Viewer (auto by filename) · Mesh Editor `.texture.txt` · Assets Config/chump · texture/lm · KUID |

### Assets Tools hub (2026-10-06) — native, no exe launch

| Path | Role |
|------|------|
| `ui/assets/studio.py` | Hub — frost sidebar + stack + bottom nav |
| `ui/assets/sidebar.py` | Native page actions only |
| `ui/assets/nav.py` | Suite nav: Assets **Packages**\|**Config**\|**KUID** · TexMesh **Texture**\|**Mesh Ops** |
| `ui/assets/kuid.py` | Normalize + hex/hash UI helpers |
| `io/lm.py` | Parse/write `*.lm.txt` |
| `io/texture.py` | `format_texture_txt` / `write_texture_txt` (+ existing check) |
| `io/image_prep.py` | Resize → `_prep/` (map-aware) |
| `io/ve39.py` | Solid-texture VE39 fix |
| `io/kuid_bin.py` | UUUVNNNN pack + `hash-XX` (CDPExplorer/Kuid2Hash RE) |
| `io/cdp.py` | CDP pack / extract / browse (+ list) |
| `io/cdp_lzss.py` | BINARY LZSS decompress + level-0 store |
| `ui/assets/packages.py` | Packages dual tables + contents sidebar |
| `io/chump.py` | **config.chump** read/write + text expand/pack (ChumpLib-style) |
| `io/tzarc.py` | TZarc **v1** + **v2** (TRS22 zlib chunk table, `size+1`) |

**Packages:** pack/extract CDP · dual drop tables · contents sidebar (delete / nested CDP) · TZarc · KUIDs.  
**Config:** edit `config.chump` ↔ pack / export `config.txt`.  
Still deferred: `.texture`→TGA, PM→IM, shadow.im, AttachmentMaker.  
HOME 2×2 · hub wipe **Assets↓** · theme ◐ · Texture/Mesh top sub-nav.

### Mesh Open / Quick Preview (2026-10-06; pane dropped 2026-10-07)

| Piece | Role |
|-------|------|
| `ui/mesh_preview.py` | `--preview` fast window (geo → PBR); `--explorer-preview` kept for opt-in only |
| `pack/shell/register.ps1` | HKCU Open + **Quick Preview** for `.trainzmesh` / `.fbx` / `.im` |
| Explorer Alt+P pane | **Off by default** — Win11 prevhost + managed/GL = white / can’t preview. Opt-in: `-WithExplorerPane` |

Boot branches on `--preview` / `--explorer-preview` **before** `MainWindow` import.  
`.im` preview = ATCH gizmos only. Register: `register.ps1 -Source` (or frozen without `-Source`).

### Light / dark theme toggle (2026-10-06) — superseded by “instant + coherent” above

| Change | Why |
|--------|-----|
| Stop `setUpdatesEnabled(False)` + sync `grabFramebuffer` | Froze UI on theme click |
| `paint_glass_chip` / `set_glass_dark` theme-aware | Nav / HUD stayed dark forever |
| `panelEdgeBtn` + default `QLabel` ink in QSS | Edge chevrons / labels ignored light sheet |
| ~~`ThemeFadeOverlay` grab fade~~ removed | Slow + GL black holes → mixed plates |

### Button hover (2026-10-06)

| Change | Why |
|--------|-----|
| `ui/theme.py` plain `QPushButton`/`QToolButton` hover | Was painting accent L-border + orange text → looked like a focus ring on black pills |
| Neutral raise-fill lift; orange stays on `#accentBtn` only | Cleaner hover; primary CTAs still orange |

### HOME hub transitions (2026-10-06)

| Change | Why |
|--------|-----|
| `ui/motion.py` `HubRevealOverlay` | Cinema morph: depth plate · glass feather · specular · tracked caption |
| Smooth path: downscale snap ≤1440 · baked caption · InOutCubic · no rotate fills | Kill stutter from 4K blit + multi-stage ease kicks |
| Directions: Mesh← · Sounds↑ · Engine→ · Assets↓ (reverse home) | Distinct per studio; no MainWindow/GL opacity |
| `warmup_hub_studios()` in boot frost | Precache Mesh + Sounds + Engine + Assets before HOME clickable |

### Ship / machine perf (2026-10-06)

| Change | Why |
|--------|-----|
| `pack/build.bat` + `trainz_studio.spec` + `entry.py` | PyInstaller onedir ship |
| `util/hw.py` — workers = cpus−1 (tex≤24, bake≤16), BLAS caps, ABOVE_NORMAL, desktop GL | Squeeze Ryzen/RTX host without starving UI |
| Frozen `PKG_ROOT` via `sys._MEIPASS` | assets/ + Assimp DLL resolve in exe |
| CuPy excluded from freeze | Dist stays lean; GPU bake stays source-only |
| matplotlib **included** (Engine TE graphs) | Was excluded → `warmup_hub_studios` ModuleNotFoundError |
| `lib/engine_tuner` · `lib/im_editor` · `lib/trainzmesh_viewer` | Internalized (was sibling `tools/`); package imports, no sys.path hacks |

This host smoke: `cpus=12 tex_workers=11 bake_workers=11` (Ryzen 5 3600).

### HOME drop zone (2026-10-06)

| Change | Why |
|--------|-----|
| `ui/home.py` `HomeDropZone` dashed rail + type list | Visible drop target on HOME |
| Routes via `_handle_dropped_paths` | Same path as window drop |
| `.mtzs` → project open | Work-file drop completeness |
| `HomePage` glassian blur wash (theme accent orbs) | Soft gradient backdrop; no MainWindow opacity |

### Boot speed (2026-10-06)

| Change | Why |
|--------|-----|
| `ui/boot.py` — QApplication before `MainWindow` import | Qt warm, then heavy module |
| HOME shell only in `MainWindow()` (~0.1s ctor) | Mesh chrome / Sounds deferred |
| `ensure_studio_chrome()` after first paint | Sidebar+Editor+nav assemble in background |
| Sounds built on `enter_sounds_studio` only | No audio stack at launch |
| `ui/frost.py` split from Editor | HOME need not import Editor |
| scene.py lazy-imports numpy | Empty Scene at boot stays light |

### Move gizmo (2026-10-06)

| Change | Why |
|--------|-----|
| Solid RGB arrow cones + center cube | Blender-like translate handles (was flat lines + orange glow) |
| Orbit target stays put while drag | Camera was chasing the a.* mid-move |
| Shared `gizmo_axis_length` for draw/pick | Tip grab matched visible arrows |

### Mesh open speed (2026-10-06)

| Change | Why |
|--------|-----|
| tzMF vertex decode → numpy strided | Python `struct` loop was ~10× slower |
| Decode winner once in parser | Stop re-decoding every endian/index candidate |
| `parse_trainzmesh_attachments` / `parse_attachment_records` jump via `b"a."` | Byte-walk of 6MB with 0 a.* was ~1.6s |
| Single disk read + `Scene.source_bytes` for Editor | Was reading the file 2–3× |
| `set_scene` purge keeps CPU `_decoded_cache` | Precache was wiped every open (bug) |
| Viewport first; Editor/Mat/lamps on `QTimer(0)` | First paint before island scan / list spam |
| Albedo precache max edge 2048; normals/params full | Big PNG open cost without tearing lamp maps |
| Faster lamp island union-find (packed edges) | Less jank when many onetex bulbs |

### Undo / Project / Self-backup

| Feature | How |
|---------|-----|
| **Undo / Redo** | Unlimited · `Ctrl+Z` / `Ctrl+Y` (or `Ctrl+Shift+Z`) · Edit menu · coalesced spin bursts |
| **Project** | File → Save/Open Project (`*.mtzs` + optional `.mtzs.buf` dirty buffer) |
| **Crash recover** | Autosave every **1 min only if edited** → `~/.cache/trainz_studio/crash_recover/` (+ `.mtzs` if project open) · prompt on next launch |

Helpers: `io/history.py` · `io/project.py`.

### Editor — Tab Edit pie (View / Move)

- **Preview** Tab = Shading pie; **Editor** Tab = Edit pie (View / Move, default View).
- Pie parents to `#center_host` + `WA_AlwaysStackOnTop` so it paints **above** GL/`#chromeLayer` (was invisible under chrome).
- Hold Tab → aim → release; short tap keeps pie sticky until click / Esc.
- Tab is stolen from sidebar spin/line/combo (ShortcutOverride + ClickFocus-only); only `QPlainTextEdit` keeps Tab.
- Move: drag **center cube** = free; drag **R/G/B arrow** (shaft or cone tip) = constrain. Miss gizmo = orbit. Shift = fine.
- Gizmo arrows/cube: **Editor + Move only** (Preview / Editor View = thin RGB axes highlight).
- Orbit target does **not** chase the point while dragging (camera stays put).
- Alt+LMB still picks a.* on both pages.

### Tab ModePie glassmorphism — 2026-10-08

| Piece | Role |
|--------|------|
| `ModePie` paint | Frost donut wedges + specular sheen + warm hover plate (theme via `glassDark`) |
| Open / close | Paint-time `_reveal` scale (OutBack open · InCubic close) — **no** opacity on MainWindow/GL |
| Bubbles | Orbiting glass orbs while armed (`QTimer` 16ms); seed on `popup_at` |
| Center hub | Frosted disc + accent title; soft radial veil instead of flat black slab |
| Theme | `_retint_glass_chips` also tints `_shading_pie` / `_edit_pie` |

### Face Orientation (2026-10-07)

| Piece | Role |
|--------|------|
| Scene tab → **Face Orientation** checkbox | Toggle Blender-style overlay |
| `view3d` `u_face_orient` + `gl_FrontFacing` | Blue = front, red = back (winding) |
| Cull off while on | Back faces must paint red |

Trainz cares about facing (cull / single-sided shade). Red outside ≈ flipped winding/normals.

### Trainz Z-up viewport (2026-10-07)

Viewport matches Trainz / PAY: **+Z up**, −Y forward (no more Y-up convert on `.trainzmesh`).
Camera / grid / sun / IBL / a.* / Face Orientation all share that basis. FBX Assimp Y-up is converted in on load. Lit PBR: stronger softbox IBL, ACES tonemap, two-sided-only normal flip.

### Viewport render (Lit) — perf notes

Mode-independent jank (shading switch does nothing) was mostly CPU overlays, not Lit:
- **Sun sphere rebuilt every paint** (Sun mode default ON) → now unit-mesh cache + numpy place.
- **Mat outline** edge list cached (cap 12k) and kept on a VBO. Draws while the camera moves — the old `_cam_busy` skip hid the orange frame until the view settled and hitched that frame.
- **Frost** `grabFramebuffer` + `view.update()` + `processEvents` → removed; skip grab while orbiting.
- a.* gizmos: one batched line draw; line-prog locs cached; grid cached.
- No lighting LOD on orbit (that caused bright-while-drag / dark-on-release). CPU skips only (frost/outline).
- Reference: `backups/26-10-05/mesh_studio-pre-trainz-studio/render/view3d.py`

Paste this into a new chat when continuing:

> Continue Trainz Studio from `trainz_studio/HANDOFF.md`. Read that file first. Do not re-audit the whole app unless asked.

---

## What this is

**MSTN Trainz Studio** — PySide6 shell with HOME · Mesh · Sounds · Engine · Assets Tools.

### Engine Tuner (2026-10-06)

| Path | Role |
|------|------|
| `ui/engine/studio.py` | Hub — left sidebar + stack + bottom nav |
| `ui/engine/sidebar.py` | Frost side: Open · summary · footer Save/Undo |
| `ui/engine/nav.py` | Bottom glass nav: **Tuner** \| **Simulation** \| **Parameters** |
| `ui/engine/throttle_panel.py` | Notch tables (+/− add/remove points) + TE graph |
| `ui/engine/pressure.py` | Trainz native ↔ bar ↔ kPa (×1000 ≈ bar) |
| `lib/engine_tuner/` | `config_io` · `physics` · `throttle_round` · `autotune` (+ standalone `app.py`) |
| `ui/engine/autotune_dialog.py` | TEE Autogenerate + Davis friction/accel dialog |

Sidebar = Mesh frost theme · min **280** / default split **360** · enginespec summary (MR/BP bar·kPa) · fixed footer Save/Save As/Undo/Redo.  
Pages: Tuner · Simulation · Parameters. HOME card · `lib/engine_tuner/run.bat`.  
**Auto Tune** — Mesh `editorDock` @ **500px** · bottom-nav right of Parameters · left sidebar frozen · open/close anim freezes matplotlib + throttled ticks · notch N0–N8 row scrolls L/R when cramped.  
**Clone curves** live on the left sidebar (numbers above checkboxes) — not the graph toolbar.

### Mesh Studio — Editor dock (MeshEditor-style)

| Tab | Contents |
|-----|----------|
| **Attachments** | Right dock = detail only (Parent / Location Z-up / Rotation). **List on left Scene tab** |
| **Meshes** | Right dock = material detail only. **List on left Scene tab** (switches with Editor tab) |

Left Scene list follows Editor tab (a.* ↔ meshes). Inputs, sliders, and dropdowns: **no mouse-wheel** (the dock still scrolls). Dock width **480** (was 340; still capped so ≥40% of the viewport stays clear). Numeric fields stay short; text fields fill the column.

| Source | a.* read | a.* write | material write |
|--------|----------|-----------|----------------|
| `.fbx` | Assimp empties | preview | — |
| `.im` | ATCH | Save (.im) | — |
| `.trainzmesh` | tzMF table | **Save** binary (+ `.bak` once) | **Save** binary (textures/colors/specPower/names) |

Binary helpers: `io/tzmf_edit.py` · UI trees: `ui/mesh_prop_tree.py`.  
**No external MeshEditor launch** — Studio owns read/edit/Save.

Draw Mode / Blend / Wireframe shown but not mapped to binary yet.

### Sounds Studio

| Feature | Status |
|---------|--------|
| Drop / Open WAV | Yes (44.1 kHz mono) |
| mp3 / video via ffmpeg | Yes — PATH or **ffmpeg…** button (`~/.cache/trainz_studio/settings.json`) |
| Waveform + amp | Yes |
| Auto QC + Fix + Save As | Yes (never silent overwrite) |
| Play / Loop | Yes |
| **Track→Track A→B** | **Yes** — Set A / Set B / Play A→B (play A → stop → loop B) |
| Fix level-match to B | Yes when fixing slot A and B is set |

Trainz seam model: **no runtime overlap** — baked Fix handles smoothness; A→B is stop-then-play.

---

## File map

| Path | Role |
|------|------|
| `ui/editor.py` | Editor dock (Attachments \| Meshes) |
| `ui/mesh_prop_tree.py` | MeshEditor-style collapsible property trees |
| `io/tzmf_edit.py` | tzMF material + attachment parse/patch/write |
| `io/history.py` | Unlimited undo/redo snapshots |
| `io/project.py` | `*.mtzs` + crash self-backup |
| `ui/sounds/studio.py` | Sounds host UI |
| `ui/engine/studio.py` | Engine Tuner host UI |
| `ui/assets/studio.py` | Assets Tools host UI (native) |
| `io/lm.py` · `io/cdp.py` · `io/tzarc.py` · `io/kuid_bin.py` | Assets writers / package list |
| `io/loaders.py` | load + `parse_trainzmesh_attachments` |
| `ui/mesh_preview.py` | Fast `--preview` / Explorer embed host |
| `pack/shell/` | register/unregister + `MeshPreviewHandler.cs` |

---

## Phase roadmap

- **A–C (done)** Sounds  
- **D:** batch QC · optional auto-pair from names  
- **Editor:** Draw Mode / Blend / Wireframe binary map · attachment Add/Delete for tzMF table rebuild  

## Do after edits

1. `python -m trainz_studio.check` (from `c:\trs22`)
2. Update this HANDOFF when shell/Editor/Sounds behavior changes
