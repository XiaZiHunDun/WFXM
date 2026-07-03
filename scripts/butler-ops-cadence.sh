#!/usr/bin/env bash
# Post-P5 operations cadence — G1-04 weekly + optional release gates (PROD-P6-03).
#
# Usage:
#   bash scripts/butler-ops-cadence.sh --weekly     # G1-04 check-in + agent eval weekly
#   bash scripts/butler-ops-cadence.sh --quarterly  # --weekly + capability baseline (AP 五维)
#   bash scripts/butler-ops-cadence.sh --release    # weekly + P5 gate + fast pytest gate
#   bash scripts/p0a-scan-remaining.sh              # P0-A 主模块差集（非 cadence 门禁）
#
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE=""
for arg in "$@"; do
  case "$arg" in
    --weekly|--release|--quarterly) MODE="$arg" ;;
    -h|--help)
      sed -n '1,9p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg (use --weekly, --quarterly, or --release)" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Specify --weekly, --quarterly, or --release" >&2
  exit 2
fi

FAIL=0

echo "=== Butler ops cadence ($MODE) ==="

if ! bash "$ROOT/scripts/butler-g1-04-weekly-checkin.sh" --log; then
  # Exit 2 during observation window is expected (closure not ready).
  ec=$?
  if [[ "$ec" -eq 2 ]]; then
    echo "(G1-04: window open — exit 2 expected)"
  else
    FAIL=1
  fi
fi

if [[ "$MODE" == "--release" ]]; then
  bash "$ROOT/scripts/butler-owner-ux-p5-gate.sh" || FAIL=1
  bash "$ROOT/scripts/butler-pytest-fast-gate.sh" || FAIL=1
fi

if [[ "$MODE" == "--weekly" || "$MODE" == "--quarterly" ]]; then
  bash "$ROOT/scripts/butler-agent-eval-weekly.sh" || FAIL=1
  echo ""
  echo "-- P0-A remaining main modules (informational) --"
  bash "$ROOT/scripts/p0a-scan-remaining.sh" || true
  echo ""
  echo "-- TCR strict readiness (flip runbook: docs/guides/tcr-strict-flip-runbook-2026-07.md) --"
  if bash "$ROOT/scripts/butler-tcr-strict-readiness.sh"; then
    if [[ -f "$ROOT/.butler/reports/tcr-strict-readiness.json" ]]; then
      python - <<'PY'
import json
from pathlib import Path
r = json.loads(Path(".butler/reports/tcr-strict-readiness.json").read_text(encoding="utf-8"))
print(f"(TCR readiness logged: status={r.get('status')} days_until_flip={r.get('days_until_flip')})")
PY
    fi
  else
    echo "(TCR readiness: FAIL — non-blocking for weekly cadence)"
  fi
fi

if [[ "$MODE" == "--quarterly" ]]; then
  bash "$ROOT/scripts/butler-capability-baseline.sh" --archive || FAIL=1
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "=== ops cadence: FAIL ==="
  exit 1
fi
echo "=== ops cadence: OK ==="
exit 0
