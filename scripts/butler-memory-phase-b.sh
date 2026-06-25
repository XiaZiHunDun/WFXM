#!/usr/bin/env bash
# 记忆系统阶段 B：运营配置守门 + recall 冒烟 + 真机话术提示。
# 前置: bash scripts/butler-memory-phase-a.sh
# 用法: bash scripts/butler-memory-phase-b.sh
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

warn=0

echo "=== 阶段 B：运营配置（推荐值）==="
check_env() {
  local name="$1"
  local want="$2"
  local got="${!name:-}"
  if [[ "$got" == "$want" ]]; then
    echo "OK: $name=$got"
  else
    echo "WARN: $name=${got:-<unset>}（推荐 $want）"
    warn=1
  fi
}

check_env BUTLER_SYNC_CONVERSATION_MEMORY 0
if [[ "${BUTLER_QUEUE_PREFETCH:-0}" == "1" ]]; then
  echo "OK: BUTLER_QUEUE_PREFETCH=1"
else
  echo "WARN: BUTLER_QUEUE_PREFETCH 未开（同句复问预取缓存会弱）"
  warn=1
fi
if [[ "${BUTLER_SEMANTIC_MEMORY:-0}" == "1" ]]; then
  echo "OK: BUTLER_SEMANTIC_MEMORY=1（阶段 A 已开）"
else
  echo "FAIL: 请先 bash scripts/butler-memory-phase-a.sh"
  exit 1
fi

echo ""
echo "=== 阶段 B：记忆快照（~/.butler）==="
python3 - <<'PY'
import json
from butler.config import get_butler_home
from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_config import semantic_memory_enabled

home = get_butler_home()
bm = ButlerMemory(home, tenant_id="default")
exp_total = 0
exp_long = 0
if bm.experience:
    rows = bm.experience.get_recent(limit=500)
    exp_total = len(rows)
    exp_long = sum(1 for r in rows if (r.get("category") or "") != "conversation")
vec_rows = bm.semantic.count_rows() if bm.semantic else 0
print(f"  butler_home: {home}")
print(f"  semantic_enabled: {semantic_memory_enabled()}")
print(f"  experience_rows(sample<=500): {exp_total} (non-conversation: {exp_long})")
print(f"  vector_rows: {vec_rows}")
if bm.semantic and vec_rows == 0:
    print("  WARN: 向量表为空 — 跑 butler memory-reindex")
bm.close()
PY

echo ""
echo "=== 阶段 B：recall fixture 冒烟 ==="
bash scripts/butler-memory-smoke.sh

echo ""
echo "=== 阶段 B：post_session 契约 ==="
pytest tests/test_post_session.py tests/test_premise_p1_p2_p6_structural.py::TestP6ExtractionPathExists -q --tb=line

echo ""
echo "=== 阶段 B：月度探针 M1–M7（自动化）==="
if ! bash "$ROOT/scripts/butler-memory-monthly-probe.sh"; then
  echo ""
  echo "FAIL: 记忆月度探针未通过 — 与运营真机表不一致风险"
  echo "  修复后重跑: bash scripts/butler-memory-monthly-probe.sh"
  exit 1
fi

if [[ "$warn" -ne 0 ]]; then
  echo ""
  echo "阶段 B 完成（有 WARN，见上）"
  exit 0
fi
echo ""
echo "阶段 B 自动化守门完成 ✓（真机可选：bash scripts/butler-memory-monthly-probe.sh --manual）"
