#!/usr/bin/env bash
# Phase 5 gate — O9 B9 + Track C multi-project.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

echo "=== Phase 5 smoke ==="
echo ""

echo "== [O9] B9 LLM delegate benchmark (oracle) =="
bash "$ROOT/scripts/butler-eval-llm-benchmark.sh"

echo ""
echo "== [C1] project register / git URL tests =="
python3 -m pytest tests/test_phase5_multi_project.py::TestC1ExternalRepo -q --tb=line

echo ""
echo "== [C2-C4] multi-project policy + Lead + templates =="
python3 -m pytest tests/test_phase5_multi_project.py -q --tb=line

echo ""
echo "== [C3] LingWen + Demo Lead smokes =="
bash "$ROOT/scripts/butler-lingwen-lead-smoke.sh"
bash "$ROOT/scripts/butler-demo-lead-smoke.sh"

echo ""
echo "== [O9] phase5 unit tests =="
python3 -m pytest tests/test_phase5_llm_benchmark.py -q --tb=line

echo ""
echo "Phase 5 automated gate: PASSED"
echo "可选: BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh"
echo "详见 docs/guides/phase5-multi-project-runbook.md"
