---
name: trainz-studio-cli
description: >-
  Run, build, and test MSTN Trainz Studio (trainz_studio_cpp) from a terminal
  without opening the GUI. Covers the headless commands on trainz_studio_cpp.exe
  (help, version, kuid, mesh, cdp, tzarc, chump, zip, texture, wav, engine, lm,
  kin), the PowerShell call pattern that waits for output and keeps the exit
  code, fast.ps1 / fast_static.ps1 builds, check_* exes, and the git push flow.
  Use when an agent must inspect a .trainzmesh/.im/.fbx/.cdp/.tzarc/.wav/
  enginespec/.lm.txt/.kin/.texture.txt from the shell, rebuild the exe, or run
  a check in trainz_studio_cpp.
---

# Trainz Studio from the terminal

**Root:** `c:\trs22\trainz_studio_cpp\` (its own git repo). For app internals
read `HANDOFF.md`. This skill is only about driving it from a shell.

## Which exe

| Exe | Built by | Notes |
|---|---|---|
| `build\trainz_studio_cpp.exe` | `powershell -File fast.ps1` | Shared Qt. Day-to-day |
| `build-static\trainz_studio_cpp.exe` | `powershell -File fast_static.ps1` | Single static exe (release zip) |

Both exes are the same program. Run `version` first. If it is older than
`TRAINZ_STUDIO_VERSION` in `CMakeLists.txt`, rebuild before you trust the
output.

## How to call it (read this first)

The exe is a **GUI-subsystem** program. A first argument that matches a command
runs headless and exits. No window, no boot dialog, no `session.lock`. Any
other argument, or none, **opens the window**, so never call it with an unknown
word.

In PowerShell, a bare `& exe mesh x` returns **before** the output arrives, and
`$LASTEXITCODE` / `cmd /c ... %ERRORLEVEL%` read 0 even on failure. Always pipe:

```powershell
$ts = "c:\trs22\trainz_studio_cpp\build\trainz_studio_cpp.exe"
& $ts mesh "D:\path\body.trainzmesh" 2>&1 | Out-String
"exit=$LASTEXITCODE"
```

The pipe makes PowerShell wait, and `$LASTEXITCODE` is then correct. In
Windows PowerShell 5.1, stderr under `2>&1` prints as a red
`NativeCommandError`. That is the exe's error line and does not mean the
command failed to run.

For separate stdout and stderr files:

```powershell
$p = Start-Process $ts -ArgumentList 'cdp','"D:\pack.cdp"' -Wait -PassThru -NoNewWindow `
  -RedirectStandardOutput "$env:TEMP\ts_out.txt" -RedirectStandardError "$env:TEMP\ts_err.txt"
$p.ExitCode
```

Quote paths that contain spaces. Inside `-ArgumentList`, use the inner `"..."`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Error. The message is on stderr (`cannot open …`, `not a kuid`, `no such entry`, `not an enginespec`, …). `texture` also exits 1 when the report has problems. `tzarc <name>` exits 1 for a binary member |
| 2 | Missing argument. Usage line on stderr |

## Commands

All commands are read-only. None of them writes or changes a file.

| Command | Prints |
|---|---|
| `help` | Usage |
| `version` | Version string |
| `kuid <kuid>` | Normalized `<kuid:a:b>` then `hash-XX` folder |
| `mesh <file.trainzmesh\|.im\|.fbx>` | `kind`, `parts N`, then `part <name> verts V tris T [type] [albedo]`. trainzmesh also prints `materials` and `attachments` with x y z |
| `cdp <file.cdp>` | Each asset: kuid, `username`, `kind`, `file <name> <size>` |
| `cdp <file.cdp> <kuid>` | That asset's config text |
| `tzarc <file.tzarc>` | `<size> <name>` per member (no inflate) |
| `tzarc <file.tzarc> <name>` | Text member contents (full path or base name) |
| `chump <file>` | config.chump as text |
| `zip <file.zip>` | `<size> <name>` per entry |
| `texture <file.texture.txt>` | Texture report (Primary found, size, keys). Exit 1 if not ok |
| `wav <file.wav>` | `rate`, `channels`, `frames`, `seconds`, then `<severity> <kind> <message>` QC findings |
| `engine <enginespec>` | Header `key=value`, `block <name> <n>`, `notch <n> points <n>` |
| `lm <file.lm.txt>` | `version`, `offset`, `calcPoint`, `meshes`, `mesh <width> <name>` |
| `kin <file.kin>` | `tick`, `bones`, `bone <name>`, `frames` |

The output is plain lines of `key value`. Parse it with `Select-String` or a
split on the first space.

Fixtures to try commands on are in `checks\fixtures\` (`tri.trainzmesh`,
`tri.im`, `tri.fbx`, `att.fbx`, `demo.cdp`, `sample.tzarc`, `chump.bin`).

## Build

`cmake` and `moc` are not on the default PATH. Without Qt `bin` and MinGW `bin`,
the build fails with `0xC0000135`. The scripts set PATH themselves:

```powershell
cd c:\trs22\trainz_studio_cpp
powershell -File fast.ps1          # build\trainz_studio_cpp.exe only
powershell -File fast_static.ps1   # build-static\ (needs tools\build_qt_static.ps1 run once)
```

Never run a bare `cmake --build build`. Target `all` links every `check_*` exe
and takes much longer. Give the build a long timeout (minutes, not seconds).

## Checks

One check per area: `check_cli`, `check_mesh`, `check_formats`, `check_assets`,
`check_sounds`, `check_engine`, `check_shell`, `check_boot`, `check_trainzutil`,
`check_update`, `check_ve`. Check exes are console programs, so a bare call
waits and returns its exit code normally.

```powershell
cd c:\trs22\trainz_studio_cpp
$env:PATH = "C:\Users\Naito\Qt\bin;C:\Users\Naito\Qt\Tools\mingw1310_64\bin;C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts;" + $env:PATH
$cmake = "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin\cmake.exe"
& $cmake --build build --target check_cli --parallel
.\build\check_cli.exe        # prints "check_cli: ok", exit 0
```

After you change `src\cli.cpp`, run `check_cli`. Run `check_shell` from
`build`. The static tree cannot load QML.

## Adding a command

1. Add the enum value, the `command_of` name, the `usage_text` line, a `cmd_*`
   function, and the `dispatch` case in `src\cli.cpp`. The parser goes in `src\io\*`.
2. Cover it in `checks\check_cli.cpp`.
3. Add it to the command list in `HANDOFF.md`, in `README.md` § Terminal, and
   in this file.

## Git

Remotes: `origin` → GitHub `naseno15/mstn-trainz-studio` (release source),
`cursor` → `origin.cursor.com/naito-wiliams/trainz-studio`. Branch `main`.

```powershell
cd c:\trs22\trainz_studio_cpp
git status -sb
git add <only the files you changed>
git commit -m "type(scope): what changed"
git push origin main
git push cursor main
```

- Stage files by name. Do not use `git add -A`. Stray untracked files sit in
  the root (empty `assets_page.cpp`, `mesh_page.h`), and `build\` is ignored.
- Commit style: `feat|fix|docs|test|build|chore(scope): …`, as in `git log`.
- Do not force-push. Do not push tags or releases unless asked.

## Don't

- Don't call the exe with a word that is not a command. That opens the GUI and
  leaves the agent waiting.
- Don't trust `$LASTEXITCODE` without the `| Out-String` pipe.
- Don't revive the Python `trainz_studio/` tree.
