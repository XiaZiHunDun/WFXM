#!/usr/bin/env bash
# AP-2: Trajectory Compliance Rate gate (strict production corpus + tool boundaries).
# Usage: bash scripts/butler-trajectory-compliance-gate.sh [--strict]
# Env: BUTLER_TCR_THRESHOLD=0.98 (default); warn-only via --warn-only
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
ARGS=()
if [[ "$WARN_ONLY" == "1" ]]; then
  ARGS+=(--warn-only)
fi
python -m butler.ops.tcr_report "${ARGS[@]}"
echo "TCR gate: OK"
