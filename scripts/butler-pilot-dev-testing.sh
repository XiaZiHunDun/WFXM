#!/usr/bin/env bash
# Butler pilot project dev testing gate.
#
# All projects under projects/ are test pilots (not production business yet).
# Agent/delegate sims MAY modify pilot workspaces — expected; see docs/guides/pilot-project-dev-testing.md
#
# Usage:
#   bash scripts/butler-pilot-dev-testing.sh                    # 演示试点 (default)
#   bash scripts/butler-pilot-dev-testing.sh --project lingwen
#   bash scripts/butler-pilot-dev-testing.sh --no-delegate    # skip LLM delegate sim
#   bash scripts/butler-pilot-dev-testing.sh --log            # append DemoPilot pilot-log on PASS
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="demopilot"
DELEGATE=1
LOG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="${2:-demopilot}"
      shift 2
      ;;
    --no-delegate) DELEGATE=0; shift ;;
    --log) LOG=1; shift ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

case "$PROJECT" in
  demopilot|demo|演示试点)
    PROJECT="demopilot"
    BUTLER_NAME="演示试点"
    DELEGATE_TRACK="demopilot"
    ;;
  lingwen|灵文|灵文1号)
    PROJECT="lingwen"
    BUTLER_NAME="灵文1号"
    DELEGATE_TRACK="lingwen"
    ;;
  *)
    echo "unknown --project: $PROJECT (use demopilot|lingwen)" >&2
    exit 2
    ;;
esac

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"
STAMP="$(date +%Y-%m-%d)"
FAIL=0

run_step() {
  local name="$1"
  shift
  echo ""
  echo "=== $name ==="
  if "$@"; then
    echo "  OK: $name"
  else
    echo "  FAIL: $name"
    FAIL=1
  fi
}

echo "=== Butler pilot dev testing ($STAMP) ==="
echo "pilot=$PROJECT butler_name=$BUTLER_NAME profile=${BUTLER_ENV_PROFILE:-?}"

if [[ "$PROJECT" == "demopilot" ]]; then
  run_step "preflight ($BUTLER_NAME)" \
    butler project preflight --project "$BUTLER_NAME"
  run_step "DemoPilot CLI smoke" \
    bash "$ROOT/scripts/butler-demo-pilot-smoke.sh"
else
  run_step "preflight ($BUTLER_NAME)" \
    butler project preflight --project "$BUTLER_NAME"
fi

run_step "flywheel checklist (--probe)" \
  bash "$ROOT/scripts/butler-dev-live-flywheel-checklist.sh" --probe

run_step "dev tools smoke (isolated workspace)" \
  bash "$ROOT/scripts/butler-dev-tools-smoke.sh"

run_step "handler sim: remote-dev" \
  bash "$ROOT/scripts/butler-wechat-remote-dev-sim.sh"

if [[ "$DELEGATE" -eq 1 && "${BUTLER_WECHAT_DEV_DELEGATE_SIM:-1}" != "0" ]]; then
  run_step "handler sim: dev-delegate ($DELEGATE_TRACK)" \
    bash "$ROOT/scripts/butler-wechat-dev-delegate-sim.sh" --track "$DELEGATE_TRACK"
else
  echo ""
  echo "=== skip dev-delegate sim (--no-delegate or BUTLER_WECHAT_DEV_DELEGATE_SIM=0) ==="
fi

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "PILOT DEV TESTING: FAIL (pilot=$PROJECT)"
  exit 1
fi

echo "PILOT DEV TESTING: PASS (pilot=$PROJECT)"

if [[ "$LOG" -eq 1 ]]; then
  if [[ "$PROJECT" == "demopilot" ]]; then
    LOG_FILE="$ROOT/projects/DemoPilot/docs/pilot-log.md"
    ROW="| $STAMP | **pilot-dev-testing gate** | butler-pilot-dev-testing.sh PASS |"
  else
    LOG_FILE="$ROOT/projects/LingWen1/docs/pilot-log.md"
    ROW="| $STAMP | **pilot-dev-testing gate（灵文）** | butler-pilot-dev-testing.sh --project lingwen PASS |"
  fi
  if [[ -f "$LOG_FILE" ]] && ! grep -q "pilot-dev-testing gate.*$STAMP" "$LOG_FILE" 2>/dev/null; then
    sed -i "/^|------|/a\\$ROW" "$LOG_FILE"
    echo "Appended: $LOG_FILE"
  fi
fi

exit 0
