#!/usr/bin/env bash
# 记忆系统阶段 C：IndexSync 统一写入 + 向量陈旧检测 + 守门测试。
# 前置: bash scripts/butler-memory-phase-b.sh
# 用法: bash scripts/butler-memory-phase-c.sh
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

if [[ "${BUTLER_SEMANTIC_MEMORY:-0}" != "1" ]]; then
  echo "FAIL: 请先 bash scripts/butler-memory-phase-a.sh"
  exit 1
fi

echo "=== 阶段 C：IndexSync + 向量陈旧检测 ==="
python3 - <<'PY'
from butler.config import get_butler_home
from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_health import drift_from_butler_memory

home = get_butler_home()
bm = ButlerMemory(home, tenant_id="default")
drift = drift_from_butler_memory(bm)
print(f"  butler_home: {home}")
print(f"  experience_indexable: {drift.get('experience_indexable', 0)}")
print(f"  experience_vectors: {drift.get('experience_vectors', 0)}")
print(f"  semantic_index_gap: {drift.get('semantic_index_gap', 0)}")
if drift.get("semantic_index_stale"):
    print("  WARN: 向量索引陈旧 — 运行 butler memory-reindex")
elif drift.get("skipped"):
    print("  SKIP: semantic 未启用或无向量表")
else:
    print("  OK: experience 向量同步正常")
bm.close()
PY

echo ""
echo "=== 阶段 C：守门 pytest ==="
pytest tests/test_memory_phase_c.py tests/test_semantic_memory.py \
  tests/test_memory_metrics_benchmark.py tests/test_post_session.py -q --tb=line

echo ""
echo "阶段 C 自动化守门完成 ✓"
