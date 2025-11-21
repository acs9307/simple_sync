#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${DIST_DIR:-"$ROOT_DIR/dist"}"
WORK_DIR="${WORK_DIR:-"$ROOT_DIR/.pyinstaller"}"
APP_NAME="${APP_NAME:-simple-sync}"

if ! command -v python >/dev/null 2>&1; then
    echo "python is required to build the standalone binary." >&2
    exit 1
fi

if ! python - <<'PY' >/dev/null 2>&1
import importlib.util
import sys

sys.exit(0 if importlib.util.find_spec("PyInstaller") else 1)
PY
then
    echo "PyInstaller is required. Install with 'pip install simple-sync[binary]'." >&2
    exit 1
fi

mkdir -p "$DIST_DIR" "$WORK_DIR"

python -m PyInstaller \
    --clean \
    --onedir \
    --name "$APP_NAME" \
    --distpath "$DIST_DIR" \
    --workpath "$WORK_DIR" \
    --paths "$ROOT_DIR" \
    "$ROOT_DIR/scripts/pyinstaller_entry.py"

echo "Standalone binary written to $DIST_DIR/$APP_NAME/$APP_NAME"
