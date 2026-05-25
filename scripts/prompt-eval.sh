#!/usr/bin/env bash
# Prompt eval gate (PEG P2-5) — pattern rubric + optional corpus mock subset.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=. pytest tests/test_prompt_eval.py tests/test_five_reports_p7.py tests/test_five_reports_p9.py tests/test_five_reports_p10.py -q "$@"
