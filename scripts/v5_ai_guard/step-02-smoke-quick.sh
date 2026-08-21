#!/usr/bin/env bash
# Step 2 快速冒烟：只验证路径匹配，不跑 vitest（秒级完成）
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 2 快速冒烟（--match-only）==="
python3 "$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py" --match-only \
  "$REPO_ROOT/butler-v5/apps/api/src/wechat-inbound-butler.ts"

print_step_footer "02-smoke" "PASS match-only"
