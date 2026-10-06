# Pack / ship (PyInstaller onedir)

```
trainz_studio/
  pack/
    entry.py              # freeze entry
    trainz_studio.spec    # Analysis / EXE / COLLECT
    build.bat             # one-click from Windows
    README.md
```

## Build

From `c:\trs22\trainz_studio` (or double-click `pack\build.bat`):

```bat
pack\build.bat
```

Output:

```
trainz_studio\dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe
```

onedir layout (fast start vs onefile). `assets/` + Assimp DLL are bundled under `_internal\trainz_studio\`.

## Notes

- CuPy / CUDA bake is **not** frozen (multi‑GB). Use source + `cupy-cuda12x` for GPU lamp bake; the exe uses the threaded CPU bake path sized by `util/hw.py`.
- Runtime auto-tunes: BLAS threads, texture/bake workers, ABOVE_NORMAL process priority, desktop OpenGL.
- Never commit `dist/` / `build/` into the repo.

## Windows shell (Open / Preview pane)

After building the exe (or for source with `-Source`):

```bat
powershell -ExecutionPolicy Bypass -File pack\shell\register.ps1
```

Use `-Source` to bind Explorer Open/Preview to the venv + `python -m trainz_studio` (cwd = repo root).
