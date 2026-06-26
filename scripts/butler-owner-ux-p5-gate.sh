#!/usr/bin/env bash
# PROD-P5 gate: Owner UX debt (P5-01/02/03 + P4 regression).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "=== P5-01 unit tests ==="
python3 -m pytest tests/test_owner_ux_p5.py -q --tb=short
echo ""
echo "=== P4 regression (required) ==="
bash "$ROOT/scripts/butler-owner-ux-p4-gate.sh"
echo "PROD-P5 GATE: PASS (P5-01/02/03 green; P4 regression green)"
