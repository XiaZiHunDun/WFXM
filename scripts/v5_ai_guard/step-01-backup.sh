#!/usr/bin/env bash
# Step 1: 备份将被修改的文件
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/${STAMP}"
log "=== Step 1: 备份 → $DEST ==="

mkdir -p "$DEST"

FILES=(
  "scripts/ai_guard/post_tool_use_hook.py"
  "scripts/ai_guard/pre_tool_use_hook.py"
  ".cursorrules"
  "butler-v5/AGENTS.md"
  ".claude/settings.json"
)

for f in "${FILES[@]}"; do
  src="$REPO_ROOT/$f"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$DEST/$f")"
    cp -a "$src" "$DEST/$f"
    log "  copied $f"
  else
    warn "  missing $f (skipped)"
  fi
done

echo "$STAMP" > "${BACKUP_ROOT}/LATEST"
log "LATEST 标记: ${BACKUP_ROOT}/LATEST → $STAMP"

print_step_footer "01" "PASS backup=$DEST"
