#!/usr/bin/env bash
# Prompt eval gate (PEG P2-5) — pattern rubric, no API key required.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=. pytest tests/test_prompt_eval.py -q "$@"
