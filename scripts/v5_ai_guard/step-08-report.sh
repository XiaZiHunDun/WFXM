#!/usr/bin/env bash
# Step 8: 生成可粘贴给 Agent 的摘要 + 建议 commit 命令
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_repo

log "=== Step 8: 迁移摘要 ==="

LATEST=""
if [[ -f "${BACKUP_ROOT}/LATEST" ]]; then
  LATEST="$(cat "${BACKUP_ROOT}/LATEST")"
fi

printf '\n--- 迁移状态 ---\n'
CHECKS=(
  "post|scripts/ai_guard/post_tool_use_hook.py|Butler v5 PostToolUse"
  "pre|scripts/ai_guard/pre_tool_use_hook.py|Butler v5 protected"
  "cr|.cursorrules|Butler v5 主线"
  "ag|butler-v5/AGENTS.md|三层事实"
  "cl|.claude/settings.json|pre_tool_use_hook.py"
)
for item in "${CHECKS[@]}"; do
  IFS='|' read -r label f m <<< "$item"
  if grep -q "$m" "$REPO_ROOT/$f" 2>/dev/null; then
    printf '  [x] %s\n' "$label"
  else
    printf '  [ ] %s\n' "$label"
  fi
done

printf '\n--- git diff 统计 ---\n'
git -C "$REPO_ROOT" diff --stat -- \
  scripts/ai_guard/post_tool_use_hook.py \
  scripts/ai_guard/pre_tool_use_hook.py \
  .cursorrules \
  butler-v5/AGENTS.md \
  .claude/settings.json \
  scripts/v5_ai_guard/ 2>/dev/null || true

printf '\n--- 备份 ---\n'
printf '  LATEST=%s\n' "${LATEST:-none}"

printf '\n--- 建议 commit（确认无误后手动执行）---\n'
cat <<'EOF'
git add \
  scripts/ai_guard/post_tool_use_hook.py \
  scripts/ai_guard/pre_tool_use_hook.py \
  .cursorrules \
  butler-v5/AGENTS.md \
  .claude/settings.json \
  scripts/v5_ai_guard/

git commit -m "$(cat <<'MSG'
chore(guard): migrate AI hooks to Butler v5 production paths

Add v5 vitest PostToolUse mapping, v5 protected files, cursorrules banner,
and AGENTS.md production vs archive section. [MANUAL-OVERRIDE]

MSG
)"
EOF

print_step_footer "08" "DONE — paste this block to Agent"
