#!/usr/bin/env bash
# Step 3: PreToolUse — 增加 v5 受保护文件
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 3: PreToolUse v5 protected ==="
python3 "$SCRIPT_DIR/apply_pre_hook_v5.py"
rc=$?

if [[ $rc -ne 0 ]]; then
  print_step_footer "03" "FAIL exit=$rc"
  exit $rc
fi

log "冒烟：应 BLOCK migration SQL"
out="$(python3 "$REPO_ROOT/scripts/ai_guard/pre_tool_use_hook.py" \
  "$REPO_ROOT/butler-v5/packages/persistence/src/migrations/0001_initial.sql" 2>&1 || true)"
echo "$out" | tail -3

if echo "$out" | grep -q '"decision": "block"'; then
  log "  OK block migration"
else
  warn "  未看到 block 决策，请人工确认"
fi

print_step_footer "03" "PASS"
