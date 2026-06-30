#!/usr/bin/env bash
# P1-C core module split gate.
# Usage: bash scripts/butler-p1c-gate.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi
echo "== P1-C module split =="
PYTHONPATH=. "$PY" -m pytest \
  tests/test_p1c_module_split.py \
  tests/test_turn_compaction.py \
  tests/test_tool_result_storage.py \
  tests/test_cc_p3_p4_features.py \
  -q
echo "P1-C gate: OK"
