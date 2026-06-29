#!/usr/bin/env bash
# AP-8: Five-dimension agent eval weekly report (CuP/TCR/Pass@3).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "== Butler agent eval weekly =="
bash scripts/butler-trajectory-compliance-gate.sh --warn-only
python -m butler.ops.agent_eval_weekly
echo "Agent eval weekly: OK"
