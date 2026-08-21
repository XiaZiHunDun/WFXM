#!/usr/bin/env bash
# Step 5: butler-v5/AGENTS.md — 增加 §0 生产 vs 脚手架
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 5: butler-v5/AGENTS.md §0 ==="
python3 "$SCRIPT_DIR/apply_agents_md_v5.py"
rc=$?

if [[ $rc -ne 0 ]]; then
  print_step_footer "05" "FAIL exit=$rc"
  exit $rc
fi

grep -A3 "## 0. 三层事实" "$REPO_ROOT/butler-v5/AGENTS.md" | head -6

print_step_footer "05" "PASS"
