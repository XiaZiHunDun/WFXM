#!/usr/bin/env bash
# 记忆系统阶段 A：语义记忆开关 + fastembed + reindex + MB 基准 + doctor 嵌入检查。
# 用法: bash scripts/butler-memory-phase-a.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

fail=0

echo "=== 阶段 A：配置检查 ==="
sem="${BUTLER_SEMANTIC_MEMORY:-0}"
emb="${BUTLER_EMBEDDING_PROVIDER:-local}"
if [[ "$sem" != "1" && "$sem" != "true" && "$sem" != "yes" && "$sem" != "on" ]]; then
  echo "FAIL: BUTLER_SEMANTIC_MEMORY 未开启（建议 .env 设 BUTLER_SEMANTIC_MEMORY=1）"
  fail=1
else
  echo "OK: BUTLER_SEMANTIC_MEMORY=$sem"
fi
if [[ "$emb" == "local" ]]; then
  echo "WARN: BUTLER_EMBEDDING_PROVIDER=local（hashing）；建议 fastembed"
elif [[ -z "$emb" ]]; then
  echo "WARN: BUTLER_EMBEDDING_PROVIDER 未设（将回退 local/hashing）"
else
  echo "OK: BUTLER_EMBEDDING_PROVIDER=$emb"
fi

echo ""
echo "=== 阶段 A：语义索引重建 ==="
python3 -m butler.main memory-reindex --tenant "${BUTLER_TENANT_ID:-default}"

echo ""
echo "=== 阶段 A：MB1–MB7 生产基准（~/.butler）==="
python3 - <<'PY'
import json
import sys

from butler.config import get_butler_home
from butler.memory.memory_benchmark import run_benchmarks

report = run_benchmarks(get_butler_home())
summary = report.summary()
print(json.dumps(summary, indent=2, ensure_ascii=False))
if summary.get("failed", 0):
    sys.exit(1)
PY

echo ""
echo "=== 阶段 A：doctor 嵌入/语义行 ==="
python3 -m butler.main doctor 2>&1 | grep -E "SEMANTIC|EMBEDDING|Embedding|fastembed|semantic|Recall@3|G2-06" || true

echo ""
echo "=== 阶段 A：pytest 守门（隔离 tmp）==="
pytest tests/test_memory_metrics_benchmark.py -q

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "阶段 A 未通过：请先修正 .env（见 .env.example 记忆段）"
  exit 1
fi
echo ""
echo "阶段 A 完成 ✓"
