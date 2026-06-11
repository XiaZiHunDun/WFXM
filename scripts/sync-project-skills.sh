#!/usr/bin/env bash
# Sync tracked project skills/ → .butler/skills/ for any project slug.
# Supports flat *.md and directory skills (foo/SKILL.md → foo.md stub + foo/).
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

PYTHONPATH="$ROOT" python3 - <<PY
from pathlib import Path
from butler.skills.layout import sync_skills_tree

actions = sync_skills_tree(Path("$SRC"), Path("$DST"))
if not actions:
    print("（无技能文件）")
else:
    for line in actions:
        print(f"Synced {line}")
PY
