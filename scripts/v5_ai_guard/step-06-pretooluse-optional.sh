#!/usr/bin/env bash
# Step 6（可选）: Claude Code 启用 PreToolUse
# 用法: bash step-06-pretooluse-optional.sh
#       或: ENABLE=1 bash step-06-pretooluse-optional.sh  （跳过确认）
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 6（可选）: Claude PreToolUse ==="
log "说明：Cursor 主要靠 .cursorrules；Claude Code 需 settings.json 才有 PreToolUse。"
log "若你主要用 Cursor，可 SKIP 本步。"

if [[ "${ENABLE:-}" != "1" ]]; then
  read -r -p "是否启用 PreToolUse？(y/N) " ans
  if [[ "${ans,,}" != "y" ]]; then
    print_step_footer "06" "SKIPPED (user choice)"
    exit 0
  fi
fi

python3 "$SCRIPT_DIR/apply_claude_pretooluse.py"
rc=$?

if [[ $rc -ne 0 ]]; then
  print_step_footer "06" "FAIL exit=$rc"
  exit $rc
fi

python3 -c "import json; d=json.load(open('$REPO_ROOT/.claude/settings.json')); print('PreToolUse keys:', list(d.get('hooks',{}).get('PreToolUse',[{}])[0].keys()))"

print_step_footer "06" "PASS"
