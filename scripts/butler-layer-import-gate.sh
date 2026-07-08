#!/usr/bin/env bash
# ENG-15: layer import dependency gate (v4-layer-model §4).
# Usage: bash scripts/butler-layer-import-gate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "== Butler ENG-15 layer import gate =="
PYTHON_BIN="$(command -v python || command -v python3)"
"${PYTHON_BIN}" -m pytest tests/test_eng15_layer_dependency_matrix.py -q --tb=line
echo "ENG-15 layer import gate: OK"
