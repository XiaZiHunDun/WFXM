#!/usr/bin/env bash
# B9 probe (3 tasks) with temporary dev model override — model A/B comparison.
#
# Usage:
#   bash scripts/butler-eval-b9-probe-model.sh deepseek/deepseek-chat
#   bash scripts/butler-eval-b9-probe-model.sh --compare minimax/MiniMax-M3 deepseek/deepseek-chat
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1

COMPARE=0
MODELS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compare) COMPARE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--compare] <provider/model> [provider/model ...]"
      echo "  default compare: minimax/MiniMax-M3 deepseek/deepseek-chat"
      exit 0
      ;;
    *) MODELS+=("$1"); shift ;;
  esac
done

if [[ ${#MODELS[@]} -eq 0 ]]; then
  if [[ "$COMPARE" -eq 1 ]]; then
    MODELS=("minimax/MiniMax-M3" "deepseek/deepseek-chat")
  else
    echo "需要至少一个 provider/model，例如 deepseek/deepseek-chat" >&2
    exit 1
  fi
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

MODELS_JSON=$(printf '%s\n' "${MODELS[@]}" | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')

python3 - <<PY
import json, os, sys

models = json.loads("""$MODELS_JSON""")
compare = bool($COMPARE)

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_TUNING_PROBE_TASK_IDS,
    b9_live_tuning_patch,
    filter_tasks_by_ids,
)
from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_llm_delegate_benchmarks
from butler.model_resolve import normalize_role, resolve_effective_model, temporary_model_override
from butler.ops.b9_failure_analysis import analyze_b9_live_results
from butler.ops.eval_config_overrides import temporary_overrides

probe = filter_tasks_by_ids(B9_LIVE_FIXED_TASKS, B9_TUNING_PROBE_TASK_IDS)
patch = b9_live_tuning_patch()
results = []

for spec in models:
    print()
    print(f"=== LIVE probe model={spec} (failure_class tuning patch) ===")
    with temporary_model_override(spec, role="dev"):
        eff = resolve_effective_model(normalize_role("dev"))
        print(
            json.dumps({
                "model_spec": spec,
                "effective": eff.config.to_dict(),
                "sources": list(eff.sources),
            }, ensure_ascii=False, indent=2),
        )
        with temporary_overrides(patch):
            report = run_llm_delegate_benchmarks(mode=B9Mode.LIVE, tasks=probe)
    analysis = analyze_b9_live_results([r.to_dict() for r in report.results])
    row = {
        "model": spec,
        "effective": eff.config.to_dict(),
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "by_classification": analysis.get("by_classification"),
        "tasks": [
            {
                "task_id": t.get("task_id"),
                "passed": t.get("passed"),
                "classification": t.get("classification"),
            }
            for t in analysis.get("tasks", [])
        ],
    }
    results.append(row)
    print(json.dumps(row, ensure_ascii=False, indent=2))

print()
print("=== MODEL PROBE SUMMARY ===")
for row in results:
    print(f"{row['model']}: {row['passed']}/{row['total']} ({row['pass_rate']:.0%})")
best = max(results, key=lambda r: (r["passed"], r["pass_rate"]), default=None)
if best:
    print(f"Best model: {best['model']}")
PY
