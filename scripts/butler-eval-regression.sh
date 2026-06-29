#!/usr/bin/env bash
# O7: DevEngine B1–B8 + Memory MB1–MB7 regression gate (via EvalIntegrationManager).
#
# Usage:
#   bash scripts/butler-eval-regression.sh
#   bash scripts/butler-eval-regression.sh --sync-dataset
#   bash scripts/butler-eval-regression.sh --no-langfuse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

SYNC_DATASET=0
NO_LANGFUSE=0
for arg in "$@"; do
  case "$arg" in
    --sync-dataset) SYNC_DATASET=1 ;;
    --no-langfuse) NO_LANGFUSE=1 ;;
    -h|--help)
      echo "Usage: $0 [--sync-dataset] [--no-langfuse]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

ARGS=(eval run --suite regression --out "$ROOT/.butler/reports/eval-unified-regression.json")
[[ "$SYNC_DATASET" -eq 1 ]] && ARGS+=(--sync-dataset)
[[ "$NO_LANGFUSE" -eq 1 ]] && ARGS+=(--no-langfuse)

echo "== Butler eval regression =="
python -m butler.main "${ARGS[@]}"
echo "REGRESSION GATE: PASSED"
