#!/usr/bin/env bash
# Phase 3: Compare dev delegate variants (B9 + optional SWE live subset).
#
# Usage:
#   bash scripts/butler-eval-experiment.sh
#   bash scripts/butler-eval-experiment.sh --with-swe
#   bash scripts/butler-eval-experiment.sh --no-langfuse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

INCLUDE_SWE=0
PUSH_LANGFUSE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-swe) INCLUDE_SWE=1 ;;
    --no-langfuse) PUSH_LANGFUSE=0 ;;
    -h|--help)
      echo "Usage: $0 [--with-swe] [--no-langfuse]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
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
from butler.ops.eval_experiment import run_eval_experiment

report = run_eval_experiment(
    experiment_id="dev-delegate",
    include_swe=bool($INCLUDE_SWE),
    push_langfuse=bool($PUSH_LANGFUSE),
)
print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
print()
for v in report.variants:
    print(f"{v.variant}: B9 {v.b9_passed}/{v.b9_total} ({v.b9_pass_rate:.0%})", end="")
    if v.swe_total:
        print(f" | SWE {v.swe_passed}/{v.swe_total} ({v.swe_pass_rate:.0%})", end="")
    print(f" [{v.mode}]")
    if v.errors:
        for e in v.errors:
            print(f"  ! {e}", file=sys.stderr)
best = max(report.variants, key=lambda x: (x.b9_pass_rate, x.swe_pass_rate), default=None)
if best:
    print(f"Best variant: {best.variant}")
PY
