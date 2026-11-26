# One-time: build static Qt 6.11.2 (qtbase + qtshadertools + qtdeclarative) into $prefix.
# Usage: powershell -File tools\build_qt_static.ps1   (30-60 min, uses all cores)
# Paths auto-detect Naseno_PC / Naito / D:\Qt layouts; override with TRAINZ_* env vars.
$ErrorActionPreference = "Stop"
$ver = "6.11.2"
$pyScripts = Join-Path $env:APPDATA "Python\Python312\Scripts"
$userQt = Join-Path $env:USERPROFILE "Qt"
$userHome = $env:USERPROFILE

function Resolve-FirstExisting([string[]]$candidates) {
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path }
    }
    return $null
}

$work = if ($env:TRAINZ_QT_STATIC_WORK) { $env:TRAINZ_QT_STATIC_WORK } else { "D:\qt_static_build" }
$prefix = if ($env:TRAINZ_QT_STATIC) { $env:TRAINZ_QT_STATIC } else {
    $existing = Resolve-FirstExisting @((Join-Path $userHome "QtStatic"), "D:\QtStatic", "C:\Users\Naito\QtStatic")
    if ($existing) { $existing } else { Join-Path $userHome "QtStatic" }
}
$mingw = Resolve-FirstExisting @(
    $env:TRAINZ_MINGW_BIN,
    (Join-Path $userQt "Tools\mingw1310_64\bin"),
    "D:\Qt\Tools\mingw1310_64\bin",
    "C:\Users\Naito\Qt\Tools\mingw1310_64\bin"
)
$cmakeBin = Resolve-FirstExisting @(
    $pyScripts,
    "C:\Program Files\CMake\bin",
    "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin"
)
$ninjaDir = Resolve-FirstExisting @(
    $pyScripts,
    "C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts"
)

if (-not $mingw -or -not (Test-Path (Join-Path $mingw "g++.exe"))) {
    throw "MinGW g++ not found. Install: python -m aqt install-tool windows desktop tools_mingw1310 qt.tools.win64_mingw1310 --outputdir D:\Qt"
}
if (-not $cmakeBin) { throw "cmake bin dir not found (pip install --user cmake)" }

$env:PATH = "$mingw;$cmakeBin;$ninjaDir;$env:PATH"
Write-Host "mingw=$mingw"
Write-Host "prefix=$prefix"
Write-Host "work=$work"

New-Item -ItemType Directory -Force $work | Out-Null
New-Item -ItemType Directory -Force $prefix | Out-Null
Set-Location $work
$base = "https://download.qt.io/official_releases/qt/6.11/$ver/submodules"

foreach ($m in "qtbase", "qtshadertools", "qtdeclarative") {
    $dir = "$m-everywhere-src-$ver"
    if (-not (Test-Path $dir)) {
        $tar = "$dir.tar.xz"
        if (-not (Test-Path $tar)) {
            Write-Host "download $tar"
            curl.exe -L --retry 5 --retry-delay 2 -o $tar "$base/$tar"
            if ($LASTEXITCODE) { throw "download failed: $tar" }
        }
        Write-Host "extract $tar"
        tar -xf $tar
        if ($LASTEXITCODE) { throw "extract failed: $tar" }
    }
    $bd = "build-$m"
    if (-not (Test-Path "$bd\.done")) {
        Write-Host "==== build $m ===="
        if ($m -eq "qtbase") {
            New-Item -ItemType Directory -Force $bd | Out-Null
            Set-Location $bd
            & "$work\$dir\configure.bat" -static -release -prefix $prefix -nomake examples -nomake tests -opensource -confirm-license -- -G Ninja "-DCMAKE_C_COMPILER=gcc" "-DCMAKE_CXX_COMPILER=g++" "-DQT_BUILD_TESTS=OFF"
            if ($LASTEXITCODE) { throw "configure failed" }
        } else {
            New-Item -ItemType Directory -Force $bd | Out-Null
            Set-Location $bd
            & "$prefix\bin\qt-configure-module.bat" "$work\$dir" -- -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
            if ($LASTEXITCODE) { throw "configure $m failed" }
        }
        cmake --build . --parallel $env:NUMBER_OF_PROCESSORS
        if ($LASTEXITCODE) { throw "build $m failed" }
        cmake --install .
        if ($LASTEXITCODE) { throw "install $m failed" }
        New-Item .done -ItemType File | Out-Null
        Set-Location $work
    } else {
        Write-Host "skip $m (already done)"
    }
}
"DONE -> $prefix"
