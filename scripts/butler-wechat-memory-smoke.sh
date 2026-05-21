#!/usr/bin/env bash
# WeChat memory 补验守门（M1b/O7/O8/M2/M4 对应 pytest，非真机 LLM）
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

echo "== memory wechat gate (pytest) =="
python3 -m pytest \
  tests/test_p0_memory_pilot.py \
  tests/test_memory_p1_p2.py \
  tests/test_memory_m3_m4_smoke.py \
  tests/test_memory_retrieval_triplets.py::test_memory_graph_command \
  tests/test_semantic_memory_p1.py \
  -q --tb=line

echo ""
echo "真机仍建议在微信勾选：/诊断、/记忆图谱、试点日期召回、预取缓存命中"
echo "Memory wechat gate done."
