#!/usr/bin/env bash
# O7: DevEngine B1–B8 + Memory MB1–MB7 regression gate.
#
# Usage:
#   bash scripts/butler-eval-regression.sh
#   bash scripts/butler-eval-regression.sh --sync-dataset
#   bash scripts/butler-eval-regression.sh --no-langfuse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNC_DATASET=0
PUSH_LANGFUSE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync-dataset) SYNC_DATASET=1 ;;
    --no-langfuse) PUSH_LANGFUSE="0" ;;
    -h|--help)
      echo "Usage: $0 [--sync-dataset] [--no-langfuse]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

PY_ARGS="sync_dataset=$([[ $SYNC_DATASET -eq 1 ]] && echo True || echo False)"
if [[ -n "$PUSH_LANGFUSE" ]]; then
  PY_ARGS="$PY_ARGS, push_langfuse=False"
fi

python3 - <<PY
import json, sys
from butler.ops.eval_regression import run_regression_gate

report = run_regression_gate($PY_ARGS)
print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
print()
print(f"DevEngine: {report.dev_passed}/{report.dev_total} ({report.dev_pass_rate:.0%})")
print(f"Memory:    {report.mem_passed}/{report.mem_total} ({report.mem_pass_rate:.0%})")
if report.scores_pushed:
    print(f"LangFuse:  pushed {report.scores_pushed} scores")
if report.dataset_synced:
    print("Dataset:   WeChat corpus synced")
if not report.passed:
    print("REGRESSION GATE: FAILED", file=sys.stderr)
    for f in report.failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)
print("REGRESSION GATE: PASSED")
PY
