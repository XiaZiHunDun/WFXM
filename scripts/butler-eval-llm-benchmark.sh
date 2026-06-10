#!/usr/bin/env bash
# O9: B9 LLM delegate end-to-end benchmark.
#
# Usage:
#   bash scripts/butler-eval-llm-benchmark.sh              # oracle (CI)
#   BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh
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
from butler.dev_engine.llm_delegate_benchmark import (
    resolve_b9_mode,
    run_llm_delegate_benchmarks,
)

from butler.ops.eval_diagnostics import append_b9_audit

mode = resolve_b9_mode()
report = run_llm_delegate_benchmarks()
append_b9_audit(report)
summary = {
    "mode": report.mode,
    "passed": report.passed,
    "total": report.total,
    "pass_rate": report.pass_rate,
    "results": [r.to_dict() for r in report.results],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
print()
print(f"B9 ({mode.value}): {report.passed}/{report.total} ({report.pass_rate:.0%})")
if report.passed < report.total:
    print("B9 BENCHMARK: FAILED", file=sys.stderr)
    for r in report.results:
        if not r.passed:
            print(f"  - {r.task_id}: {'; '.join(r.failure_reasons)}", file=sys.stderr)
    sys.exit(1)
print("B9 BENCHMARK: PASSED")
PY
