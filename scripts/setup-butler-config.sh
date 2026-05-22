#!/usr/bin/env bash
# Copy docs/config/config.yaml.example → ~/.butler/config.yaml if missing.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
EXAMPLE="$ROOT/docs/config/config.yaml.example"
TARGET="$BUTLER_HOME/config.yaml"

mkdir -p "$BUTLER_HOME"
if [[ -f "$TARGET" ]]; then
  echo "Already exists: $TARGET"
  exit 0
fi
if [[ ! -f "$EXAMPLE" ]]; then
  echo "Missing example: $EXAMPLE" >&2
  exit 1
fi
cp "$EXAMPLE" "$TARGET"
echo "Created $TARGET from config.yaml.example"
echo "Edit gateway / auxiliary sections as needed; env vars still override."
echo "OCR fallback: pip install -e \".[wechat-ocr]\" (plus system tesseract + chi_sim)"
