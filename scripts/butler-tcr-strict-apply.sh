#!/usr/bin/env bash
# Flip fast-gate TCR to --strict when calendar + readiness allow.
# Usage: bash scripts/butler-tcr-strict-apply.sh [--dry-run]
# Runbook: docs/guides/tcr-strict-flip-runbook-2026-07.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--dry-run]"
      echo "Requires tcr-strict-readiness status=ready (see butler-tcr-strict-readiness.sh)."
      exit 0
      ;;
  esac
done

READINESS_JSON="$ROOT/.butler/reports/tcr-strict-readiness.json"
FAST_GATE="$ROOT/scripts/butler-pytest-fast-gate.sh"

echo "== TCR strict apply =="

if ! bash "$ROOT/scripts/butler-tcr-strict-readiness.sh" >/tmp/tcr-readiness.log 2>&1; then
  cat /tmp/tcr-readiness.log
  echo "TCR strict apply: BLOCKED (readiness failed)"
  exit 1
fi
cat /tmp/tcr-readiness.log

status="$(python - <<PY
import json
from pathlib import Path
p = Path("$READINESS_JSON")
print(json.loads(p.read_text(encoding="utf-8")).get("status", "fail"))
PY
)"

if [[ "$status" == "wait" ]]; then
  echo "TCR strict apply: WAIT (calendar not ready — see readiness report)"
  exit 0
fi

if [[ "$status" != "ready" ]]; then
  echo "TCR strict apply: BLOCKED (status=$status)"
  exit 1
fi

if grep -q 'butler-trajectory-compliance-gate.sh --strict' "$FAST_GATE"; then
  echo "fast-gate already uses --strict"
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] would flip warn-only → strict in $FAST_GATE"
  exit 0
fi

sed -i 's/butler-trajectory-compliance-gate.sh --warn-only/butler-trajectory-compliance-gate.sh --strict/' "$FAST_GATE"
echo "Applied: fast-gate TCR is now --strict"
grep trajectory-compliance "$FAST_GATE"
echo ""
echo "Verify: bash scripts/butler-pytest-fast-gate.sh"
