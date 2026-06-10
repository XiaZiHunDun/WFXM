#!/usr/bin/env bash
# D2-4/D2-5 memory effectiveness metrics smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== memory metrics wiring + benchmark tests =="
python3 -m pytest \
  tests/test_memory_metrics_wiring.py \
  tests/test_memory_metrics_benchmark.py \
  tests/test_phase4_multi_proj.py::TestD26DecayMonitoring \
  -q --tb=line

echo ""
echo "Memory metrics smoke: PASSED"
