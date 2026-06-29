#!/usr/bin/env bash
# AP-2: Check whether fast-gate may flip TCR from --warn-only to --strict.
# Does not modify any file. ~2 min (runs full TCR pytest suite).
#
# Usage: bash scripts/butler-tcr-strict-readiness.sh
# Env:   BUTLER_TCR_STRICT_AFTER=2026-07-27 (default)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

STRICT_AFTER="${BUTLER_TCR_STRICT_AFTER:-2026-07-27}"
today="$(date +%Y-%m-%d)"
REPORT="$ROOT/.butler/reports/tcr-latest.json"
FAST_GATE="$ROOT/scripts/butler-pytest-fast-gate.sh"

echo "== TCR strict readiness =="
echo "today=$today  flip_after=$STRICT_AFTER"

if ! bash "$ROOT/scripts/butler-trajectory-compliance-gate.sh" --strict; then
  echo "TCR strict: FAIL — rate below threshold; do not flip fast-gate"
  exit 1
fi

if [[ ! -f "$REPORT" ]]; then
  echo "TCR strict: missing $REPORT" >&2
  exit 1
fi

python - <<PY
import json
from pathlib import Path

report = json.loads(Path("$REPORT").read_text(encoding="utf-8"))
rate = report.get("trajectory_compliance_rate", 0)
print(f"TCR rate: {rate * 100:.2f}%  passed={report.get('passed')}/{report.get('total')}")
PY

if [[ "$today" < "$STRICT_AFTER" ]]; then
  echo "Calendar: WAIT — stable weekly through $STRICT_AFTER, then flip:"
  echo "  sed -i 's/butler-trajectory-compliance-gate.sh --warn-only/butler-trajectory-compliance-gate.sh --strict/' $FAST_GATE"
  exit 0
fi

echo "READY: flip fast-gate TCR to --strict:"
echo "  sed -i 's/butler-trajectory-compliance-gate.sh --warn-only/butler-trajectory-compliance-gate.sh --strict/' $FAST_GATE"
exit 0
