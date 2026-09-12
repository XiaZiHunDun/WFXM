#!/usr/bin/env bash
# git commit-msg hook: enforce [MANUAL-OVERRIDE] tag when protected files are staged.
#
# Why this hook (and not pre-commit):
# - pre-commit runs BEFORE prepare-commit-msg creates COMMIT_EDITMSG.
#   Trying to grep the message in pre-commit always fails (file doesn't exist yet).
# - commit-msg runs AFTER prepare-commit-msg. Git passes the commit message file
#   path as $1. This is the earliest point where we can read the message.
#
# Behavior:
# - If protected files are staged AND commit message lacks [MANUAL-OVERRIDE]:
#   exit 1 (block commit).
# - If protected files are staged AND message has [MANUAL-OVERRIDE]: allow with warning.
# - If no protected files staged: pass through silently.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

. "$ROOT/scripts/ai_guard/protected_files.sh"

COMMIT_MSG_FILE="$1"
if [ -z "$COMMIT_MSG_FILE" ] || [ ! -f "$COMMIT_MSG_FILE" ]; then
    echo "❌ commit-msg hook invoked without message file (arg \$1 empty or not a file)"
    exit 1
fi

# Detect protected files in staged
PROTECTED_HITS=()
for pf in "${PROTECTED_FILES[@]}"; do
    if git diff --cached --name-only | grep -q "^${pf}$"; then
        PROTECTED_HITS+=("$pf")
    fi
done

if [ "${#PROTECTED_HITS[@]}" -eq 0 ]; then
    exit 0
fi

# Protected files staged — require [MANUAL-OVERRIDE] tag in message
if grep -q "\[MANUAL-OVERRIDE\]" "$COMMIT_MSG_FILE"; then
    echo "⚠️  [MANUAL-OVERRIDE] detected — allowing protected file commit"
    for pf in "${PROTECTED_HITS[@]}"; do
        echo "   ✓ $pf"
    done
    exit 0
fi

# Block + list protected files with explanation
echo "❌ BLOCKED: 受保护文件被修改 without [MANUAL-OVERRIDE]:"
for pf in "${PROTECTED_HITS[@]}"; do
    echo "   - $pf"
done
echo ""
echo "如需人工覆盖，请在 commit message 中添加 [MANUAL-OVERRIDE] 标记。"
echo "或使用 --no-verify 跳过所有 hooks（紧急情况 / 真有 rationale）。"
exit 1