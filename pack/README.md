# Pack / ship (PyInstaller onefile)

```
trainz_studio/
  pack/
    entry.py              # freeze entry
    trainz_studio.spec    # Analysis / EXE
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
trainz_studio\dist\MSTN_TrainzStudio.exe
```

onefile layout. Fonts + logo + Assimp DLL are bundled; Poly Haven HDRIs are **not** (re-fetch with `python -m trainz_studio.scripts.fetch_hdris`).

## Notes

- CuPy / CUDA bake is **not** frozen (multi‑GB). Use source + `cupy-cuda12x` for GPU lamp bake; the exe uses the threaded CPU bake path sized by `util/hw.py`.
- Runtime auto-tunes: BLAS threads, texture/bake workers, ABOVE_NORMAL process priority, desktop OpenGL.
- Never commit `dist/` / `build/` into the repo. Ship the exe via GitHub Releases.

## Windows shell (Open / Preview pane)

After building the exe (or for source with `-Source`):

```bat
powershell -ExecutionPolicy Bypass -File pack\shell\register.ps1
```

Use `-Source` to bind Explorer Open/Preview to the venv + `python -m trainz_studio` (cwd = repo root).
