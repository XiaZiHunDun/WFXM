#!/usr/bin/env bash
# Five-reports regression gate: P5–P10 + PR-F1–F6 subsets (no API keys required).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

echo "== five-reports unit tests (P5–P10) =="
python3 -m pytest \
  tests/test_five_reports_p5.py \
  tests/test_five_reports_p6.py \
  tests/test_five_reports_p7.py \
  tests/test_five_reports_p8.py \
  tests/test_five_reports_p9.py \
  tests/test_five_reports_p10.py \
  tests/test_prompt_eval.py \
  tests/test_mcp_merge.py \
  -q "$@"

echo ""
echo "== five-reports PR-F (LobeHub / PEG / recall / circuit / sessions / handoff) =="
python3 -m pytest \
  tests/test_lobehub_p0_features.py \
  tests/test_peg_prompt_contracts.py \
  tests/test_memory_recall_layers.py \
  tests/test_provider_health.py \
  tests/test_sessions_cli.py \
  tests/test_outcome_reflection.py \
  tests/test_task_orchestrator_handoff.py \
  tests/test_five_reports_f6.py \
  -q "$@"

echo ""
echo "== prompt-eval script =="
./scripts/prompt-eval.sh

echo ""
echo "== registry manifest =="
PYTHONPATH=. python3 -m butler.main registry verify

echo ""
echo "five-reports gate: OK"
