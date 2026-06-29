#!/usr/bin/env bash
# Flip fast-gate TCR to --strict when calendar + readiness allow.
# Usage: bash scripts/butler-tcr-strict-apply.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--dry-run]"
      exit 0
      ;;
  esac
done

STRICT_AFTER="${BUTLER_TCR_STRICT_AFTER:-2026-07-27}"
today="$(date +%Y-%m-%d)"
FAST_GATE="$ROOT/scripts/butler-pytest-fast-gate.sh"

echo "== TCR strict apply =="

if ! bash "$ROOT/scripts/butler-tcr-strict-readiness.sh" >/tmp/tcr-readiness.log 2>&1; then
  cat /tmp/tcr-readiness.log
  echo "TCR strict apply: BLOCKED (readiness failed)"
  exit 1
fi

if [[ "$today" < "$STRICT_AFTER" ]]; then
  echo "Calendar: WAIT until $STRICT_AFTER (today=$today)"
  cat /tmp/tcr-readiness.log | tail -3
  exit 0
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
