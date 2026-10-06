#!/usr/bin/env bash
# Launch IM Attachment Editor (Tk UI). Optional: path to .im
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
cd "$REPO"
exec python3 -m trainz_studio.lib.im_editor "$@"
