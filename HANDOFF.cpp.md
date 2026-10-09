# MSTN Trainz Studio C++ — continuation handoff

**Last updated:** 2026-10-09 (Asia/Bangkok) — GUI exe, boot dialog, fast build

**Root:** `trainz_studio/cpp/` (git). `c:\trs22\trainz_studio_cpp\` is a junction to that folder.  
**Exe:** `build\trainz_studio_cpp.exe` (Windows GUI — double-click does not open a terminal)  
**QML:** `trainz_studio/ui/qml` via `QML_DIR`  
**Toolchain:** Qt `C:\Users\Naito\Qt`, MinGW `C:\Users\Naito\Qt\Tools\mingw1310_64`, CMake from Python 3.12, Ninja `Python312\Scripts\ninja.exe`  
**Configure cache:** Release, `CMAKE_PREFIX_PATH=C:\Users\Naito\Qt`, `TRAINZ_QT_PREFIX=C:/Users/Naito/Qt`

Python studio handoff stays in `trainz_studio/HANDOFF.md`. This file is the C++ port only.

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

`src/main.cpp` shows a frameless boot dialog (brand, orange bar, stage line) before `ShellWindow`, then closes it when the main window is up. Stages are reported from the shell constructor (`Starting…`, `Chrome`, `Studios`, `Ready`). `check_shell` asserts at least four stage callbacks.

Home ↔ studio switches grab the old page and fade that pixmap on a sibling label (180ms). The effect stays off the OpenGL view. Title menus are a `Qt::Tool` window (not `Popup`) so a click outside or Esc dismisses them; open plays a short scale/fade in `MenuDrop.qml`. Traffic lights show × − + and a `GlassTip` while the cluster is hovered. Dragging the caption uses `startSystemMove`; `WM_EXITSIZEMOVE` maximizes when the cursor is on the top screen edge. Min/max window flags stay on so Windows snap still has a thick frame.

`WIN32_EXECUTABLE` is on the app target only. Check exes stay console programs so their `printf` still shows.

## Layout

| Piece | Role |
|--------|------|
| `trainz_ui` | Object library: shell + studio pages. Precompiled header `src/ui/qt_pch.h` |
| `trainz_io` | Static parsers (kuid, cdp, tzarc, mesh, enginespec, wav) |
| `src/main.cpp` | Boot dialog + `ShellWindow` |
| `checks/` | One exe per area. They link `trainz_ui`; they do not recompile it |

A compile definition that only one check needs (such as `FIXTURE_DIR`) belongs on that check target, not on `trainz_ui`.
