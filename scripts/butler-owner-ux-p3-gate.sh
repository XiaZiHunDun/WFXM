#!/usr/bin/env bash
# PROD-P3 Owner UX gate — switch hints, gate templates, route hints.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
echo "=== PROD-P3 Owner UX gate ==="
python3 -m pytest tests/test_owner_ux_p3.py tests/test_project_manager.py -q --tb=line
echo "PROD-P3 GATE: PASS"
