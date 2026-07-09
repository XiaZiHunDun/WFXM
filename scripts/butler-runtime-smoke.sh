#!/usr/bin/env bash
# Runtime ops smoke — 灵文1号（默认）或 普通试点项目（轻量 jobs）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-灵文1号}"

if [[ -f .env ]]; then
  set -a
  set +u
  # shellcheck disable=SC1091
  source .env
  set -u
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."
# 冒烟默认不推微信（避免 iLink 限流）；真机推送验证用 butler-wechat-push-verify.sh
# 或 BUTLER_RUNTIME_SMOKE_PUSH=1
if [[ "${BUTLER_RUNTIME_SMOKE_PUSH:-0}" != "1" ]]; then
  export BUTLER_RUNTIME_PUSH=0
fi
export BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS="${BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS:-30}"
export WECHAT_SEND_CHUNK_RETRIES="${WECHAT_SEND_CHUNK_RETRIES:-6}"
export WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS="${WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS:-2}"

echo "== runtime unit tests (incl. mutating approval gate) =="
python3 -m pytest tests/test_runtime.py -q --tb=line

echo ""
echo "== list jobs ($PROJECT) =="
python3 -m butler.main runtime list --project "$PROJECT"

_run() {
  local id="$1"
  shift
  echo ""
  echo "== run $id =="
  python3 -m butler.main runtime run "$id" --project "$PROJECT" "$@"
}

if [[ "$PROJECT" == "普通试点项目" ]]; then
  _run pilot-heartbeat --no-notify
  _run test-unit-smoke --no-notify --force
else
  _run factory-status-daily --no-notify

  if [[ "${BUTLER_RUNTIME_PUSH:-0}" == "1" ]]; then
    echo ""
    echo "== cooldown before next runtime push =="
    sleep "${BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS}"
  else
    echo ""
    echo "== skip push cooldown (BUTLER_RUNTIME_PUSH=0) =="
  fi

  _run publish-preflight --no-notify

  echo ""
  echo "== agent runtime bridge (list_runtime_jobs / run_runtime_job) =="
  export BUTLER_RUNTIME_ENABLED=1
  python3 -m pytest tests/test_dev_ops_p2.py::TestRuntimeBridgeTools -q --tb=line

  if [[ "${BUTLER_RUNTIME_RUN_CONSISTENCY:-0}" == "1" ]]; then
    _run consistency-weekly --no-notify
  else
    echo ""
    echo "Skip consistency-weekly (set BUTLER_RUNTIME_RUN_CONSISTENCY=1 to run; may take several minutes)"
  fi
fi

echo ""
echo "== timer status =="
systemctl --user --no-pager list-timers 'butler-runtime*' 2>/dev/null || echo "(no user timer)"

echo ""
echo "Runtime smoke done."
