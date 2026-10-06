# MSTN Trainz Studio — continuation handoff

**Last updated:** 2026-10-07 (Asia/Bangkok) — Mesh Studio clear + Show table  
**Owner chat:** continue from this handoff  
**Root:** `c:\trs22\trainz_studio\`  
**Backup (pre-rename):** `c:\trs22\backups\26-10-05\mesh_studio-pre-trainz-studio\`  
**Run:** `start.bat` / `start.vbs` (silent) · `start_debug.bat` (console) · `python -m trainz_studio` (cwd = `c:\trs22`)  
**EXE:** `trainz_studio\dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe` — rebuild: `pack\build.bat`  
**Shell:** `pack\shell\register.ps1` (Open + Quick Preview + Explorer pane) · `unregister.ps1`  
**Smoke:** `python -m trainz_studio.check` from `c:\trs22` → expect `trainz_studio check: OK`

### Mesh Studio — clear + Show table (2026-10-07)

| Piece | Role |
|--------|------|
| Scene **Meshes in scene** | `QTableWidget` **Show \| Faces \| Mesh file** (same column language as Assets Mesh Ops) |
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
| Layout | Four centered tiles in **one row** — short tags, airier glass, logo without plate |
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
| Bottom `AssetsPageNav` | **Packages** · **Config** · **Texture / Mesh** · **KUID** + Mesh-style scrub |
| Top `AssetsSubNav` | Same capsule / scrub, **no Home/Theme** — **Texture** \| **Mesh Ops** |
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
| `ui/table_chrome.py` rounded rows | Real row radius + hover bubble + orange pill (Win QSS `::item` radii ignored) · hooked via `enable_smooth_scroll` |
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
| `ui/assets/packages.py` | Finder · Viewer/Editor; `queue_rail` mounted in Assets sidebar |
| Queue | Drop + table + Remove/Clear in **left sidebar** (wider) · CDP/TZarc icon footer |
| Sidebar footer | Material icons + tooltips: Open/Pack/Extract CDP · TZarc · Copy KUIDs |
| Finder | hierarchical folders first · drill-in · folder size · styled list |
| Sidebar | Viewer\|Editor toggle · title = mode + file · back + expand icons (top-right) · A+/A− · Save CDP on action row |
| Expand / Restore | Animated Finder splitter collapse (~420ms) · Editor tab disabled for view-only files |
| Texture / Mesh dock | Right props ~600px (min 480) · silk open/shut (InOutCubic 560ms, freeze page paint, defer sidebar) |
| CodeEdit | global font pt · `enable_code_scroll` coast **0.78** (hard brake / reverse kills coast) |
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
| Drop onto table | Dashed rail removed — empty/drag paint on table; more row height |
| Name overlap fix | Cell widget only (no duplicate `setItem` text under badge title) |
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
| `ui/assets/nav.py` | Bottom: **Packages** \| **Config** \| **Texture / Mesh** \| **KUID** · Top: **Texture** \| **Mesh Ops** |
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
- **Mat outline** rebuilt ≤80k edges every paint → cached, capped 12k, skipped while `_cam_busy`.
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

Left Scene list follows Editor tab (a.* ↔ meshes). Spinboxes: **no mouse-wheel** — type or arrow buttons only.

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
