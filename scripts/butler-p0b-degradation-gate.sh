#!/usr/bin/env bash
# P0-B degradation visibility gate.
# Usage: bash scripts/butler-p0b-degradation-gate.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi
echo "== P0-B degradation visibility =="
PYTHONPATH=. "$PY" -m pytest \
  tests/test_degradation_registry.py \
  tests/test_owner_surface.py::test_owner_diagnostic_brief_shows_memory_degradation \
  tests/test_owner_surface.py::test_owner_degradation_brief_line_embedding \
  tests/test_owner_surface.py::test_owner_degradation_brief_line_offline \
  -q
echo "P0-B gate: OK"
