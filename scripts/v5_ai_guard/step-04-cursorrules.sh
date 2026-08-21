#!/usr/bin/env bash
# Step 4: .cursorrules — 增加 v5 主线 banner
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 4: .cursorrules v5 banner ==="
python3 "$SCRIPT_DIR/apply_cursorrules_v5.py"
rc=$?

if [[ $rc -ne 0 ]]; then
  print_step_footer "04" "FAIL exit=$rc"
  exit $rc
fi

head -8 "$REPO_ROOT/.cursorrules"

print_step_footer "04" "PASS"
