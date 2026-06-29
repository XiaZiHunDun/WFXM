#!/usr/bin/env bash
# AP-2: Check whether fast-gate may flip TCR from --warn-only to --strict.
# Writes .butler/reports/tcr-strict-readiness.json (status: wait|ready|fail).
# ~2 min (runs full TCR pytest suite in strict mode).
#
# Usage: bash scripts/butler-tcr-strict-readiness.sh
# Env:   BUTLER_TCR_STRICT_AFTER=2026-07-27 (default)
# Runbook: docs/guides/tcr-strict-flip-runbook-2026-07.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

STRICT_AFTER="${BUTLER_TCR_STRICT_AFTER:-2026-07-27}"
today="$(date +%Y-%m-%d)"

echo "== TCR strict readiness =="
echo "today=$today  flip_after=$STRICT_AFTER"

if ! bash "$ROOT/scripts/butler-trajectory-compliance-gate.sh" --strict; then
  echo "TCR strict gate: FAIL (pytest below threshold)"
  exit 1
fi

exec python -m butler.ops.tcr_strict_readiness \
  --today "$today" \
  --strict-after "$STRICT_AFTER"
