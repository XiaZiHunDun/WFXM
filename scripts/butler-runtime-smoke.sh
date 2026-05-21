#!/usr/bin/env bash
# Runtime ops smoke for 灵文1号 (readonly jobs + mutating gates via pytest).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-灵文1号}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== runtime unit tests (incl. mutating approval gate) =="
python3 -m pytest tests/test_runtime.py -q --tb=line

echo ""
echo "== list jobs ($PROJECT) =="
python3 -m butler.main runtime list --project "$PROJECT"

echo ""
echo "== run factory-status-daily =="
python3 -m butler.main runtime run factory-status-daily --project "$PROJECT"

echo ""
echo "== run publish-preflight (readonly) =="
python3 -m butler.main runtime run publish-preflight --project "$PROJECT"

echo ""
echo "== agent runtime bridge (list_runtime_jobs / run_runtime_job) =="
export BUTLER_RUNTIME_ENABLED=1
python3 -m pytest tests/test_dev_ops_p2.py::TestRuntimeBridgeTools -q --tb=line

if [[ "${BUTLER_RUNTIME_RUN_CONSISTENCY:-0}" == "1" ]]; then
  echo ""
  echo "== run consistency-weekly (slow, opt-in) =="
  python3 -m butler.main runtime run consistency-weekly --project "$PROJECT"
else
  echo ""
  echo "Skip consistency-weekly (set BUTLER_RUNTIME_RUN_CONSISTENCY=1 to run; may take several minutes)"
fi

echo ""
echo "== timer status =="
systemctl --user --no-pager list-timers 'butler-runtime*' 2>/dev/null || echo "(no user timer)"

echo ""
echo "Runtime smoke done."
