#!/usr/bin/env bash
# Pytest collection bisect helper — incremental gates for full-suite tech debt.
# Full `pytest tests/` may fail from cross-test state; use layered gates for release.
# Usage:
#   bash scripts/butler-pytest-bisect.sh
#   RUN_FULL=1 bash scripts/butler-pytest-bisect.sh
#   DOMAINS=1 bash scripts/butler-pytest-bisect.sh   # also run butler-domain-pytest.sh layers
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

_run "Layer D: ACL contracts + hooks" \
  tests/core/test_compaction_context_adapter.py \
  tests/core/test_context_pipeline_acl.py \
  tests/core/test_hook_context_adapter.py \
  tests/core/test_dev_context_adapter.py \
  tests/core/test_pre_compact_hook_acl.py \
  tests/core/test_compaction_checkpoint_acl.py \
  tests/test_hook_result_dataclasses.py

_run "Layer E: gateway utterance catalog" \
  tests/corpus/runners/test_gateway_utterance_catalog.py

if [[ "${DOMAINS:-0}" == "1" ]]; then
  for domain in gateway ops core dev_engine memory; do
    _run "Domain: tests/$domain" "tests/$domain/"
  done
fi

echo ""
if [[ "${RUN_FULL:-0}" == "1" ]]; then
  echo "== Full suite (RUN_FULL=1) =="
  OUT="$(mktemp)"
  set +e
  "$PY" -m pytest tests/ -q --tb=no -m 'not live_llm' 2>&1 | tee "$OUT"
  rc=${PIPESTATUS[0]}
  set -e
  if [[ "$rc" -eq 0 ]]; then
    echo "  -> OK"
  else
    failed="$(grep -E '^FAILED ' "$OUT" 2>/dev/null | wc -l | tr -d ' ')"
    passed="$(grep -E ' passed' "$OUT" 2>/dev/null | tail -1 || true)"
    echo "  -> FAIL rc=$rc ${passed:-} failed_lines=${failed:-?}"
    echo "  Tip: bisect with pytest tests/<file>.py -q --tb=line"
    fail=$((fail + 1))
  fi
  rm -f "$OUT"
else
  echo "Tip: RUN_FULL=1 $0 to probe full suite (may take 10–30 min)."
  echo "Tip: DOMAINS=1 $0 to run tests/{gateway,ops,core,dev_engine,memory}."
fi

echo ""
echo "summary: layer_fail=$fail"
exit "$fail"
