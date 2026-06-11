#!/usr/bin/env bash
# B9 LIVE fixed set (10 tasks) — weekly LLM delegate gate.
#
# Usage:
#   BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-b9-live.sh
#   bash scripts/butler-eval-b9-live.sh   # forces LIVE mode
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json, sys
from butler.dev_engine.llm_delegate_benchmark import (
    B9_LIVE_FIXED_TASK_IDS,
    B9Mode,
    run_b9_live_fixed_benchmarks,
)
from butler.ops.eval_bridge import llm_benchmark_to_scores, push_scores
from butler.ops.eval_diagnostics import append_b9_audit

report = run_b9_live_fixed_benchmarks(mode=B9Mode.LIVE)
append_b9_audit(report)
try:
    push_scores(llm_benchmark_to_scores(report))
except Exception:
    pass

stuck_ids = {"B9L_stuck_unsolvable"}
expect_pass = sum(1 for r in report.results if r.task_id not in stuck_ids)
got_pass = sum(
    1 for r in report.results
    if r.passed and r.task_id not in stuck_ids
)
stuck_ok = all(
    r.passed for r in report.results if r.task_id in stuck_ids
) if any(r.task_id in stuck_ids for r in report.results) else True

summary = {
    "mode": report.mode,
    "fixed_set": B9_LIVE_FIXED_TASK_IDS,
    "passed": report.passed,
    "total": report.total,
    "pass_rate": report.pass_rate,
    "expect_pass_tasks": f"{got_pass}/{expect_pass}",
    "stuck_ok": stuck_ok,
    "results": [r.to_dict() for r in report.results],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
print()
print(f"B9 LIVE fixed: {report.passed}/{report.total} ({report.pass_rate:.0%})")
print(f"  solvable: {got_pass}/{expect_pass}  stuck_ok={stuck_ok}")

failed = got_pass < expect_pass or not stuck_ok
if failed:
    print("B9 LIVE FIXED: FAILED", file=sys.stderr)
    for r in report.results:
        if not r.passed:
            print(f"  - {r.task_id}: {'; '.join(r.failure_reasons)}", file=sys.stderr)
    sys.exit(1)
print("B9 LIVE FIXED: PASSED")
PY
