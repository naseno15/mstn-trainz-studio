# MSTN Trainz Studio C++ — continuation handoff

**Last updated:** 2026-10-11 (Asia/Bangkok) — Mesh Studio opens .im and .fbx

`.im` with no GEOM (attachment-only, such as `cab.im`) still opens. Each ATCH point is the same RGB line triad as the corner gizmo, spun by that point's orientation. Not a mesh part. `.fbx` goes through `parse_fbx_parts` (ufbx, metres, Trainz Z-up). Bind pose only — no skinning.

**Last updated:** 2026-10-09 (Asia/Bangkok) — Mesh Studio Tab pie

Hold Tab on Preview or Settings and drag to Wireframe, Solid, Material, or Render. The wheel pops open with an overshoot, collapses on close, and the active slice eases outward while a line tracks the cursor. A short tap leaves the wheel up until a click, Esc, or Tab again. Meshes Editor and Attachs Editor use the same key for Move / Edit. Render is full lit maps; Material is albedo only; Solid and Wireframe are flat clay, and Wireframe draws edges.

**Last updated note:** crash log + CrashDialog

`src/ui/crash_report.cpp` logs Qt warnings, critical and fatal messages, `std::terminate`, and Windows SEH crashes (code, module, offset) to `%LOCALAPPDATA%\TrainzStudio\trainz_studio.log`. The log rotates once at 1 MB. `session.lock` is written at startup and removed after `app.exec()` returns. If it is still there on the next launch, `CrashDialog.qml` shows the last 80 log lines (Open log folder / Copy / OK). `check_shell` loads the dialog and fails on any QML warning. Assets Config, KUID, and Export text boxes assign `bridge.configText` / `kuidIn` / `exportIn`. The setters are not invokable, so do not call `setX()` from QML.

**Last updated note:** mesh floor grid, origin axes, mesh tree

Dropping or opening a mesh shows a glass progress sheet (read, parse, textures, scene, upload). Texture scan and decode run on one worker per core; the sheet counts how many unique maps have finished. The mesh viewport draws an XY grid on Z = 0, RGB axes through the world origin, and a corner axis triad. Face Orientation paints front faces green and back faces red. Opening a mesh loads an albedo image from beside the file (`name.texture.txt` Primary, or `name.png` / `.tga` / `*albedo*`). The left list is one table, Show | Mesh. The right dock is a labeled Mesh / Material / Textures table for the selected part. The bottom pill clears on the well that is not selected.

**Last updated note:** Assets Packages / Config / KUID / Export pages

Packages fills the three columns: the left queue takes a CDP, tzarc, zip, or folder drop; the center Finder lists assets and, after a double-click, that asset's files (folder icon vs file icon, folders grouped on top, date modified newest first, breadcrumb, config.txt). The right Viewer stays open and shows the clicked file with line numbers. Ctrl+S saves the file open in the editor. A Finder row keeps an amber highlight and a trailing * until that file is saved, including after you open another file. Sidebar and viewer widths stay in QML while the pointer is down. Content width is frozen and clipped for that drag, then laid out once on release. Config edits config.chump as text. KUID normalizes a paste to hex and hash-XX. Export reads a KUID list and runs TrainzUtil createCDP.

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

`src/main.cpp` shows a frameless boot dialog (brand, orange bar, stage line) before `ShellWindow`, then closes it when the main window is up. It is not always-on-top, so other windows can cover it. The bar glide is short (about 16–70 ms per step). Startup compiles only the home chrome (title, home, menu, toast, status). Mesh, Sounds, Engine, Assets, and TrainzUtil compile the first time that page is opened. `check_shell` asserts at least four stage callbacks. The × on the card, Esc, and Alt+F4 abort startup immediately, including while a QML compile is blocking the UI thread, and still clear `session.lock`.

Home ↔ studio switches grab the old page and fade that pixmap on a sibling label (180ms). The effect stays off the OpenGL view. Title menus are a `Qt::Tool` window (not `Popup`) so a click outside or Esc dismisses them; open plays a short scale/fade in `MenuDrop.qml`. Traffic lights show × − + and a `GlassTip` while the cluster is hovered. Dragging the caption uses `startSystemMove`; `WM_EXITSIZEMOVE` maximizes when the cursor is on the top screen edge. Min/max window flags stay on so Windows snap still has a thick frame.

`WIN32_EXECUTABLE` is on the app target only. Check exes stay console programs so their `printf` still shows.

`prepare_qt_runtime` requests desktop OpenGL 3.3 and `QSGRendererInterface::Software` before `QApplication`. A D3D Qt Quick widget in the same window paints the transparent viewport center black, so the mesh `QOpenGLWidget` never shows through. `MeshView::paintGL` rebinds the widget FBO draw buffer to `GL_COLOR_ATTACHMENT0` (a user shadow FBO leaves it at `GL_NONE`, and Lit stays black). Env `none` clears the studio gray and skips the sky dome; the softbox stays on the reflection sampler. `check_mesh` grabs a frame of `tri.trainzmesh` and requires lit pixels.

## Layout

Mesh Lods, Texture Params, Texture Editor, and Texture Denoiser share a 440px right dock. `Texmesh::dock_width()` resets the dock when the page changes.

| Piece | Role |
|--------|------|
| `trainz_ui` | Object library: shell + studio pages. Precompiled header `src/ui/qt_pch.h` |
| `trainz_io` | Static parsers (kuid, cdp, tzarc, mesh, enginespec, wav) |
| `src/main.cpp` | Boot dialog + `ShellWindow` |
| `checks/` | One exe per area. They link `trainz_ui`; they do not recompile it |

A compile definition that only one check needs (such as `FIXTURE_DIR`) belongs on that check target, not on `trainz_ui`.

## TrainzUtil parity (Python trainzutil_host.py / trainz_install.py)
- Library: Modified/Size from content index (original/local/editing), Author/Build via shared cache ~/.cache/trainz_studio/tu-archive-meta.json, Type codes -> names (trainz_meta.cpp category_label).
- View Detail: picks drive sidebar cards (cover, deps, credits, status). Tools: Inspect/Export/Each CDP/Tuner (-> Engine page, save commits back)/Packages (-> Assets)/Edit/Submit/Validate/Backups/Encrypt. Export and Each CDP fill the right Progress list (`N of M`) the same way Validate does.
- Install: zip/cdp sources with nested zips, staged installs, real ok/fail from TrainzUtil output.
- Check: check_trainzutil (check_meta covers labels, index, author scan).
