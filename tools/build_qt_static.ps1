# One-time: build static Qt 6.11.2 (qtbase + qtshadertools + qtdeclarative) into $prefix.
# Usage: powershell -File tools\build_qt_static.ps1   (30-60 min, uses all cores)
$ErrorActionPreference = "Stop"
$ver = "6.11.2"
$work = "C:\qt_static_build"
$prefix = "C:\Users\Naito\QtStatic"
$mingw = "C:\Users\Naito\Qt\Tools\mingw1310_64\bin"
$cmakeBin = "C:\Users\Naito\AppData\Roaming\Python\Python312\site-packages\cmake\data\bin"
$ninja = "C:\Users\Naito\AppData\Roaming\Python\Python312\Scripts"
$env:PATH = "$mingw;$cmakeBin;$ninja;$env:PATH"
New-Item -ItemType Directory -Force $work | Out-Null
Set-Location $work
$base = "https://download.qt.io/official_releases/qt/6.11/$ver/submodules"

foreach ($m in "qtbase", "qtshadertools", "qtdeclarative") {
    $dir = "$m-everywhere-src-$ver"
    if (-not (Test-Path $dir)) {
        $tar = "$dir.tar.xz"
        if (-not (Test-Path $tar)) { Invoke-WebRequest "$base/$tar" -OutFile $tar }
        tar -xf $tar
    }
    $bd = "build-$m"
    if (-not (Test-Path "$bd\.done")) {
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
    }
}
"DONE -> $prefix"
