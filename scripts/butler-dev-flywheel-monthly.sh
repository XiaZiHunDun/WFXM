#!/usr/bin/env bash
# Monthly Butler-native dev flywheel gate (no CC bridge).
#
# Usage:
#   bash scripts/butler-dev-flywheel-monthly.sh
#   bash scripts/butler-dev-flywheel-monthly.sh --log   # append pilot-log row on PASS
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG=0
for arg in "$@"; do
  case "$arg" in
    --log) LOG=1 ;;
    -h|--help)
      sed -n '1,8p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

FAIL=0
STAMP="$(date +%Y-%m-%d)"
echo "=== Butler dev flywheel monthly ($STAMP) ==="
echo "profile=${BUTLER_ENV_PROFILE:-?} dev_engine=${BUTLER_DEV_ENGINE:-?}"
echo

run_step() {
  local name="$1"
  shift
  echo "--- $name ---"
  if "$@"; then
    echo "  OK: $name"
  else
    echo "  FAIL: $name"
    FAIL=1
  fi
  echo
}

run_step "flywheel checklist (--probe)" \
  bash "$ROOT/scripts/butler-dev-live-flywheel-checklist.sh" --probe

run_step "G1-04 prod evidence (read-only)" \
  bash "$ROOT/scripts/butler-dev-prod-evidence-checklist.sh"

run_step "handler sim: remote-dev" \
  bash "$ROOT/scripts/butler-wechat-remote-dev-sim.sh"

run_step "handler sim: owner-ux" \
  bash "$ROOT/scripts/butler-wechat-owner-ux-sim.sh"

run_step "WeChat attach probe (handler)" \
  bash "$ROOT/scripts/butler-wechat-attach-probe.sh"

run_step "memory monthly probe (M1–M7)" \
  bash "$ROOT/scripts/butler-memory-monthly-probe.sh"

if [[ "${BUTLER_WECHAT_DEV_DELEGATE_SIM:-1}" != "0" ]]; then
  run_step "handler sim: dev-delegate lingwen (full)" \
    bash "$ROOT/scripts/butler-wechat-dev-delegate-sim.sh" --track lingwen
  run_step "handler sim: dev-delegate demopilot (--quick)" \
    bash "$ROOT/scripts/butler-wechat-dev-delegate-sim.sh" --track demopilot --quick
else
  echo "--- skip dev-delegate (BUTLER_WECHAT_DEV_DELEGATE_SIM=0) ---"
  echo
fi

echo "=== WeChat manual (after green gate) ==="
echo "  See docs/guides/dev-flywheel-monthly.md §2"
echo "  Suggested: 灵文1号 dev 飞轮 md 或 普通试点项目 README 摘要"
echo

if [[ "$FAIL" -ne 0 ]]; then
  echo "MONTHLY GATE: FAIL — fix before WeChat manual flywheel"
  exit 1
fi

echo "MONTHLY GATE: PASS (handler sims)"
if [[ "$LOG" -eq 1 ]]; then
  LOG_FILE="$ROOT/projects/LingWen1/docs/pilot-log.md"
  ROW="| $STAMP | **月度 Dev 飞轮 gate** | monthly.sh PASS；真机话术见 dev-flywheel-monthly.md |"
  if [[ -f "$LOG_FILE" ]]; then
    # Insert after header table row
    if ! grep -q "月度 Dev 飞轮 gate.*$STAMP" "$LOG_FILE" 2>/dev/null; then
      sed -i "/^|------|/a\\$ROW" "$LOG_FILE"
      echo "Appended pilot-log: $LOG_FILE"
    else
      echo "pilot-log already has entry for $STAMP"
    fi
  fi
fi
exit 0
