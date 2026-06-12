#!/usr/bin/env bash
# B9 LIVE tuning probe — analyze baseline + compare baseline vs delegate_rescue on 3 tasks.
#
# Usage:
#   bash scripts/butler-eval-b9-tuning.sh
#   bash scripts/butler-eval-b9-tuning.sh --analyze-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1

ANALYZE_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --analyze-only) ANALYZE_ONLY=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--analyze-only]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json, sys
from pathlib import Path

from butler.ops.b9_failure_analysis import (
    analyze_b9_live_results,
    analyze_probe_tasks,
    mine_delegate_failure_signatures,
)
from butler.ops.eval_diagnostics import b9_audit_path

audit = b9_audit_path()
if audit.is_file():
    last = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[-1])
    results = last.get("results") or []
    print("=== Last B9 LIVE audit analysis ===")
    print(json.dumps(analyze_b9_live_results(results), ensure_ascii=False, indent=2))
    print()
    print("=== Probe tasks (top-3 failures) ===")
    print(json.dumps(analyze_probe_tasks(results), ensure_ascii=False, indent=2))
else:
    print("(no b9_benchmark.jsonl yet)")

print()
print("=== Mined delegate failure signatures (b9-benchmark) ===")
print(json.dumps(mine_delegate_failure_signatures(), ensure_ascii=False, indent=2))

if int(${ANALYZE_ONLY:-0}):
    sys.exit(0)

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_TUNING_PROBE_TASK_IDS,
    b9_failure_class_tuning_patch,
    b9_live_tuning_patch,
    filter_tasks_by_ids,
)
from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_llm_delegate_benchmarks
from butler.ops.eval_config_overrides import apply_b9_failure_class_overrides, temporary_overrides

probe = filter_tasks_by_ids(B9_LIVE_FIXED_TASKS, B9_TUNING_PROBE_TASK_IDS)
print()
print(f"=== LIVE probe: {len(probe)} tasks (baseline overrides) ===")
with temporary_overrides({}):
    base = run_llm_delegate_benchmarks(mode=B9Mode.LIVE, tasks=probe)
base_analysis = analyze_b9_live_results([r.to_dict() for r in base.results])
print(json.dumps({
    "variant": "baseline",
    "passed": base.passed,
    "total": base.total,
    "pass_rate": base.pass_rate,
    "analysis": base_analysis,
}, ensure_ascii=False, indent=2))

patch = b9_live_tuning_patch()
print()
print(f"=== LIVE probe: delegate_rescue patch {patch} ===")
with temporary_overrides(patch):
    tuned = run_llm_delegate_benchmarks(mode=B9Mode.LIVE, tasks=probe)
tuned_analysis = analyze_b9_live_results([r.to_dict() for r in tuned.results])
print(json.dumps({
    "variant": "delegate_rescue",
    "passed": tuned.passed,
    "total": tuned.total,
    "pass_rate": tuned.pass_rate,
    "analysis": tuned_analysis,
}, ensure_ascii=False, indent=2))

fc_patch = b9_failure_class_tuning_patch()
print()
print(f"=== LIVE probe: failure_class patch {fc_patch} ===")
with temporary_overrides(fc_patch):
    failure_class = run_llm_delegate_benchmarks(mode=B9Mode.LIVE, tasks=probe)
fc_analysis = analyze_b9_live_results([r.to_dict() for r in failure_class.results])
print(json.dumps({
    "variant": "failure_class",
    "passed": failure_class.passed,
    "total": failure_class.total,
    "pass_rate": failure_class.pass_rate,
    "analysis": fc_analysis,
}, ensure_ascii=False, indent=2))

best = max(
    [("baseline", base), ("delegate_rescue", tuned), ("failure_class", failure_class)],
    key=lambda item: (item[1].passed, item[1].pass_rate),
)
applied = None
if audit.is_file():
    full_analysis = analyze_b9_live_results(results)
    applied = apply_b9_failure_class_overrides(full_analysis)
elif failure_class.passed > base.passed:
    applied = apply_b9_failure_class_overrides(fc_analysis)
if applied:
    print()
    print("=== Persisted failure-class overrides ===")
    print(json.dumps(applied, ensure_ascii=False, indent=2))

print()
print(
    f"PROBE SUMMARY: baseline {base.passed}/{base.total} → "
    f"rescue {tuned.passed}/{tuned.total} → "
    f"failure_class {failure_class.passed}/{failure_class.total} "
    f"(best={best[0]})"
)
PY
