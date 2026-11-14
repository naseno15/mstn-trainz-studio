# macOS build

Native macOS build of Trainz Studio (same studios as Windows, minus Content Manager).

## Dev build

```bash
./fast.sh
# → build-macos/trainz_studio_cpp
```

## Portable pack (like win64 zip)

True MinGW-style static Qt is Windows-only. On macOS the ready-to-use pack is a self-contained `.app` (Qt frameworks inside) zipped the same way as the Windows release:

```bash
./fast_pack_macos.sh
# runs every check_*, then macdeployqt, then:
#   dist/TrainzStudio.app
#   dist/TrainzStudio-<ver>-macos-<arch>.zip
```

Open: `open dist/TrainzStudio.app`  
Needs Qt 6 at `TRAINZ_QT_PREFIX` / `CMAKE_PREFIX_PATH` (default `$HOME/Qt/6.10.1/macos`) only on the build machine — end users do not install Qt.

## What works

Mesh Studio · Sounds Studio (AudioQueue playback) · Engine Tuner · Assets Tools · Texture & Mesh Lods · headless CLI

## Disabled on macOS (Windows-only)

| Feature | Why |
|---------|-----|
| **TrainzUtil** studio (home card + View menu) | Needs Trainz Launcher + `TrainzUtil.exe` |
| Assets **Export createCDP** | Calls TrainzUtil |
| Config **KUID library picker** | Reads TrainzUtil library |
| In-app **Install update** | Ships `*win64.zip` + PowerShell helper |

Edit CDP / config / mesh / wav / texture offline still works. Install, validate, encrypt, createCDP stay on Windows Trainz.
