#!/usr/bin/env bash
# Incremental macOS build — trainz_studio_cpp only (not check_*).
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
qt_prefix="${TRAINZ_QT_PREFIX:-${CMAKE_PREFIX_PATH:-$HOME/Qt/6.10.1/macos}}"
if [[ ! -d "$qt_prefix" ]]; then
  echo "Qt kit not found at $qt_prefix — set TRAINZ_QT_PREFIX or CMAKE_PREFIX_PATH" >&2
  exit 1
fi
export PATH="$qt_prefix/bin:/opt/homebrew/bin:$PATH"
build="$root/build-macos"
if [[ ! -f "$build/build.ninja" ]]; then
  cmake -S "$root" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$qt_prefix" \
    -DTRAINZ_QT_PREFIX="$qt_prefix"
fi
cmake --build "$build" --target trainz_studio_cpp --parallel "$(sysctl -n hw.ncpu)"
echo "ok: $build/trainz_studio_cpp"
