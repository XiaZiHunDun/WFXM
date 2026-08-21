#!/usr/bin/env bash
# shellcheck disable=SC2034
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_ROOT="${REPO_ROOT}/.backup/v5-ai-guard"
MARKER_PREFIX="=== Butler v5 AI Guard migration"

log() { printf '[v5-ai-guard] %s\n' "$*"; }
warn() { printf '[v5-ai-guard][WARN] %s\n' "$*" >&2; }
fail() { printf '[v5-ai-guard][FAIL] %s\n' "$*" >&2; exit 1; }

require_repo() {
  if [[ ! -d "${REPO_ROOT}/butler-v5" ]] || [[ ! -d "${REPO_ROOT}/scripts/ai_guard" ]]; then
    fail "未在 WFXM 仓库根目录（缺少 butler-v5/ 或 scripts/ai_guard/）"
  fi
}

print_step_footer() {
  local step="$1"
  local status="$2"
  printf '\n========== STEP %s RESULT: %s ==========\n' "$step" "$status"
  printf 'REPO_ROOT=%s\n' "$REPO_ROOT"
  printf '请将上方整段（含 STEP RESULT）复制给 Agent 继续下一步。\n'
}
