#!/usr/bin/env bash
# O9: B9 LLM delegate end-to-end benchmark (via EvalIntegrationManager).
#
# Usage:
#   bash scripts/butler-eval-llm-benchmark.sh              # oracle (CI)
#   BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh  # live
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

NO_LANGFUSE=0
if [[ "${1:-}" == "--no-langfuse" ]]; then
  NO_LANGFUSE=1
fi

# LIVE mode still uses b9_oracle suite id but resolve_b9_mode inside benchmark
ARGS=(eval run --suite b9_oracle --out "$ROOT/.butler/reports/eval-unified-b9.json")
[[ "$NO_LANGFUSE" -eq 1 ]] && ARGS+=(--no-langfuse)

echo "== Butler eval B9 =="
python -m butler.main "${ARGS[@]}"
echo "B9 BENCHMARK: PASSED"
