# Single static exe -> build-static\trainz_studio_cpp.exe (needs tools\build_qt_static.ps1 done once).
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

$qt = Resolve-FirstExisting @(
    $env:TRAINZ_QT_STATIC,
    $userQtStatic,
    "D:\QtStatic",
    "C:\Users\Naito\QtStatic"
)
$mingw = Resolve-FirstExisting @(
    $env:TRAINZ_MINGW_BIN,
    (Join-Path $userQt "Tools\mingw1310_64\bin"),
    "D:\Qt\Tools\mingw1310_64\bin",
    "C:\Users\Naito\Qt\Tools\mingw1310_64\bin"
)
$cmake = Resolve-FirstExisting @(
    (Join-Path $pyScripts "cmake.exe"),
    "C:\Program Files\CMake\bin\cmake.exe",
    "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin\cmake.exe"
)
if (-not $qt) { throw "Static Qt not found. Run tools\build_qt_static.ps1 first." }
if (-not $mingw) { throw "MinGW bin not found." }
if (-not $cmake) { throw "cmake.exe not found." }

$env:PATH = "$mingw;$pyScripts;" + $env:PATH
$build = Join-Path $root "build-static"
if (-not (Test-Path (Join-Path $build "build.ninja"))) {
    & $cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$qt" -DTRAINZ_STATIC=ON "-DCMAKE_C_COMPILER=gcc" "-DCMAKE_CXX_COMPILER=g++"
    if ($LASTEXITCODE) { throw "cmake configure failed" }
}
& $cmake --build $build --target trainz_studio_cpp --parallel $env:NUMBER_OF_PROCESSORS
if ($LASTEXITCODE) { throw "cmake build failed" }
