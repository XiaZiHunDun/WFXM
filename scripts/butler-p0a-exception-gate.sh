#!/usr/bin/env bash
# P0-A exception governance gate — hotspot except Exception budgets.
# Usage: bash scripts/butler-p0a-exception-gate.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi
echo "== P0-A exception governance =="
PYTHONPATH=. "$PY" -m pytest tests/test_p0a_exception_governance.py tests/test_best_effort.py -q
echo "P0-A gate: OK"
