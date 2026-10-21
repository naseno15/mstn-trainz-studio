# MSTN Trainz Studio C++ — continuation handoff

**Last updated:** 2026-10-22 (Asia/Bangkok) — Mesh drop after Clear

Clear meshes puts the full-page drop target back (the chrome mask used to stay holed, so a drop on the empty view never arrived). A drop on the welcome screen replaces the scene. A file that does not open is not kept in the scene list, so the next `.fbx` cannot reload the previous `.fbx` + `.trainzmesh` set. The viewport itself accepts drops while a mesh is open.

**Last updated:** 2026-10-20 (Asia/Bangkok) — Material Color in Live viewport

Material Color drives the viewport in Material / Lit / Albedo (not Solid/Wireframe clay). No albedo → flat `u_flat_color` from the mat; with albedo → texture × colour. Load paints `ViewPart::color` from matching mats; channel / swatch edits and undo call `apply_mat_color_preview`. StdZeroTex like `arrow.trainzmesh` / `red.m.m.notex` shows red live.

**Last updated:** 2026-10-20 (Asia/Bangkok) — Texture Editor Overlay vs CHANNELS + queue pick

Overlay **Sample from stamp** (gray/R/G/B/A) only chooses which channel to *read* from the stamp. Destination channels are the Adjust → CHANNELS ticks (`ch_r_`…`ch_a_`, all on by default) — that is why Overlay looked like it painted the whole map. Dropping a grey image onto a channel box still replaces that one channel. `pick_row` on the parameter page now sets `param_queue_` current row (Maps list clicks open that image).

**Last updated:** 2026-10-18 (Asia/Bangkok) — Color / Type edit + save

RGBA channel boxes use the same draft/commit pattern as Name. Colour swatches open `QColorDialog` (`color` / `emisPick` / `specPick`). Type chips match case-insensitively and write `StdOneTex` (not a duplicate `stdonetex`). Material Color / Emissive / Specular / Specular Power / Type are written on Save when the block has those offsets (StdOneTex on halser has them).

**Last updated:** 2026-10-18 (Asia/Bangkok) — Meshes Editor fields commit before Save

The Name / texture / spin Fields kept a live↔text binding that reset the typed value on blur before `commit`, and Save often never stole focus from the TextInput, so renames never reached `setText` / the file. Fields now keep a draft, commit on blur from that draft, and Save / Save As `forceActiveFocus` + `Qt.callLater` so the write sees the new name.

**Last updated:** 2026-10-18 (Asia/Bangkok) — Orphan material pick warns

Picking a material with no matching part (name / albedo stem) posts ““…˝ is not on any geometry”. Attachment rows stay quiet. Changing a texture on an orphan material still saves the slot but says the preview is unchanged.

**Last updated:** 2026-10-18 (Asia/Bangkok) — Meshes Editor texture pick updates Live preview

Changing an Albedo / Normal / Parameters slot (browse or type) reloads that image onto matching parts via `MeshView::setPartPixels` (no camera reframe). Resolve still looks beside the mesh (`name.texture` → sibling `.texture.txt` Primary). Missing images keep the old preview and say so on the status line. Undo re-applies the current material's maps.

**Last updated:** 2026-10-18 (Asia/Bangkok) — Meshes Editor texture labels + pick

Texture browse prefers `.texture.txt` / `.texture` (images still allowed). Picking `foo.texture.txt` stores `foo.texture` in the mesh slot. Map column shows friendly names (Albedo, Env BRDF / Irradiance / Radiance, Normal, Parameters); Color uses Emissive / Specular / Specular Power; Vertices is Vertex Format. Raw Trainz keys stay in the file. `check_mesh` covers `mesh_tex_map_label` / `mesh_texture_slot_ref`.

**Last updated:** 2026-10-15 (Asia/Bangkok) — Mesh Studio Save / Save As always save or say why

Save used to grey out as soon as two meshes were open (`saveOn` was `!path_.isEmpty()`, and scene mode clears `path_`), so clicks did nothing. Scene mode was preview only. Now `load_scene` keeps each file's bytes (`file_bytes_` is one per scene file), its real `tzmf` material blocks (`MatEdit::file` plus a list prefix in `label`), and its attachment offsets. `MeshBridge::save_files(ask)` writes every scene `.trainzmesh` whose bytes or `.meta` two-sided flags changed. Single-file Save always writes. Save As writes the selected file and points the scene at the new path. `.bak` is made on first write, and both the mesh and the `.meta` go through `QSaveFile`. Offsets are re-read from the current bytes on every save and paired by index. They used to be the load-time offsets, so a rename that resized a string made the next Save write floats at stale offsets. Yawed Preview Asset files are spun back, and attachments matching `att_base_` stay untouched. `.im` / `.fbx` only get `.meta` flags. Every outcome gets a toast: Saved, Save failed, Not saved (preview only), or No changes to save. `check_mesh` covers both modes on temp copies. The ATS checks fall back to `backups/26-10-15/…` now that the asset left `editing/`.

**Last updated:** 2026-10-15 (Asia/Bangkok) — Texture Params writes what it shows

Ticking Alpha with no file writes `Alpha=<Primary>` (Trainz takes alpha from the Primary image itself). Renaming Primary moves that along. Picking an image (drop or list row) runs `open_primary`: it loads that image's sibling `<name>.texture.txt` into the form if there is one, so nothing carries over from the previous image. With no file, Tile and Compression stay as set, and Alpha, hints and extra keys start empty. Opening a `.texture.txt` resets every field first (`load_texture_keys`). Keys the form has no field for (AlphaHint, ModifyMap, MipAlgorithm, nonpoweroftwo, unknown) stay in `tex_extra_` and are written back. Save opens on the form's own `tex_path_`. Save all writes the form's file exactly as previewed. Every other file keeps its own keys: Primary, Tile and Compression come from the page, and name-guessed UsageHint / NormalMapHint only fill gaps. Writes go through `QSaveFile`, and failures show in the status line. Nothing auto-saves: edits change the preview until Save / Save all. `check_assets` covers the Alpha tick, the kept AlphaHint, and switching rows.

**Last updated:** 2026-10-15 (Asia/Bangkok) — TGA read/write everywhere

Neither Qt install (`Qt` or `QtStatic`) has a qtga image plugin, and Qt's own cannot write. `src/ui/tga_image.cpp` is a static Qt image plugin (`TrainzTgaPlugin`, `Q_IMPORT_PLUGIN` in the same file) so every `QImage`, `QImageReader`, `QImage::save`, and QML `Image` handles `.tga`: Texture Editor, Params, Denoiser, Resize → `_prep` as TGA, Mesh Studio textures, thumbnails. It reads 24/32-bit colour and 8-bit grey, raw or RLE, any origin. It writes uncompressed bottom-left TGA: grey stays 8-bit, alpha gives 32-bit, otherwise 24-bit. That file is compiled with `QT_STATICPLUGIN` and no PCH (CMake source properties). Mesh Studio's private `decode_tga` is gone. `check_mesh` round-trips all three depths, decodes an RLE packet, and opens the KIHA40 `label/0.tga` when present.

**Last updated:** 2026-10-15 (Asia/Bangkok) — `.kin` per mesh in multi-mesh scenes

Each `.kin` belongs to one scene file (`HeldKin::file`): the mesh in the `.kin`'s folder whose bytes hold every bone as a whole name (`kin_bones_in_mesh` rejects `r.ats` inside `r.atsleft`). Ties go to `<mesh>_scene.kin`, then `<mesh>.kin`, then `<mesh>*.kin` (`kin_rank`). `bind_anims` runs after both `load_file` and `load_scene`, so dropping atsleft + atsright + ats_box finds both clips; a `.kin` dropped onto a scene binds the same way. Each clip has its own frame and play state. Play/Stop and the Frame slider act on the selected clip only, several meshes can play at once, and one mesh takes one clip at a time (`own_file`). `MeshView::setFileAnims` holds one model matrix per file (`ViewPart::file` / `ViewAtt::file`). Attachments of an animated file move with it. Shadows stay at rest pose. Scene yaw is applied to the motion as well. `check_mesh` covers the KIHA40 ATS meshes when that editing folder exists.

**Last updated:** 2026-10-15 (Asia/Bangkok) — every trainzmesh material is listed

`.trainzmesh` material blocks are found by layout only (`read_material_head`: identifier type, name, `00000000 01`, colour, BE count 1–32, then every key/value string). There is no type whitelist and no `.m.` name rule. The old list was lowercase and compared case-sensitively, so `StdOneTex` / `StdOneTexBlend` blocks (lights, dest signs, stickers, status) were dropped. Part naming (`bind_material_names`) and `parse_tzmf_materials` share that reader. `texture0` counts as the albedo slot. The Type combo has one handler that respects an unknown type prepended at index 0. `check_formats` covers a `StdOneTexBlend` block with no `.m.` and the real KIHA40 `int.trainzmesh` (26 materials).

**Last updated:** 2026-10-14 (Asia/Bangkok) — TrainzUtil only on demand, faster library search

Opening Assets Tools or Texture & Mesh Lods no longer builds the TrainzUtil page, so the Launcher probe and library sync do not start. Only the TrainzUtil page itself, or the Assets **Config** tab (`AssetsBridge::pageOpened("config")`, deferred one tick), builds it. A KUID pick still builds it if it is missing. Library search keeps one lowercase search string per row (`LibraryList::hay_`) and clears it in every mutator that changes rows, dates, owners, meta, or credits. Typing more of the same query filters the current `shown_` (already sorted) and skips the full re-scan and re-sort. `check_trainzutil` covers narrowing, widening, and a row added mid-search.

**Last updated:** 2026-10-14 (Asia/Bangkok) — screen scale, Texture Params clear buttons

The layout is drawn for a 1920×1080 desktop. `prepare_qt_runtime` reads the primary desktop in logical pixels (a DPI-unaware thread's `GetSystemMetrics`) and sets `QT_SCALE_FACTOR` to `ui_scale_for(w, h)` = min(w/1920, h/1080), clamped to 0.5–1. 1366×768 gets 0.711. It never scales up, and a `QT_SCALE_FACTOR` already in the environment wins. The device pixel ratio can now be below 1, so `MeshView` uses `devicePixelRatioF()` unclamped, and the boot × hit box is converted to physical pixels with `ClientToScreen`. Texture Params has Clear selected / Clear all on its list too (`tex_remove` / `tex_clear`). Both pages remove rows through `remove_selected_rows`, which sorts the extended selection first. The static-tree `check_shell` cannot load QML (no plugin import on check targets); run it from `build`.

**Last updated:** 2026-10-13 (Asia/Bangkok) — Scene tab order, middle-drag scroll

On the Mesh Studio Scene tab the Viewport card sits under Mesh Info, above Attachments. Holding the middle button and dragging scrolls the left sidebar, the right Editor dock, and the Settings page at 3× pointer travel (`MiddleScroll.qml`, a middle-button `DragHandler` with `flick` and `gain`). Left clicks still go to the rows.

**Last updated:** 2026-10-12 (Asia/Bangkok) — Scene attachment list

Dropping a `.trainzmesh` puts each `a.*` name in the left Scene list. Clicking a row selects that triad and flies the camera to it. The list stays on the Scene tab while previewing.

Attachs Editor shows the picked attachment's name, location (m, up to 6 decimals), and rotation as Blender XYZ Euler degrees (R = Rz·Ry·Rx), each on its own full-width row. The stored quaternion is a read-only line under them. Enter or leaving a field applies the value at once (normalized quaternion, triad moves). Apply does the same. Save writes position and quaternion back into the `.trainzmesh` at the parsed offset. Rename, Parent, Add, and Delete are not written yet. Those buttons are disabled. `.im` and multi-mesh scene attachments are preview only.

Picking Move on the Attachs Editor pie (Tab) turns on viewport drag. The picked attachment gets arrowheads and a white centre box. Left-drag the centre to move it in the view plane, or one of its axis lines to slide along that axis. Holding Shift during a free drag locks to the world axis it has moved along most. Esc during the drag puts it back. `pie_sector` centres slice i on i·step from the top, matching the drawn wheel. It used to start slice 0 at the top, so the upper-left of Move read as Edit. Location and Rotation are three fields per row. Apply / Add / Delete are icon buttons with the RaiseButton glass tip. Add and Delete only post a status line. Location fields follow the drag. Save writes it the same as Apply. `.fbx` nodes named `a.*` load as attachments (world pose from ufbx, no geometry); `checks/fixtures/att.fbx` covers it.

Undo / redo (Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y, Edit menu) goes through `page_verb` → `call:undoEdit` / `call:redoEdit` per page. Mesh Studio snapshots attachments and material blocks (`MeshBridge::EditSnap`, 100 steps) around `setChecked` / `setCombo` / `setText` / `setSpin` / `setChannel` / Apply, and one step per viewport drag (`MeshView::attDragDone`). View toggles don't make a step because nothing in the snapshot changes. History clears on load and Clear. Assets Config keeps whole-text snapshots per row edit; one Source typing burst is one step. Engine Tuner and Texture & Mesh Lods keep their own stacks. Sounds has no undo: Fix adds a new clip and never overwrites. A focused text field keeps its own Ctrl+Z.

**Last updated:** 2026-10-12 (Asia/Bangkok) — view gizmo on the viewport, cropped logo

The axis triad floats at the top-left of the mesh viewport. Drag orbits. Clicking an axis flies the camera onto that axis. `LogoProvider` crops `assets/mstn_logo_white.png` to the ink and every sidebar, Home, and About uses that mark at the column width.

Dropping a mesh lists `.kin` files in the same folder whose bone names are inside that mesh (`windowcab.trainzmesh` → `windowcab_scene.kin`, bone `r.fuckyou`). Play and the frame slider move a one-bone part from frame 0. A dropped `.kin` whose bones are not in any loaded mesh is reported and not kept. (Multi-mesh: see 2026-10-15.)

**Last updated:** 2026-10-12 (Asia/Bangkok) — attachment pick and names

Left-drag orbits even when the press lands on an attachment. Shift+click selects an attachment (brighter axes) or, if the click misses, a mesh part. Shift+click on empty space clears the attachment and the material highlight. Att names are rasterized to an image and drawn as a screen quad. QPainter on the OpenGL framebuffer flipped the glyphs.

**Last updated:** 2026-10-12 (Asia/Bangkok) — trainzmesh attachment axes

Opening a `.trainzmesh` reads the `a.*` table (same pose as an `.im` ATCH) and draws the RGB triad after the body, on top of the shell. The Atts checkbox still hides that file's points. An attachment-only `.im` is unchanged.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Config tag editor

Assets Config opens `config.txt` (drop, Open, or the library **Edit config** button) as sunk fields. Short tags sit four across. `username` and `description` take the whole row, and `description` is a tall wrapping field. A hairline splits Identity, Category, Credits, Script, Asset, and Containers. A container row drills in, so `mesh-table` → a mesh → `effects` → `texture-replacement` / `corona` / `attachment` are the same list, with the editor chosen from the parent container. KUID rows pick from the TrainzUtil library, filtered by category-class. Numbered `kuid-table` keys stay plain text. Save writes `config.txt` back when the file came from an editing folder; a library copy that is not open for edit asks for a save path. Source still shows the raw text.

**Last updated:** 2026-10-12 (Asia/Bangkok) — Help menu

The title bar **Help** menu has Check for updates, About Trainz Studio (matte sheet: MSTN Production since 2024, purpose, Facebook, website, email, per language), and Source code. Source code opens `https://github.com/naseno15/mstn-trainz-studio`. Check for updates opens a matte sheet, asks GitHub for the latest releases and the latest commit, and shows a spinner until that returns. Each release expands. Install update appears only when a newer tag has a Windows zip. Warn, log, about, and update sheets rise in. Switching language blurs the window, swaps the catalog, then sharpens. UI text uses Segoe UI with Leelawadee UI and Yu Gothic UI so Thai and Japanese are outline faces.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Optional GitHub update

About a second after the window is up, the app asks `https://api.github.com/repos/naseno15/mstn-trainz-studio/releases/latest` (override with `TRAINZ_UPDATE_REPO`, skip with `TRAINZ_NO_UPDATE`). A newer tag that has a `*win64.zip` asset shows a toast at the bottom-right. × dismisses it for this session. The body opens a dialog; **Install update** downloads the zip, then a hidden PowerShell helper waits for this process, copies the archive folder that contains the exe over `applicationDirPath()`, and starts that exe again. **Later** leaves the toast up. The current build is the published `v4.4.3` release, so the toast stays hidden until a higher tag exists. `check_update` covers version compare, asset pick, and the two QML files.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Packages viewer dock and text well

Clearing the queue (or removing the last CDP) clears the Viewer/Editor with it. Line numbers read `gutterLines.firstLine` (the old id was undefined, so every row painted NaN). Viewer and Editor are the same text document; the swap only flips read-only and does not rebuild an HTML copy. The Packages right dock opens level with the Finder: half of the width left after the queue column. The splitter cannot go wider than that.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Backups hide empty folders

`find_asset_backups` skips a day-folder child that is a directory with no file anywhere under it (nested empty folders count as empty). A loose file or a folder that still has a file stays in the list and in search.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Mesh Lods `.lm.txt` names

Dropping `.fbx` writes `name="….trainzmesh"` in the `.lm.txt` preview and on Save. Content Manager compiles that FBX to `.trainzmesh` on submit. `.im` stays `.im`. The mesh list is a Finder-style table (name, width, LOD tick, type). Clear selected and Clear all sit on that list. Preview and log use the same coloring as the Packages viewer. The shared right dock starts at 260px.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Mesh Studio opens .im and .fbx

`.im` with no GEOM (attachment-only, such as `cab.im`) still opens. Each ATCH point is the same RGB line triad as the corner gizmo, spun by that point's orientation. Not a mesh part. `.fbx` goes through `parse_fbx_parts` (ufbx, metres, Trainz Z-up). Bind pose only — no skinning.

**Last updated:** 2026-10-09 (Asia/Bangkok) — Mesh Studio Tab pie

Hold Tab on Preview or Settings and drag to Wireframe, Solid, Material, or Render. The wheel pops open with an overshoot, collapses on close, and the active slice eases outward while a line tracks the cursor. A short tap leaves the wheel up until a click, Esc, or Tab again. Meshes Editor and Attachs Editor use the same key for Move / Edit. Render is full lit maps; Material is albedo only; Solid and Wireframe are flat clay, and Wireframe draws edges.

**Last updated note:** crash log + CrashDialog

`src/ui/crash_report.cpp` logs Qt warnings, critical and fatal messages, `std::terminate`, and Windows SEH crashes (code, module, offset) to `%LOCALAPPDATA%\TrainzStudio\trainz_studio.log`. The log rotates once at 1 MB. `session.lock` is written at startup and removed after `app.exec()` returns. If it is still there on the next launch, `CrashDialog.qml` shows the last 80 log lines (Open log folder / Copy / OK). `check_shell` loads the dialog and fails on any QML warning. Assets Config, KUID, and Export text boxes assign `bridge.configText` / `kuidIn` / `exportIn`. The setters are not invokable, so do not call `setX()` from QML.

**Last updated note:** mesh floor grid, origin axes, mesh tree

Dropping or opening a mesh shows a glass progress sheet (read, parse, textures, scene, upload). Texture scan and decode run on one worker per core; the sheet counts how many unique maps have finished. The mesh viewport draws an XY grid on Z = 0, RGB axes through the world origin, and a corner axis triad. Face Orientation paints front faces green and back faces red. Opening a mesh loads an albedo image from beside the file (`name.texture.txt` Primary, or `name.png` / `.tga` / `*albedo*`). The left list is one table, Show | Mesh. The right dock is a labeled Mesh / Material / Textures table for the selected part. The bottom pill clears on the well that is not selected.

**Last updated note:** Assets Packages / Config / KUID / Export pages

Packages fills the three columns: the left queue takes a CDP, tzarc, zip, or folder drop; the center Finder lists assets and, after a double-click, that asset's files (folder icon vs file icon, folders grouped on top, date modified newest first, breadcrumb, config.txt). A library send indexes config.txt or config.chump and every file under that asset, including subfolders; a folder with one asset opens straight onto that file list. The right Viewer stays open and shows the clicked file with line numbers. Ctrl+S saves the file open in the editor. A Finder row keeps an amber highlight and a trailing * until that file is saved, including after you open another file. Sidebar and viewer widths stay in QML while the pointer is down. Content width is frozen and clipped for that drag, then laid out once on release. Config edits config.chump as text. KUID normalizes a paste to hex and hash-XX. Export reads a KUID list and runs TrainzUtil createCDP.

Opening Smart TrainzUtil probes the Launcher, then lists installed assets (`filterbystatus I`). The sidebar **Data** button opens the folder from `getinstallationdatapath`. **Refresh** and **Scan** run that probe again; the status line changes to “Checking Launcher…” while it runs. The Launcher must be open with Advanced debug tools on, or the status line says so and the table stays empty.

**Root:** `c:\trs22\trainz_studio_cpp\` (this repo). The Python `trainz_studio/` tree was removed; this directory is the only Trainz Studio source.  
**Exe:** `build\trainz_studio_cpp.exe` (Windows GUI — double-click does not open a terminal)  
**QML:** `ui/qml` via `QML_DIR`  
**Toolchain:** Qt `C:\Users\Naito\Qt`, MinGW `C:\Users\Naito\Qt\Tools\mingw1310_64`, CMake from Python 3.12, Ninja `Python312\Scripts\ninja.exe`  
**Configure cache:** Release, `CMAKE_PREFIX_PATH=C:\Users\Naito\Qt`, `TRAINZ_QT_PREFIX=C:/Users/Naito/Qt`

## Fast build

`cmake` and `moc` are not on the default PATH. A build without Qt `bin` and MinGW `bin` fails with `0xC0000135` (DLL not found).

Day-to-day, from `trainz_studio_cpp`:

```
powershell -File fast.ps1
```

That builds **only** `trainz_studio_cpp`. UI sources live in the `trainz_ui` object library and compile once. Do not run a bare `cmake --build build` — target `all` also links every `check_*` exe.

After a `CMakeLists.txt` change, `fast.ps1` still reconfigures if `build.ninja` exists only when you run cmake yourself. If the ninja file is already there, run cmake in `build` first, then `fast.ps1`.

One check, same PATH:

```
cmake --build build --target check_shell --parallel
.\build\check_shell.exe
```

## Boot and window

`src/main.cpp` shows a frameless boot dialog (brand, orange bar, stage line) before `ShellWindow`, then closes it when the main window is up. It is not always-on-top, so other windows can cover it. The bar glide is short (about 16–70 ms per step). Startup compiles the home chrome (title, home, menu, toast, status) and Mesh Studio. The mesh page holds a `QOpenGLWidget`; building it after the window is visible makes Windows recreate the window, so the app blinks away and back. Sounds, Engine, Assets, and TrainzUtil still compile the first time that page is opened. `check_shell` asserts at least four stage callbacks. The × on the card, Esc, and Alt+F4 abort startup immediately, including while a QML compile is blocking the UI thread, and still clear `session.lock`.

Home ↔ studio switches grab the old page and fade that pixmap on a sibling label (180ms). The effect stays off the OpenGL view. Title menus are a `Qt::Tool` window (not `Popup`) so a click outside or Esc dismisses them; open plays a short scale/fade in `MenuDrop.qml`. Traffic lights show × − + and a `GlassTip` while the cluster is hovered. Dragging the caption uses `startSystemMove`; `WM_EXITSIZEMOVE` maximizes when the cursor is on the top screen edge. Min/max window flags stay on so Windows snap still has a thick frame.

`WIN32_EXECUTABLE` is on the app target only. Check exes stay console programs so their `printf` still shows.

`prepare_qt_runtime` requests desktop OpenGL 3.3 and `QSGRendererInterface::Software` before `QApplication`. A D3D Qt Quick widget in the same window paints the transparent viewport center black, so the mesh `QOpenGLWidget` never shows through. `MeshView::paintGL` rebinds the widget FBO draw buffer to `GL_COLOR_ATTACHMENT0` (a user shadow FBO leaves it at `GL_NONE`, and Lit stays black). Env `none` clears the studio gray and skips the sky dome; the softbox stays on the reflection sampler. `check_mesh` grabs a frame of `tri.trainzmesh` and requires lit pixels.

## Layout

Mesh Lods, Texture Params, Texture Editor, and Texture Denoiser share a 260px right dock. `Texmesh::dock_width()` resets the dock when the page changes.

| Piece | Role |
|--------|------|
| `trainz_ui` | Object library: shell + studio pages. Precompiled header `src/ui/qt_pch.h` |
| `trainz_io` | Static parsers (kuid, cdp, tzarc, mesh, enginespec, wav) |
| `src/main.cpp` | Boot dialog + `ShellWindow` |
| `checks/` | One exe per area. They link `trainz_ui`; they do not recompile it |

A compile definition that only one check needs (such as `FIXTURE_DIR`) belongs on that check target, not on `trainz_ui`.

## TrainzUtil
- Library: the loading sheet waits on the Content Manager list only. Modified/Size fill in from the content index after the rows are up; author names follow from the cache. The cache stamp is a decimal string in ~/.cache/trainz_studio/tu-archive-meta.json (a JSON number cannot hold a nanosecond mtime, so a numeric stamp reopened every archive on each launch). Type codes -> names (trainz_meta.cpp category_label).
- View Detail: picks drive sidebar cards (cover, deps, credits, status). Tools: Inspect/Export/Each CDP/Tuner (-> Engine page, save commits back)/Packages (-> Assets)/Edit/Submit/Validate/Backups/GameScript. Export and Each CDP fill the right Progress list (`N of M`) the same way Validate does.
- GameScript page (nav id `encrypt`): TrainzUtil `encrypt` writes `.gse` beside `.gs` by asking the running game. Container is 16 bytes: `u32` version 2, `u32` 0, `u32` payload size, `u32` 0. Payload is a packed image under a per-byte XOR (one literal edit flips one ciphertext byte by the plaintext xor; repetitive text packs smaller first). Not chump, tzarc, or lzss. No decrypt command. Fixture pair: `checks/fixtures/gamescript/alsthom_mainlib.gs` + `.gse`.
- Install: zip/cdp sources with nested zips, staged installs, real ok/fail from TrainzUtil output.
- Check: check_trainzutil (check_meta covers labels, index, author scan).
