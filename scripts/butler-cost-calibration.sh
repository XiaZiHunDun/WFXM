#!/usr/bin/env bash
# D4 cost calibration smoke: rollup + baseline + premise gates
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "=== D4 cost calibration unit ==="
python -m pytest tests/test_cost_calibration.py -q

echo "=== P-COST premise ==="
python -m pytest tests/test_premise_v3_new.py -k PCOST -q

echo "=== Support line E (token cost) ==="
python -m pytest tests/test_support_line_e.py -k cost -q

echo "=== CLI report (empty ok) ==="
python -m butler.ops.cost_calibration_cli report || true

echo "OK: D4 cost calibration gates passed"
