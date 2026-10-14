# MSTN Trainz Studio C++ — continuation handoff

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

Dropping a mesh lists `.kin` files in the same folder whose bone names are inside that mesh (`windowcab.trainzmesh` → `windowcab_scene.kin`, bone `r.fuckyou`). Play and the frame slider move a one-bone part from frame 0. A dropped `.kin` whose bones are not in the mesh is reported and not kept.

**Last updated:** 2026-10-12 (Asia/Bangkok) — attachment pick and names

Left-drag orbits even when the press lands on an attachment. Shift+click selects an attachment (brighter axes) or, if the click misses, a mesh part. Shift+click on empty space clears the attachment and the material highlight. Att names are rasterized to an image and drawn as a screen quad. QPainter on the OpenGL framebuffer flipped the glyphs.

**Last updated:** 2026-10-12 (Asia/Bangkok) — trainzmesh attachment axes

Opening a `.trainzmesh` reads the `a.*` table (same pose as an `.im` ATCH) and draws the RGB triad after the body, on top of the shell. The Atts checkbox still hides that file's points. An attachment-only `.im` is unchanged.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Config tag editor

Assets Config opens `config.txt` (drop, Open, or the library **Edit config** button) as sunk fields. Short tags sit four across. `username` and `description` take the whole row, and `description` is a tall wrapping field. A hairline splits Identity, Category, Credits, Script, Asset, and Containers. A container row drills in, so `mesh-table` → a mesh → `effects` → `texture-replacement` / `corona` / `attachment` are the same list, with the editor chosen from the parent container. KUID rows pick from the TrainzUtil library, filtered by category-class. Numbered `kuid-table` keys stay plain text. Save writes `config.txt` back when the file came from an editing folder; a library copy that is not open for edit asks for a save path. Source still shows the raw text.

**Last updated:** 2026-10-12 (Asia/Bangkok) — Help menu

The title bar **Help** menu has Check for updates, About Trainz Studio (matte sheet: MSTN Production since 2024, purpose, Facebook, website, email, per language), and Source code. Source code opens `https://github.com/naseno15/mstn-trainz-studio`. Check for updates opens a matte sheet, asks GitHub for the latest releases and the latest commit, and shows a spinner until that returns. Each release expands. Install update appears only when a newer tag has a Windows zip. Warn, log, about, and update sheets rise in. Switching language blurs the window, swaps the catalog, then sharpens. UI text uses Segoe UI with Leelawadee UI and Yu Gothic UI so Thai and Japanese are outline faces.

**Last updated:** 2026-10-11 (Asia/Bangkok) — Optional GitHub update

About a second after the window is up, the app asks `https://api.github.com/repos/naseno15/mstn-trainz-studio/releases/latest` (override with `TRAINZ_UPDATE_REPO`, skip with `TRAINZ_NO_UPDATE`). A newer tag that has a `*win64.zip` asset shows a toast at the bottom-right. × dismisses it for this session. The body opens a dialog; **Install update** downloads the zip, then a hidden PowerShell helper waits for this process, copies the archive folder that contains the exe over `applicationDirPath()`, and starts that exe again. **Later** leaves the toast up. The current build is the published `v4.3.5` release, so the toast stays hidden until a higher tag exists. `check_update` covers version compare, asset pick, and the two QML files.

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

**Root:** `c:\trs22\trainz_studio_cpp\` (this repo). Python leftovers stay in `c:\trs22\trainz_studio\`. These are separate directories. Do not junction them.  
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

## TrainzUtil parity (Python trainzutil_host.py / trainz_install.py)
- Library: the loading sheet waits on the Content Manager list only. Modified/Size fill in from the content index after the rows are up; author names follow from the cache. The cache stamp is a decimal string in ~/.cache/trainz_studio/tu-archive-meta.json (a JSON number cannot hold a nanosecond mtime, so a numeric stamp reopened every archive on each launch). Type codes -> names (trainz_meta.cpp category_label).
- View Detail: picks drive sidebar cards (cover, deps, credits, status). Tools: Inspect/Export/Each CDP/Tuner (-> Engine page, save commits back)/Packages (-> Assets)/Edit/Submit/Validate/Backups/GameScript. Export and Each CDP fill the right Progress list (`N of M`) the same way Validate does.
- GameScript page (nav id `encrypt`): TrainzUtil `encrypt` writes `.gse` beside `.gs` by asking the running game. Container is 16 bytes: `u32` version 2, `u32` 0, `u32` payload size, `u32` 0. Payload is a packed image under a per-byte XOR (one literal edit flips one ciphertext byte by the plaintext xor; repetitive text packs smaller first). Not chump, tzarc, or lzss. No decrypt command. Fixture pair: `checks/fixtures/gamescript/alsthom_mainlib.gs` + `.gse`.
- Install: zip/cdp sources with nested zips, staged installs, real ok/fail from TrainzUtil output.
- Check: check_trainzutil (check_meta covers labels, index, author scan).
