#!/usr/bin/env bash
# Memory module smoke: recall fixtures + optional reindex hint.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== memory recall fixtures =="
python3 -m pytest tests/test_memory_recall_fixtures.py -q --tb=short "$@"

if [[ "${BUTLER_SEMANTIC_MEMORY:-0}" == "1" ]]; then
  echo ""
  echo "BUTLER_SEMANTIC_MEMORY=1: 若刚改 MEMORY/批准待审，建议再跑:"
  echo "  bash scripts/butler-memory-reindex.sh"
else
  echo ""
  echo "提示: 试点建议 .env 设 BUTLER_SEMANTIC_MEMORY=1 与 BUTLER_QUEUE_PREFETCH=1"
fi
