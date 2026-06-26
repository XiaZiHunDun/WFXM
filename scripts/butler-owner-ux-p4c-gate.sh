#!/usr/bin/env bash
# PROD-P4-C gate: memory auto-approve + Owner PMF metrics.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "=== PROD-P4-C gate ==="
python3 -m pytest tests/test_owner_ux_p4c.py tests/test_owner_surface.py::test_memory_auto_classify_low_risk_fact -q --tb=short
echo "PROD-P4-C GATE: PASS"
