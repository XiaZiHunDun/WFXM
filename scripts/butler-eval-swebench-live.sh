#!/usr/bin/env bash
# Phase 3: Weekly SWE-bench Lite LIVE/oracle subset (default 3 instances).
#
# Usage:
#   bash scripts/butler-eval-swebench-live.sh
#   BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-swebench-live.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json, sys
from butler.ops.swebench_live_eval import (
    push_swebench_live_scores,
    resolve_swe_live_mode,
    run_swebench_live_benchmark,
    select_weekly_instances,
)

mode = resolve_swe_live_mode()
ids = [i.instance_id for i in select_weekly_instances()]
report = run_swebench_live_benchmark(mode=mode)
push = push_swebench_live_scores(report)
summary = {
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
print(f"SWE live ({mode}): {report.passed}/{report.total} ({report.pass_rate:.0%}) week={report.week}")
if report.passed < report.total:
    print("SWE LIVE BENCHMARK: FAILED", file=sys.stderr)
    for r in report.results:
        if not r.passed:
            print(f"  - {r.instance_id}: {'; '.join(r.failure_reasons)}", file=sys.stderr)
    sys.exit(1)
print("SWE LIVE BENCHMARK: PASSED")
PY
