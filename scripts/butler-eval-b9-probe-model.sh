#!/usr/bin/env bash
# B9 probe / tier1 with temporary dev model override — model A/B comparison.
#
# Usage:
#   bash scripts/butler-eval-b9-probe-model.sh deepseek/deepseek-reasoner
#   bash scripts/butler-eval-b9-probe-model.sh --compare minimax/MiniMax-M3 deepseek/deepseek-reasoner
#   bash scripts/butler-eval-b9-probe-model.sh --tier1 deepseek/deepseek-reasoner
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1

COMPARE=0
TIER1=0
MODELS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compare) COMPARE=1; shift ;;
    --tier1) TIER1=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--compare|--tier1] <provider/model> [provider/model ...]"
      echo "  default compare: minimax/MiniMax-M3 deepseek/deepseek-chat deepseek/deepseek-reasoner"
      echo "  --tier1: run tier1 LIVE fixed tasks (release gate subset) instead of 3-task probe"
      exit 0
      ;;
    *) MODELS+=("$1"); shift ;;
  esac
done

if [[ ${#MODELS[@]} -eq 0 ]]; then
  if [[ "$COMPARE" -eq 1 ]]; then
    MODELS=("minimax/MiniMax-M3" "deepseek/deepseek-chat" "deepseek/deepseek-reasoner")
  else
    echo "需要至少一个 provider/model，例如 deepseek/deepseek-reasoner" >&2
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
tier1_mode = bool($TIER1)

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_TUNING_PROBE_TASK_IDS,
    b9_live_tuning_patch,
    filter_tasks_by_ids,
)
from butler.dev_engine.b9_tiers import filter_tier_tasks, summarize_tier_results
from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_llm_delegate_benchmarks
from butler.model_resolve import normalize_role, resolve_effective_model, temporary_model_override
from butler.ops.b9_failure_analysis import analyze_b9_live_results
from butler.ops.eval_config_overrides import temporary_overrides

if tier1_mode:
    tasks = filter_tier_tasks(B9_LIVE_FIXED_TASKS, tier=1)
    run_label = "tier1 LIVE fixed"
else:
    tasks = filter_tasks_by_ids(B9_LIVE_FIXED_TASKS, B9_TUNING_PROBE_TASK_IDS)
    run_label = "probe (3 tasks)"
patch = b9_live_tuning_patch()
results = []

for spec in models:
    print()
    print(f"=== LIVE {run_label} model={spec} (failure_class tuning patch) ===")
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
            report = run_llm_delegate_benchmarks(mode=B9Mode.LIVE, tasks=tasks)
    result_dicts = [r.to_dict() for r in report.results]
    analysis = analyze_b9_live_results(result_dicts)
    row = {
        "model": spec,
        "run": run_label,
        "effective": eff.config.to_dict(),
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "tiers": summarize_tier_results(result_dicts) if tier1_mode else None,
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
