# Single static exe -> build-static\trainz_studio_cpp.exe (needs tools\build_qt_static.ps1 done once).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$qt = "C:\Users\Naito\QtStatic"
$env:PATH = "C:\Users\Naito\Qt\Tools\mingw1310_64\bin;C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts;" + $env:PATH
$cmake = "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin\cmake.exe"
$build = Join-Path $root "build-static"
if (-not (Test-Path (Join-Path $build "build.ninja"))) {
    & $cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$qt" -DTRAINZ_STATIC=ON -DCMAKE_CXX_COMPILER_LAUNCHER="C:/Users/Naito/AppData/Local/Microsoft/WinGet/Packages/Ccache.Ccache_Microsoft.Winget.Source_8wekyb3d8bbwe/ccache-4.14.1-windows-x86_64/ccache.exe"
}
& $cmake --build $build --target trainz_studio_cpp --parallel $env:NUMBER_OF_PROCESSORS

