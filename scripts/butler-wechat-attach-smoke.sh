#!/usr/bin/env bash
# WeChat md/txt attachment smoke: unit + /详细 handler integration.
# Usage: bash scripts/butler-wechat-attach-smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

echo "== WeChat attach smoke =="
"$PY" -m pytest -q --tb=line \
  tests/test_wechat_text_export.py \
  tests/gateway/test_wechat_attach_detail.py \
  "$@"

echo ""
echo "WeChat attach smoke: OK"
