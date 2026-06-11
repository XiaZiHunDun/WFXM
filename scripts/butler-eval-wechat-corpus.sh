#!/usr/bin/env bash
# Phase 4: WeChat gateway corpus regression → LangFuse scores.
#
# Usage:
#   bash scripts/butler-eval-wechat-corpus.sh
#   bash scripts/butler-eval-wechat-corpus.sh --no-langfuse
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

PUSH=1
if [[ "${1:-}" == "--no-langfuse" ]]; then
  PUSH=0
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json, sys
from butler.ops.wechat_corpus_eval import run_and_push_wechat_corpus_eval

summary = run_and_push_wechat_corpus_eval(push_langfuse=bool($PUSH))
print(json.dumps(summary, ensure_ascii=False, indent=2))
print()
print(
    f"WeChat corpus: {summary.get('passed')}/{summary.get('total')} "
    f"({float(summary.get('pass_rate') or 0):.0%})"
)
if summary.get("exit_code", 0) != 0:
    print("WECHAT CORPUS GATE: FAILED", file=sys.stderr)
    sys.exit(1)
print("WECHAT CORPUS GATE: PASSED")
PY
