#!/usr/bin/env bash
# Five-reports P5–P10 regression gate (no API keys required).
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
echo "== prompt-eval script =="
./scripts/prompt-eval.sh

echo ""
echo "== registry manifest =="
PYTHONPATH=. python3 -m butler.main registry verify

echo ""
echo "five-reports gate: OK"
