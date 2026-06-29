#!/usr/bin/env bash
# AP-8: Five-dimension agent eval weekly (via EvalIntegrationManager).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "== Butler agent eval weekly =="
python -m butler.main eval run --suite tcr,agent_weekly --warn-only \
  --out "$ROOT/.butler/reports/eval-unified.json"
python -m butler.ops.agent_eval_weekly
echo "Agent eval weekly: OK"
