# Incremental app build. Compiles trainz_studio_cpp only — not the check exes.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PATH = "C:\Users\Naito\Qt\bin;C:\Users\Naito\Qt\Tools\mingw1310_64\bin;C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts;" + $env:PATH
$cmake = "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin\cmake.exe"
$build = Join-Path $root "build"
if (-not (Test-Path (Join-Path $build "build.ninja"))) {
    & $cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:\Users\Naito\Qt -DTRAINZ_QT_PREFIX=C:/Users/Naito/Qt -DCMAKE_CXX_COMPILER_LAUNCHER="C:/Users/Naito/AppData/Local/Microsoft/WinGet/Packages/Ccache.Ccache_Microsoft.Winget.Source_8wekyb3d8bbwe/ccache-4.14.1-windows-x86_64/ccache.exe"
    # ponytail: unity build tried; clashes (duplicate anon lower_copy in src/io), so off
}
& $cmake --build $build --target trainz_studio_cpp --parallel $env:NUMBER_OF_PROCESSORS
# deploy only once (Qt DLLs don't change between builds)
if (-not (Test-Path (Join-Path $build "Qt6Core.dll"))) {
    & "C:\Users\Naito\Qt\bin\windeployqt.exe" --release --compiler-runtime --qmldir (Join-Path $root "ui\qml") (Join-Path $build "trainz_studio_cpp.exe")
}
