#!/usr/bin/env bash
# Step 0: 环境探测（只读，不改文件）
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 0: 环境探测 ==="
log "REPO_ROOT=$REPO_ROOT"

checks=0
pass=0

check() {
  checks=$((checks + 1))
  if eval "$2"; then
    log "  OK  $1"
    pass=$((pass + 1))
  else
    warn "  FAIL $1"
  fi
}

check "git 仓库" "git -C \"$REPO_ROOT\" rev-parse --is-inside-work-tree >/dev/null 2>&1"
check "butler-v5 存在" "test -d \"$REPO_ROOT/butler-v5\""
check "pnpm" "command -v pnpm >/dev/null"
check "node" "command -v node >/dev/null"
check "python3" "command -v python3 >/dev/null"
check "post hook" "test -f \"$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py\""
check "pre hook" "test -f \"$REPO_ROOT/scripts/ai_guard/pre_tool_use_hook.py\""
check ".cursorrules" "test -f \"$REPO_ROOT/.cursorrules\""
check "claude settings" "test -f \"$REPO_ROOT/.claude/settings.json\""

log ""
log "Git 分支: $(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo '?')"
log "未提交变更:"
git -C "$REPO_ROOT" status --short 2>/dev/null | head -20 || true

log ""
log "v5 迁移标记探测:"
grep -q "Butler v5 PostToolUse" "$REPO_ROOT/scripts/ai_guard/post_tool_use_hook.py" 2>/dev/null && log "  post hook v5: 已存在" || log "  post hook v5: 未应用"
grep -q "Butler v5 protected" "$REPO_ROOT/scripts/ai_guard/pre_tool_use_hook.py" 2>/dev/null && log "  pre hook v5: 已存在" || log "  pre hook v5: 未应用"
grep -q "Butler v5 主线" "$REPO_ROOT/.cursorrules" 2>/dev/null && log "  cursorrules v5: 已存在" || log "  cursorrules v5: 未应用"
grep -q "三层事实" "$REPO_ROOT/butler-v5/AGENTS.md" 2>/dev/null && log "  AGENTS.md §0: 已存在" || log "  AGENTS.md §0: 未应用"

if [[ "$pass" -eq "$checks" ]]; then
  print_step_footer "00" "PASS ($pass/$checks)"
else
  print_step_footer "00" "PARTIAL ($pass/$checks)"
  exit 1
fi
