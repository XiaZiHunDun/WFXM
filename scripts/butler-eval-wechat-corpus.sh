#!/usr/bin/env bash
# Phase 4: WeChat gateway corpus regression (via EvalIntegrationManager).
#
# Usage:
#   bash scripts/butler-eval-wechat-corpus.sh
#   bash scripts/butler-eval-wechat-corpus.sh --no-langfuse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

NO_LANGFUSE=0
if [[ "${1:-}" == "--no-langfuse" ]]; then
  NO_LANGFUSE=1
fi

ARGS=(eval run --suite wechat_corpus --out "$ROOT/.butler/reports/eval-unified-wechat-corpus.json")
[[ "$NO_LANGFUSE" -eq 1 ]] && ARGS+=(--no-langfuse)

echo "== Butler eval wechat corpus =="
python -m butler.main "${ARGS[@]}"
echo "WECHAT CORPUS GATE: PASSED"
