# Rebuild trainz_studio history as many fine-grained commits (local only).
$ErrorActionPreference = "Stop"
Set-Location "c:\trs22\trainz_studio"

$authorName = "Naito"
$authorEmail = "naito@users.noreply.github.com"
$env:GIT_AUTHOR_NAME = $authorName
$env:GIT_AUTHOR_EMAIL = $authorEmail
$env:GIT_COMMITTER_NAME = $authorName
$env:GIT_COMMITTER_EMAIL = $authorEmail

# Preserve remotes
$remotes = @{}
git remote | ForEach-Object {
  $n = $_
  $remotes[$n] = @{
    fetch = (git remote get-url $n)
    push  = (git remote get-url --push $n)
  }
}

# Snapshot working tree outside .git (or reuse TRAINZ_SNAP)
if ($env:TRAINZ_SNAP -and (Test-Path $env:TRAINZ_SNAP)) {
  $snap = $env:TRAINZ_SNAP
} else {
  $stamp = Get-Date -Format "yyyyMMddHHmmss"
  $snap = Join-Path $env:TEMP "trainz_studio_snap_$stamp"
  New-Item -ItemType Directory -Path $snap | Out-Null
  git ls-files | ForEach-Object {
    $dst = Join-Path $snap $_
    $dir = Split-Path $dst -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -Force $_ $dst
  }
}

# Nuke git and re-init
Remove-Item -Recurse -Force .git
git init -b main

function C([string]$msg, [string[]]$paths) {
  $existing = @()
  foreach ($p in $paths) {
    $src = Join-Path $snap $p
    if (-not (Test-Path $src)) { Write-Host "MISSING $p"; continue }
    $dst = Join-Path (Get-Location) $p
    $dir = Split-Path $dst -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -Recurse -Force $src $dst
    git add -- $p
    $existing += $p
  }
  if (-not $existing) { return }
  git -c user.name=$authorName -c user.email=$authorEmail commit -m $msg | Out-Null
  Write-Host ("{0:D3} {1}" -f (++$script:n), $msg)
}

$script:n = 0

# —— scaffold ——
C "chore: ignore venv cache build artifacts and HDRI binaries" @(".gitignore")
C "chore: pin Python dependencies for Trainz Studio" @("requirements.txt")
C "docs: introduce MSTN Trainz Studio README" @("README.md")
C "feat: package root metadata and REPO_ROOT helpers" @("__init__.py")
C "feat: python -m trainz_studio entrypoint" @("__main__.py")
C "feat: Windows silent launch via start.bat" @("start.bat")
C "feat: Windows silent launch via start.vbs" @("start.vbs")
C "feat: Windows console debug launcher" @("start_debug.bat")
C "feat: POSIX start.sh launcher" @("start.sh")

# —— util ——
C "feat(util): package init for host helpers" @("util/__init__.py")
C "feat(util): CPU worker caps BLAS and desktop GL hints" @("util/hw.py")

# —— io core (mesh studio foundation) ——
C "feat(io): package init" @("io/__init__.py")
C "feat(io): Scene model for meshes materials attachments" @("io/scene.py")
C "feat(io): Assimp DLL discovery for FBX load" @("io/assimp_dll.py")
C "feat(io): mesh loaders for trainzmesh FBX and IM" @("io/loaders.py")
C "feat(io): texture decode cache for viewport maps" @("io/texcache.py")
C "feat(io): mesh meta two-sided sidecar writer" @("io/mesh_meta.py")
C "feat(io): animation stub helpers" @("io/anim.py")
C "feat(io): unlimited undo redo snapshot history" @("io/history.py")
C "feat(io): MTZS project save open and crash recover" @("io/project.py")
C "feat(io): tzMF binary material and attachment edit" @("io/tzmf_edit.py")

# —— libs internalized ——
C "feat(lib): internal libs package root" @("lib/__init__.py")
C "feat(lib/trainzmesh): package init" @("lib/trainzmesh_viewer/__init__.py")
C "feat(lib/trainzmesh): module entrypoint" @("lib/trainzmesh_viewer/__main__.py")
C "feat(lib/trainzmesh): fast tzMF binary parser" @("lib/trainzmesh_viewer/parser.py")
C "feat(lib/trainzmesh): texture path resolve helpers" @("lib/trainzmesh_viewer/textures.py")
C "feat(lib/trainzmesh): standalone viewer shell" @("lib/trainzmesh_viewer/viewer.py")
C "feat(lib/im): package init" @("lib/im_editor/__init__.py")
C "feat(lib/im): module entrypoint" @("lib/im_editor/__main__.py")
C "feat(lib/im): ATCH parse edit and save core" @("lib/im_editor/core.py")
C "feat(lib/im): CLI for attachment ops" @("lib/im_editor/cli.py")
C "feat(lib/im): optional Tk app shell" @("lib/im_editor/app.py")
C "feat(lib/im): shell launcher" @("lib/im_editor/start.sh")
C "feat(lib/engine): package init" @("lib/engine_tuner/__init__.py")
C "feat(lib/engine): module entrypoint" @("lib/engine_tuner/__main__.py")
C "feat(lib/engine): enginespec config_io read write" @("lib/engine_tuner/config_io.py")
C "feat(lib/engine): TE physics and Davis helpers" @("lib/engine_tuner/physics.py")
C "feat(lib/engine): throttle notch rounding" @("lib/engine_tuner/throttle_round.py")
C "feat(lib/engine): autotune TEE generator" @("lib/engine_tuner/autotune.py")
C "feat(lib/engine): standalone tuner app" @("lib/engine_tuner/app.py")
C "feat(lib/engine): library self-check" @("lib/engine_tuner/check.py")
C "feat(lib/engine): Windows run.bat launcher" @("lib/engine_tuner/run.bat")
C "feat(lib/engine): PowerShell run.ps1 launcher" @("lib/engine_tuner/run.ps1")

# —— render + lamps ——
C "feat(render): package init" @("render/__init__.py")
C "feat(render): environment lighting helpers" @("render/env.py")
C "feat(render): HDRI load and IBL setup" @("render/hdri.py")
C "feat(render): OpenGL View3D Z-up PBR viewport" @("render/view3d.py")
C "feat(lamps): package init" @("lamps/__init__.py")
C "feat(lamps): path-trace lamp bake to albedo" @("lamps/bake.py")

# —— audio / sounds pipeline ——
C "feat(audio): package init" @("audio/__init__.py")
C "feat(audio): ffmpeg path config" @("audio/ffmpeg_cfg.py")
C "feat(audio): WAV and ffmpeg decode to mono 44k1" @("audio/decode.py")
C "feat(audio): loop seam classify heuristics" @("audio/classify.py")
C "feat(audio): loop QC metrics" @("audio/loop_qc.py")
C "feat(audio): loop fix level-match exporter" @("audio/loop_fix.py")
C "feat(audio): WAV export helper" @("audio/export_wav.py")

# —— UI chrome foundation ——
C "feat(ui): package init" @("ui/__init__.py")
C "feat(ui): dark light theme QSS and palette" @("ui/theme.py")
C "feat(ui): frost glass frame grab and tint" @("ui/frost.py")
C "feat(ui): hub reveal hover bubble and motion" @("ui/motion.py")
C "feat(ui): floating capsule chrome shared bars" @("ui/float_chrome.py")
C "feat(ui): title bar chrome helpers" @("ui/title_chrome.py")
C "feat(ui): Material Icons apply helpers" @("ui/icons.py")
C "feat(ui): smooth scroll and coast for lists" @("ui/smooth_scroll.py")
C "feat(ui): painted table row radius chrome" @("ui/table_chrome.py")
C "feat(ui): boot frost overlay before MainWindow" @("ui/boot.py")
C "feat(ui): glass crash dialog and fault log" @("ui/crash_dialog.py")
C "feat(ui): HOME hub cards drop zone and glass" @("ui/home.py")
C "feat(ui): MainWindow shell studios and theme" @("ui/app.py")

# —— Mesh Studio UI ——
C "feat(ui): MeshEditor-style property trees" @("ui/mesh_prop_tree.py")
C "feat(ui): Editor dock Attachments and Meshes" @("ui/editor.py")
C "feat(ui): fast mesh preview window modes" @("ui/mesh_preview.py")
C "feat(ui): TrainzScript code edit find replace" @("ui/code_edit.py")

# —— Sounds Studio UI ——
C "feat(ui/sounds): package init" @("ui/sounds/__init__.py")
C "feat(ui/sounds): waveform widget" @("ui/sounds/waveform.py")
C "feat(ui/sounds): audio player loop controls" @("ui/sounds/player.py")
C "feat(ui/sounds): Track A to B transition sim" @("ui/sounds/track_sim.py")
C "feat(ui/sounds): Sounds Studio host UI" @("ui/sounds/studio.py")

# —— Engine Studio UI ——
C "feat(ui/engine): package init" @("ui/engine/__init__.py")
C "feat(ui/engine): pressure unit conversions" @("ui/engine/pressure.py")
C "feat(ui/engine): throttle notch table and TE graph" @("ui/engine/throttle_panel.py")
C "feat(ui/engine): autotune dialog" @("ui/engine/autotune_dialog.py")
C "feat(ui/engine): frost sidebar Save Undo" @("ui/engine/sidebar.py")
C "feat(ui/engine): bottom nav Tuner Sim Params" @("ui/engine/nav.py")
C "feat(ui/engine): Engine Tuner studio hub" @("ui/engine/studio.py")

# —— Assets IO (native tools) ——
C "feat(io): CDP LZSS decompress and level-0 pack" @("io/cdp_lzss.py")
C "feat(io): CDP pack extract browse and delete" @("io/cdp.py")
C "feat(io): TZarc v1 v2 read write" @("io/tzarc.py")
C "feat(io): config.chump expand and pack" @("io/chump.py")
C "feat(io): KUID UUUVNNNN hash helpers" @("io/kuid_bin.py")
C "feat(io): texture.txt format and write" @("io/texture.py")
C "feat(io): lm.txt parse and write" @("io/lm.py")
C "feat(io): image prep resize to _prep folder" @("io/image_prep.py")
C "feat(io): VE39 solid texture scan and fix" @("io/ve39.py")

# —— Assets UI ——
C "feat(ui/assets): package init" @("ui/assets/__init__.py")
C "feat(ui/assets): KUID normalize UI helpers" @("ui/assets/kuid.py")
C "feat(ui/assets): Packages Finder Viewer Editor" @("ui/assets/packages.py")
C "feat(ui/assets): native sidebar actions" @("ui/assets/sidebar.py")
C "feat(ui/assets): Packages Config Texture Mesh nav" @("ui/assets/nav.py")
C "feat(ui/assets): Assets Tools studio hub" @("ui/assets/studio.py")

# —— i18n ——
C "feat(i18n): package exports t and g" @("ui/i18n/__init__.py")
C "feat(i18n): language core and QSettings" @("ui/i18n/core.py")
C "feat(i18n): English key table" @("ui/i18n/keys_en.py")
C "feat(i18n): English catalog" @("ui/i18n/catalog_en.py")
C "feat(i18n): Thai catalog" @("ui/i18n/catalog_th.py")
C "feat(i18n): Japanese catalog" @("ui/i18n/catalog_ja.py")
C "feat(i18n): Indonesian catalog" @("ui/i18n/catalog_id.py")
C "feat(i18n): Noto font swap per language" @("ui/i18n/fonts.py")
C "feat(i18n): retranslate snapshot apply" @("ui/i18n/retranslate.py")
C "feat(i18n): VE39 glossary strings" @("ui/i18n/glossary_ve.py")
C "chore(i18n): extract English keys helper" @("ui/i18n/_extract_en_keys.py")
C "chore(i18n): run extract helper" @("ui/i18n/_run_extract.py")
C "chore(i18n): filter keys helper" @("ui/i18n/_filter_keys.py")
C "chore(i18n): add language keys helper" @("ui/i18n/_add_lang_keys.py")
C "chore(i18n): patch language keys helper" @("ui/i18n/_patch_lang_keys.py")
C "chore(i18n): patch HOME strings helper" @("ui/i18n/_patch_home.py")
C "chore(i18n): fix Indonesian menus helper" @("ui/i18n/_fix_id_menus.py")

# —— pack / ship ——
C "docs(pack): PyInstaller and shell notes" @("pack/README.md")
C "feat(pack): frozen entrypoint for onedir exe" @("pack/entry.py")
C "feat(pack): trainz_studio PyInstaller spec" @("pack/trainz_studio.spec")
C "feat(pack): legacy mesh_studio spec example" @("pack/mesh_studio.spec.example")
C "feat(pack): Windows build.bat for ship" @("pack/build.bat")
C "docs(pack/shell): Explorer preview registration" @("pack/shell/README.md")
C "feat(pack/shell): MeshPreviewHandler C# stub" @("pack/shell/MeshPreviewHandler.cs")
C "feat(pack/shell): register Open and Quick Preview" @("pack/shell/register.ps1")
C "feat(pack/shell): register.bat wrapper" @("pack/shell/register.bat")
C "feat(pack/shell): unregister shell hooks" @("pack/shell/unregister.ps1")

# —— checks / docs ——
C "test: package smoke check suite" @("check.py")
C "chore: enginespec CDP debug helper" @("_check_enginespec_cdp.py")
C "chore: mesh stage debug helper" @("_check_mesh_stage.py")
C "docs: continuation HANDOFF for agents" @("HANDOFF.md")

# —— assets ——
C "assets: font license NOTICE" @("assets/fonts/NOTICE.txt")
C "assets: Material Icons font" @("assets/fonts/MaterialIcons-Regular.ttf")
C "assets: Noto Sans Regular" @("assets/fonts/NotoSans-Regular.ttf")
C "assets: Noto Sans Medium" @("assets/fonts/NotoSans-Medium.ttf")
C "assets: Noto Sans SemiBold" @("assets/fonts/NotoSans-SemiBold.ttf")
C "assets: Noto Sans Bold" @("assets/fonts/NotoSans-Bold.ttf")
C "assets: Noto Sans Thai Looped" @("assets/fonts/NotoSansThaiLooped.ttf")
C "assets: Noto Sans JP Regular" @("assets/fonts/NotoSansJP-Regular.ttf")
C "assets: Noto Sans JP Bold" @("assets/fonts/NotoSansJP-Bold.ttf")
C "assets: MSTN logo mark" @("assets/mstn_logo_white.png")
C "assets: HDRI folder placeholder" @("assets/hdri/.gitkeep")
C "docs(assets): HDRI fetch instructions" @("assets/hdri/README.md")
C "feat(scripts): package init" @("scripts/__init__.py")
C "feat(scripts): Poly Haven HDRI fetch script" @("scripts/fetch_hdris.py")

# —— fixtures ——
C "fixtures: README for sample assets" @("fixtures/README.txt")
C "fixtures: sample albedo texture.txt" @("fixtures/sample_albedo.texture.txt")
C "fixtures: sample normal texture.txt" @("fixtures/sample_normal.texture.txt")
C "fixtures: bad missing texture.txt case" @("fixtures/bad_missing.texture.txt")
C "fixtures: tiny sample albedo PNG" @("fixtures/sample_albedo.png")
C "fixtures: body.trainzmesh sample" @("fixtures/body.trainzmesh")
C "fixtures: bumper.trainzmesh sample" @("fixtures/bumper.trainzmesh")
C "fixtures: bumper.fbx sample" @("fixtures/bumper.fbx")

# —— vendor ——
C "vendor: Assimp DLL for FBX preview on Windows" @("vendor/assimp/Release/assimp-vc143-mt.dll")

# catch-all
git add -A
if (git diff --cached --name-only) {
  git -c user.name=$authorName -c user.email=$authorEmail commit -m "chore: include any remaining package files"
  Write-Host ("{0:D3} catch-all" -f (++$script:n))
}

# restore remotes
foreach ($name in $remotes.Keys) {
  git remote add $name $remotes[$name].fetch
  if ($remotes[$name].push -ne $remotes[$name].fetch) {
    git remote set-url --push $name $remotes[$name].push
  }
}

Remove-Item -Recurse -Force $snap
Write-Host "==== TOTAL $($script:n) commits ===="
git rev-list --count HEAD
git log --oneline | Measure-Object | Select-Object -ExpandProperty Count
git status -sb
git remote -v
