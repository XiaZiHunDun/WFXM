#!/usr/bin/env bash
# Pytest collection bisect helper — incremental gates for full-suite tech debt.
# Full `pytest tests/` may fail from cross-test state; use layered gates for release.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
PY="${PYTHON:-/home/ailearn/miniconda3/bin/python3}"
if [[ ! -x "$PY" ]]; then PY=python3; fi

fail=0
_run() {
  local title="$1"
  shift
  echo ""
  echo "== $title =="
  if "$PY" -m pytest "$@" -q --tb=no; then
    echo "  -> OK"
  else
    echo "  -> FAIL"
    fail=$((fail + 1))
  fi
}

echo "Butler pytest bisect ($(date -Iseconds))"

_run "Layer A: reasoning + gateway + queue" \
  tests/test_reasoning_trace.py \
  tests/gateway/test_gateway_handler.py \
  tests/gateway/test_message_queue.py

_run "Layer B: CC harness subset" \
  tests/test_cc_p3_p4_features.py \
  tests/ops/test_runtime_metrics.py \
  tests/test_tool_result_storage.py

_run "Layer C: tools_registry (isolated)" \
  tests/test_tools_registry.py

_run "Layer D: gateway utterance catalog" \
  tests/corpus/runners/test_gateway_utterance_catalog.py

echo ""
if [[ "${RUN_FULL:-0}" == "1" ]]; then
  echo "== Full suite (RUN_FULL=1) =="
  if "$PY" -m pytest tests/ -q --tb=line -x 2>&1 | tail -20; then
    echo "  -> OK"
  else
    echo "  -> FAIL (see above; known tech debt when run without isolation)"
    fail=$((fail + 1))
  fi
else
  echo "Tip: RUN_FULL=1 $0 to probe full suite (may take minutes)."
fi

echo ""
echo "summary: layer_fail=$fail"
exit "$fail"
