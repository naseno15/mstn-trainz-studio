#!/usr/bin/env bash
# Launch MSTN Mesh Studio (macOS / Linux). Optional: path to .fbx/.im/.trainzmesh
set -euo pipefail
CALLER_PWD="$(pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating venv + installing deps…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$HERE/requirements.txt"
fi
if ! command -v assimp >/dev/null 2>&1; then
  echo "warning: assimp not on PATH — FBX load will fail (brew install assimp)" >&2
fi
ARGS=()
for a in "$@"; do
  if [[ "$a" != /* && -e "$CALLER_PWD/$a" ]]; then
    ARGS+=("$CALLER_PWD/$a")
  elif [[ "$a" != /* && -e "$HERE/$a" ]]; then
    ARGS+=("$HERE/$a")
  else
    ARGS+=("$a")
  fi
done
cd "$HERE/.."
echo "trainz_studio: launching…"
exec "$VENV/bin/python" -m trainz_studio ${ARGS[@]+"${ARGS[@]}"}
