#!/usr/bin/env bash
# Install tracked project skills into LingWen1/.butler/skills (gitignored runtime dir).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/projects/LingWen1/skills"
DST="$ROOT/projects/LingWen1/.butler/skills"
mkdir -p "$DST"
if [[ ! -d "$SRC" ]]; then
  echo "missing $SRC" >&2
  exit 1
fi
cp -f "$SRC"/*.md "$DST/"
echo "Synced $(basename "$SRC")/*.md -> $DST"
