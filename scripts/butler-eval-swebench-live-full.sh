#!/usr/bin/env bash
# SWE-bench Lite full set (15 instances) — gated by 2 consecutive weekly 3/3 passes.
#
# Usage:
#   bash scripts/butler-eval-swebench-live-full.sh          # respects gate
#   bash scripts/butler-eval-swebench-live-full.sh --force  # skip gate (stretch)
#   BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-swebench-live-full.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json
import sys

from butler.dev_engine.swebench_lite import get_all_instances
from butler.ops.swebench_entry_gate import evaluate_swe_full_entry_gate
from butler.ops.swebench_live_eval import (
    push_swebench_live_scores,
    resolve_swe_live_mode,
    run_swebench_live_benchmark,
)

force = bool(${FORCE})
gate = evaluate_swe_full_entry_gate()
print("gate=", json.dumps(gate, ensure_ascii=False, indent=2))
if not gate.get("allowed") and not force:
    print(
        "SWE FULL LIVE: BLOCKED — need 2 consecutive weekly subset passes at 100%.",
        file=sys.stderr,
    )
    print(
        "Run: bash scripts/butler-eval-swebench-live.sh weekly until gate opens.",
        file=sys.stderr,
    )
    sys.exit(2)

instances = get_all_instances()
mode = resolve_swe_live_mode()
ids = [i.instance_id for i in instances]
report = run_swebench_live_benchmark(instances=instances, mode=mode)
push = push_swebench_live_scores(report)
summary = {
    "scope": "full",
    "gate": gate,
    "forced": force,
    "mode": report.mode,
    "week": report.week,
    "instances": ids,
    "passed": report.passed,
    "total": report.total,
    "pass_rate": report.pass_rate,
    "scores_pushed": push.get("scores_pushed", 0),
    "results": [r.to_dict() for r in report.results],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
print()
print(
    f"SWE full ({mode}): {report.passed}/{report.total} "
    f"({report.pass_rate:.0%}) instances={len(ids)}"
)
if report.passed < report.total:
    print("SWE FULL LIVE BENCHMARK: FAILED", file=sys.stderr)
    for r in report.results:
        if not r.passed:
            print(f"  - {r.instance_id}: {'; '.join(r.failure_reasons)}", file=sys.stderr)
    sys.exit(1)
print("SWE FULL LIVE BENCHMARK: PASSED")
PY
