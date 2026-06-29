#!/usr/bin/env bash
# Post-P5 operations cadence — G1-04 weekly + optional release gates (PROD-P6-03).
#
# Usage:
#   bash scripts/butler-ops-cadence.sh --weekly     # G1-04 check-in + agent eval weekly
#   bash scripts/butler-ops-cadence.sh --quarterly  # --weekly + capability baseline (AP 五维)
#   bash scripts/butler-ops-cadence.sh --release    # weekly + P5 gate + fast pytest gate
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
