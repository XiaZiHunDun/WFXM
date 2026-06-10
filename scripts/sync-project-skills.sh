#!/usr/bin/env bash
# Sync tracked project skills/ → .butler/skills/ for any project slug.
#
# Usage:
#   bash scripts/sync-project-skills.sh LingWen1
#   bash scripts/sync-project-skills.sh DemoPilot
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLUG="${1:-}"
if [[ -z "$SLUG" ]]; then
  echo "Usage: $0 <project-slug>" >&2
  exit 1
fi

SRC="$ROOT/projects/$SLUG/skills"
DST="$ROOT/projects/$SLUG/.butler/skills"
if [[ ! -d "$SRC" ]]; then
  echo "missing $SRC" >&2
  exit 1
fi
mkdir -p "$DST"
cp -f "$SRC"/*.md "$DST/"
echo "Synced $SRC/*.md -> $DST"
