# Incremental app build. Compiles trainz_studio_cpp only — not the check exes.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PATH = "C:\Users\Naito\Qt\bin;C:\Users\Naito\Qt\Tools\mingw1310_64\bin;C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts;" + $env:PATH
$cmake = "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin\cmake.exe"
$build = Join-Path $root "build"
if (-not (Test-Path (Join-Path $build "build.ninja"))) {
    & $cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:\Users\Naito\Qt -DTRAINZ_QT_PREFIX=C:/Users/Naito/Qt
}
& $cmake --build $build --target trainz_studio_cpp --parallel
& "C:\Users\Naito\Qt\bin\windeployqt.exe" --release --compiler-runtime (Join-Path $build "trainz_studio_cpp.exe")
