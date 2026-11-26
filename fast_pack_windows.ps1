# Portable Windows pack (TrainzStudio-*-win64.zip) — static single exe, like fast_pack_macos.sh.
# Needs: MinGW + static Qt (tools\build_qt_static.ps1 once), cmake, ninja.
# Usage:
#   powershell -File fast_pack_windows.ps1
#   powershell -File fast_pack_windows.ps1 -Upload   # attach zip to GitHub release for this version
param(
    [switch]$Upload,
    [switch]$SkipChecks,
    [string]$QtStatic = "",
    [string]$MingwBin = "",
    [string]$Tag = ""
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScripts = Join-Path $env:APPDATA "Python\Python312\Scripts"
$userQt = Join-Path $env:USERPROFILE "Qt"
$userQtStatic = Join-Path $env:USERPROFILE "QtStatic"

function Resolve-FirstExisting([string[]]$candidates) {
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path }
    }
    return $null
}

if (-not $QtStatic) {
    $QtStatic = Resolve-FirstExisting @(
        $env:TRAINZ_QT_STATIC,
        $userQtStatic,
        "D:\QtStatic",
        "C:\Users\Naito\QtStatic"
    )
}
if (-not $MingwBin) {
    $MingwBin = Resolve-FirstExisting @(
        $env:TRAINZ_MINGW_BIN,
        (Join-Path $userQt "Tools\mingw1310_64\bin"),
        "D:\Qt\Tools\mingw1310_64\bin",
        "C:\Users\Naito\Qt\Tools\mingw1310_64\bin"
    )
}

$cmake = Resolve-FirstExisting @(
    (Join-Path $pyScripts "cmake.exe"),
    "C:\Program Files\CMake\bin\cmake.exe",
    (Get-Command cmake -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
)
$ninja = Resolve-FirstExisting @(
    (Join-Path $pyScripts "ninja.exe"),
    (Get-Command ninja -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
)

if (-not $QtStatic -or -not (Test-Path (Join-Path $QtStatic "lib\cmake\Qt6\Qt6Config.cmake"))) {
    throw "Static Qt not found. Set TRAINZ_QT_STATIC or run: powershell -File tools\build_qt_static.ps1"
}
if (-not $MingwBin -or -not (Test-Path (Join-Path $MingwBin "g++.exe"))) {
    throw "MinGW bin not found. Set TRAINZ_MINGW_BIN or install tools_mingw1310 (aqt)."
}
if (-not $cmake) { throw "cmake.exe not found" }
if (-not $ninja) { throw "ninja.exe not found" }

$env:PATH = "$MingwBin;$pyScripts;$env:PATH"
$verLine = Select-String -Path (Join-Path $root "CMakeLists.txt") -Pattern 'project\(trainz_studio_cpp VERSION ([0-9.]+)' | Select-Object -First 1
if (-not $verLine) { throw "cannot read version from CMakeLists.txt" }
$ver = $verLine.Matches[0].Groups[1].Value
if (-not $Tag) { $Tag = "v$ver" }

$build = Join-Path $root "build-static"
$dist = Join-Path $root "dist"
$zipName = "TrainzStudio-$ver-win64.zip"
$zipPath = Join-Path $dist $zipName
$stage = Join-Path $dist "win64-stage"

Write-Host "== configure (TRAINZ_STATIC) =="
& $cmake -S $root -B $build -G Ninja `
    -DCMAKE_BUILD_TYPE=Release `
    "-DCMAKE_PREFIX_PATH=$QtStatic" `
    -DTRAINZ_STATIC=ON `
    "-DCMAKE_C_COMPILER=gcc" `
    "-DCMAKE_CXX_COMPILER=g++"
if ($LASTEXITCODE) { throw "cmake configure failed" }

$targets = @(
    "check_boot", "check_cli", "check_formats", "check_shell", "check_update", "check_ve",
    "check_trainzutil", "check_engine", "check_sounds", "check_mesh", "check_assets",
    "trainz_studio_cpp"
)
if ($SkipChecks) { $targets = @("trainz_studio_cpp") }

Write-Host "== build =="
& $cmake --build $build --parallel $env:NUMBER_OF_PROCESSORS --target @targets
if ($LASTEXITCODE) { throw "cmake build failed" }

if (-not $SkipChecks) {
    Write-Host "== auto test =="
    $fail = 0
    foreach ($name in @(
        "check_boot", "check_cli", "check_formats", "check_shell", "check_update", "check_ve",
        "check_trainzutil", "check_engine", "check_sounds", "check_mesh", "check_assets"
    )) {
        Write-Host "--- $name ---"
        $exe = Join-Path $build "$name.exe"
        & $exe 2>&1 | Out-String | Write-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAIL $name" -ForegroundColor Red
            $fail = 1
        }
    }
    if ($fail -ne 0) { throw "checks failed — pack aborted" }
    Write-Host "all checks: ok"
}

$appExe = Join-Path $build "trainz_studio_cpp.exe"
if (-not (Test-Path $appExe)) { throw "missing $appExe" }

Write-Host "== stage + zip =="
New-Item -ItemType Directory -Force $dist | Out-Null
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item $appExe (Join-Path $stage "trainz_studio_cpp.exe")
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host "== smoke =="
$smoke = & $appExe version 2>&1 | Out-String
$smoke = $smoke.Trim()
Write-Host "version: $smoke"
if ($smoke -notmatch [regex]::Escape($ver)) {
    throw "version mismatch: exe='$smoke' expected contains '$ver'"
}
& $appExe help 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "help failed" }

Write-Host "ok: $zipPath"
Get-Item $zipPath | Format-List FullName, Length, LastWriteTime

if ($Upload) {
    Write-Host "== upload $zipName -> release $Tag =="
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        throw "gh CLI not found. Install GitHub CLI, then: gh auth login"
    }
    & gh release view $Tag --repo naseno15/mstn-trainz-studio 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & gh release create $Tag --repo naseno15/mstn-trainz-studio --title $Tag --notes "Trainz Studio $ver"
        if ($LASTEXITCODE) { throw "gh release create failed" }
    }
    & gh release upload $Tag $zipPath --repo naseno15/mstn-trainz-studio --clobber
    if ($LASTEXITCODE) { throw "gh release upload failed" }
    Write-Host "uploaded: https://github.com/naseno15/mstn-trainz-studio/releases/tag/$Tag"
}
