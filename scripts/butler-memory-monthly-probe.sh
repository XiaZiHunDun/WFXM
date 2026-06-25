#!/usr/bin/env bash
# Memory monthly probe — M1–M7 automated gate (pytest) + optional WeChat manual hints.
#
# Usage:
#   bash scripts/butler-memory-monthly-probe.sh
#   bash scripts/butler-memory-monthly-probe.sh --log      # append pilot-log row on PASS
#   bash scripts/butler-memory-monthly-probe.sh --manual   # print 5-min WeChat script only
#
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG=0
MANUAL=0
for arg in "$@"; do
  case "$arg" in
    --log) LOG=1 ;;
    --manual) MANUAL=1 ;;
    -h|--help)
      sed -n '1,10p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

_wechat_manual() {
  cat <<'EOF'
微信 5 分钟月度探针（灵文1号；自动化绿后可选真机复验）：

  1. /诊断
  2. 灵文试点统一测试是哪天？
  3. 我们决定下周试点 Redis → /记忆待审 → /拒绝记忆 1
  4. 重复发第 2 句 → /诊断（预取缓存: 命中）
  5. 项目用什么技术栈？顶层有哪些目录？
  6. /新对话 → 我们刚才聊过什么？
  7. 请记住：月度探针打卡 YYYY-MM-DD → /记忆待审 → /批准记忆 全部

详见 docs/guides/memory-ops.md §微信 5 分钟月度探针
EOF
}

if [[ "$MANUAL" -eq 1 ]]; then
  _wechat_manual
  exit 0
fi

STAMP="$(date +%Y-%m-%d)"
FAIL=0

echo "=== Butler memory monthly probe ($STAMP) ==="
echo "semantic=${BUTLER_SEMANTIC_MEMORY:-0} prefetch=${BUTLER_QUEUE_PREFETCH:-0}"
echo ""

if [[ "${BUTLER_SEMANTIC_MEMORY:-0}" != "1" ]]; then
  echo "FAIL: BUTLER_SEMANTIC_MEMORY 未开 — 先 bash scripts/butler-memory-phase-a.sh"
  exit 1
fi

_probe() {
  local id="$1"
  local desc="$2"
  shift 2
  printf "  %-3s " "$id"
  if python3 -m pytest "$@" -q --tb=line >/dev/null 2>&1; then
    echo "✅  $desc"
    return 0
  fi
  echo "❌  $desc"
  FAIL=1
  return 0
}

_probe_optional() {
  local id="$1"
  local desc="$2"
  shift 2
  printf "  %-3s " "$id"
  if python3 -m pytest "$@" -q --tb=line >/dev/null 2>&1; then
    echo "✅  $desc"
  else
    echo "⚠️  $desc（加分项，不计入 FAIL）"
  fi
}

echo "M1–M7 自动化探针（handler/记忆模块 pytest，非真机 LLM）："
_probe M1 "/诊断 记忆分层与向量快照" \
  tests/test_semantic_memory_p1.py::TestDiagnosticsNoSession
_probe M2 "paraphrase 召回统一测试日" \
  tests/test_semantic_memory_p1.py::TestProjectPrefetchAndFence::test_search_project_memory_vectors
_probe M3 "Pending → /拒绝记忆 向量清理" \
  tests/test_memory_m3_m4_smoke.py::TestM3RejectPendingGateway::test_reject_via_slash_command
_probe M4 "同句预取缓存命中" \
  tests/test_memory_m3_m4_smoke.py::TestM4PrefetchCacheHit::test_repeat_query_hits_warm_cache
_probe M5 "novel-factory / 关键词 facts 召回" \
  tests/test_memory_recall_fixtures.py::TestMemoryRecallFixtures::test_keyword_fallback_case \
  tests/test_memory_p1_p2.py::TestNovelFactoryStatusWorkflow::test_builtin_resolves_with_steps
_probe M6 "/新对话 清空上下文摘要" \
  tests/test_p0_memory_pilot.py::TestNewCommandMemoryFeedback::test_new_appends_extraction_summary
_probe M7 "记住 → 批准 → 向量同步" \
  tests/test_semantic_memory_p1.py::TestProjectMemoryVectors::test_remember_pending_then_approve_syncs_vectors

echo ""
_probe_optional M1b "/记忆图谱 三元组展示" \
  tests/test_memory_retrieval_triplets.py::test_memory_graph_command
_probe_optional M1c "observation store 迁移/诊断" \
  tests/test_observation_migrate.py

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "MEMORY MONTHLY PROBE: FAIL（修复后重跑 phase-b / monthly-probe）"
  exit 1
fi

echo "MEMORY MONTHLY PROBE: PASS (M1–M7)"
echo ""
_wechat_manual

if [[ "$LOG" -eq 1 ]]; then
  LOG_FILE="$ROOT/projects/LingWen1/docs/pilot-log.md"
  ROW="| $STAMP | **记忆月度探针** | butler-memory-monthly-probe.sh M1–M7 PASS |"
  if [[ -f "$LOG_FILE" ]] && ! grep -q "记忆月度探针.*$STAMP" "$LOG_FILE" 2>/dev/null; then
    sed -i "/^|------|/a\\$ROW" "$LOG_FILE"
    echo ""
    echo "Appended: $LOG_FILE"
  fi
fi

exit 0
