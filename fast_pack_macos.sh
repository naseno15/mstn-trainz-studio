#!/usr/bin/env bash
# Portable macOS pack (equivalent of TrainzStudio-*-win64.zip).
# True MinGW-style static Qt is Windows-only here; this ships a self-contained .app via macdeployqt.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
qt_prefix="${TRAINZ_QT_PREFIX:-${CMAKE_PREFIX_PATH:-$HOME/Qt/6.10.1/macos}}"
if [[ ! -d "$qt_prefix" ]]; then
  echo "Qt kit not found at $qt_prefix" >&2
  exit 1
fi
export PATH="$qt_prefix/bin:/opt/homebrew/bin:$PATH"
ver="$(sed -n 's/.*project(trainz_studio_cpp VERSION \([0-9.]*\).*/\1/p' "$root/CMakeLists.txt" | head -1)"
arch="$(uname -m)"
build="$root/build-macos-pack"
dist="$root/dist"
app="$dist/TrainzStudio.app"
zip_name="TrainzStudio-${ver}-macos-${arch}.zip"

echo "== configure (portable, no QT_PREFIX pin) =="
cmake -S "$root" -B "$build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$qt_prefix" \
  -DTRAINZ_MAC_BUNDLE=ON

echo "== build app + checks =="
checks=(
  check_boot check_cli check_formats check_shell check_update check_ve
  check_trainzutil check_engine check_sounds check_mesh check_assets
  trainz_studio_cpp
)
cmake --build "$build" --parallel "$(sysctl -n hw.ncpu)" --target "${checks[@]}"

echo "== auto test =="
fail=0
for name in check_boot check_cli check_formats check_shell check_update check_ve \
            check_trainzutil check_engine check_sounds check_mesh check_assets; do
  echo "--- $name ---"
  if ! "$build/$name"; then
    echo "FAIL $name" >&2
    fail=1
  fi
done
if [[ "$fail" -ne 0 ]]; then
  echo "checks failed — pack aborted" >&2
  exit 1
fi
echo "all checks: ok"

echo "== stage .app =="
rm -rf "$dist"
# CMake MACOSX_BUNDLE already wrote TrainzStudio.app under build/
built_app="$build/TrainzStudio.app"
if [[ ! -d "$built_app" ]]; then
  echo "missing $built_app" >&2
  exit 1
fi
mkdir -p "$dist"
cp -R "$built_app" "$app"
mkdir -p "$app/Contents/Resources/fonts"
for f in NotoSans-Regular.ttf NotoSans-Medium.ttf NotoSansThaiLooped.ttf NotoSansJP-Regular.ttf; do
  src="$root/assets/fonts/$f"
  [[ -f "$src" ]] && cp "$src" "$app/Contents/Resources/fonts/"
done
if [[ -f "$root/assets/TrainzStudio.icns" ]]; then
  cp "$root/assets/TrainzStudio.icns" "$app/Contents/Resources/TrainzStudio.icns"
  /usr/libexec/PlistBuddy -c 'Set :CFBundleIconFile TrainzStudio' "$app/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string TrainzStudio' "$app/Contents/Info.plist"
fi
# Finder launches get TRAINZ_BUNDLE so any leftover QT_PREFIX pin is skipped.
plist="$app/Contents/Info.plist"
if [[ -f "$plist" ]]; then
  /usr/libexec/PlistBuddy -c 'Add :LSEnvironment dict' "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c 'Add :LSEnvironment:TRAINZ_BUNDLE string 1' "$plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c 'Set :LSEnvironment:TRAINZ_BUNDLE 1' "$plist"
fi

echo "== macdeployqt =="
# SQL driver probes print ERROR when odbc/psql/mimer are absent — harmless; strip after deploy.
macdeployqt "$app" -always-overwrite -qmldir="$root/ui/qml" -verbose=1 || true
rm -rf "$app/Contents/PlugIns/sqldrivers"

echo "== zip =="
(
  cd "$dist"
  rm -f "$zip_name"
  ditto -c -k --sequesterRsrc --keepParent TrainzStudio.app "$zip_name"
)
# Smoke: CLI from inside the bundle
"$app/Contents/MacOS/TrainzStudio" version
"$app/Contents/MacOS/TrainzStudio" help >/dev/null

echo "ok: $dist/$zip_name"
ls -lh "$dist/$zip_name"
echo "open: open $app"
