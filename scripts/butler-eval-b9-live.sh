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
from butler.dev_engine.b9_tiers import (
    B9_STUCK_TASK_IDS,
    b9_task_tier,
    summarize_tier_results,
)
from butler.dev_engine.llm_delegate_benchmark import (
    B9_LIVE_FIXED_TASK_IDS,
    B9Mode,
    run_b9_live_fixed_benchmarks,
)
from butler.env_parse import float_env
from butler.ops.eval_bridge import llm_benchmark_to_scores, push_scores
from butler.ops.eval_diagnostics import append_b9_audit

report = run_b9_live_fixed_benchmarks(mode=B9Mode.LIVE)
append_b9_audit(report)
summary_rescue = None
try:
    from butler.ops.eval_actions import maybe_apply_b9_live_rescue

    summary_rescue = maybe_apply_b9_live_rescue(report)
except Exception:
    pass
try:
    push_scores(llm_benchmark_to_scores(report))
except Exception:
    pass

result_dicts = [r.to_dict() for r in report.results]
tiers = summarize_tier_results(result_dicts)
tier1 = tiers["tier1"]
tier2 = tiers["tier2"]
tier1_min = float_env("BUTLER_EVAL_B9_TIER1_PASS_RATE_MIN", 0.5)

stuck_ok = all(
    r.passed for r in report.results if r.task_id in B9_STUCK_TASK_IDS
) if any(r.task_id in B9_STUCK_TASK_IDS for r in report.results) else True

expect_pass = sum(1 for r in report.results if r.task_id not in B9_STUCK_TASK_IDS)
got_pass = sum(
    1 for r in report.results
    if r.passed and r.task_id not in B9_STUCK_TASK_IDS
)

summary = {
    "mode": report.mode,
    "fixed_set": B9_LIVE_FIXED_TASK_IDS,
    "passed": report.passed,
    "total": report.total,
    "pass_rate": report.pass_rate,
    "expect_pass_tasks": f"{got_pass}/{expect_pass}",
    "stuck_ok": stuck_ok,
    "tiers": tiers,
    "tier1_gate": {
        "min_pass_rate": tier1_min,
        "passed": tier1["passed"],
        "total": tier1["total"],
        "pass_rate": tier1["pass_rate"],
    },
    "results": result_dicts,
}
if summary_rescue is not None:
    summary["delegate_rescue_applied"] = summary_rescue
print(json.dumps(summary, ensure_ascii=False, indent=2))
print()
print(f"B9 LIVE fixed: {report.passed}/{report.total} ({report.pass_rate:.0%})")
print(f"  solvable: {got_pass}/{expect_pass}  stuck_ok={stuck_ok}")
print(
    f"  tier1 (gate): {tier1['passed']}/{tier1['total']} "
    f"({tier1['pass_rate']:.0%}, min={tier1_min:.0%})"
)
print(f"  tier2 (stretch): {tier2['passed']}/{tier2['total']} ({tier2['pass_rate']:.0%})")

tier1_failed = tier1["total"] and tier1["pass_rate"] < tier1_min
if tier1_failed or not stuck_ok:
    print("B9 LIVE FIXED: FAILED (tier1 gate)", file=sys.stderr)
    for r in report.results:
        if not r.passed and b9_task_tier(r.task_id) == 1:
            print(f"  [tier1] {r.task_id}: {'; '.join(r.failure_reasons)}", file=sys.stderr)
    if not stuck_ok:
        print("  stuck task did not pass as expected", file=sys.stderr)
    sys.exit(1)
if tier2["total"] and tier2["passed"] < tier2["total"]:
    print("B9 LIVE FIXED: PASSED (tier1 gate); tier2 stretch failures (non-blocking):")
    for r in report.results:
        if not r.passed and b9_task_tier(r.task_id) == 2:
            print(f"  [tier2] {r.task_id}: {'; '.join(r.failure_reasons)}")
else:
    print("B9 LIVE FIXED: PASSED")
PY
