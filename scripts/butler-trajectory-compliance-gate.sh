#!/usr/bin/env bash
# AP-2: Trajectory Compliance Rate gate (via EvalIntegrationManager).
# Usage: bash scripts/butler-trajectory-compliance-gate.sh [--strict|--warn-only]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

WARN_ONLY=1
for arg in "$@"; do
  case "$arg" in
    --strict) WARN_ONLY=0 ;;
    --warn-only) WARN_ONLY=1 ;;
  esac
done

echo "== Butler TCR gate =="
RUN_ARGS=(eval run --suite tcr --out "$ROOT/.butler/reports/eval-unified-tcr.json")
if [[ "$WARN_ONLY" == "1" ]]; then
  RUN_ARGS+=(--warn-only)
fi
python -m butler.main "${RUN_ARGS[@]}"
echo "TCR gate: OK"
