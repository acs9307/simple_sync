#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

echo "Resolving version from latest git tag..."
python "$ROOT_DIR/scripts/apply_version_from_tag.py" --repo "$ROOT_DIR"

echo "Building sdist and wheel..."
(cd -- "$ROOT_DIR" && python -m build --outdir "$ROOT_DIR/dist")

echo "Release artifacts written to $ROOT_DIR/dist"
