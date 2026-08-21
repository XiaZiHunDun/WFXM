#!/usr/bin/env bash
# Step 2: PostToolUse — 增加 butler-v5 vitest 映射
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 2: PostToolUse v5 vitest ==="
python3 "$SCRIPT_DIR/apply_post_hook_v5.py"
rc=$?

if [[ $rc -ne 0 ]]; then
  print_step_footer "02" "FAIL apply exit=$rc"
  exit $rc
fi

# 修复已知 f-string 换行 bug（幂等）
python3 "$SCRIPT_DIR/repair_post_hook_fstring.py" || true

log "语法检查..."
python3 -m py_compile "$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py"
rc=$?
if [[ $rc -ne 0 ]]; then
  print_step_footer "02" "FAIL SyntaxError — 请运行: python3 scripts/v5_ai_guard/repair_post_hook_fstring.py"
  exit $rc
fi

# 冒烟：路径匹配（秒级，不跑 vitest）
log "冒烟：路径匹配（--match-only）..."
python3 "$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py" --match-only \
  "$REPO_ROOT/butler-v5/apps/api/src/wechat-inbound-butler.ts"

log "可选完整 vitest（约 20–60 秒）："
log "  python3 scripts/ai_guard/post_tool_use_hook.py butler-v5/apps/api/src/wechat-inbound-butler.ts"

print_step_footer "02" "PASS"
