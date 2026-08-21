#!/usr/bin/env bash
# Step 7: 验收 — v5 全量测试 + hook 冒烟
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 7: 验收 ==="

log "7a. butler-v5 全量测试..."
cd "$REPO_ROOT/butler-v5"
pnpm test 2>&1 | tail -15
test_rc=${PIPESTATUS[0]}
cd "$REPO_ROOT"

log ""
log "7b. post hook 路径匹配（不跑 vitest，仅 import 检查）..."
python3 -c "
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location(
    'post', Path('$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
t, d = mod._find_matching_v5_tests('$REPO_ROOT/butler-v5/apps/api/src/wechat-inbound-butler.ts')
print('v5 match:', d, '->', t)
assert t, 'no v5 test match'
"

log ""
log "7c. pre hook block 列表抽样..."
python3 "$REPO_ROOT/scripts/ai_guard/pre_tool_use_hook.py" \
  "$REPO_ROOT/butler-v5/packages/runtime/src/run-engine.ts" 2>&1 | grep -E 'block|BLOCKED|WARNING' || true

if [[ $test_rc -eq 0 ]]; then
  print_step_footer "07" "PASS pnpm test ok"
else
  print_step_footer "07" "FAIL pnpm test exit=$test_rc"
  exit $test_rc
fi
