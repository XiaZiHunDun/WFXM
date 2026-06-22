#!/usr/bin/env bash
# DoT-lite plan mode smoke (no WeChat): plan markdown → plan_step + reason_graph + edges.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
export BUTLER_SESSION_TRANSCRIPT=1
export BUTLER_REASONING_TRACE=1
export BUTLER_PLAN_REASON_GRAPH=1

SK="smoke:dot:$(date +%s%N)"
python3 - <<PY
from butler.core.plan_reason_graph import load_graph, summarize_graph
from butler.core.reasoning_trace import format_reasoning_diagnostic_lines
from butler.core.session_transcript import load_transcript_tail
from butler.plan.markdown_sync import sync_plan_file_to_transcript
from butler.plan.mode import clear_plan_mode, set_plan_mode

sk = "$SK"
set_plan_mode(sk, True)
md = """## 已知事实
- Loop 入口在 butler/core/agent_loop.py 证据: read_file

## 待验证
- [hypothesis] gateway 已加载最新 commit 假设: upgrade 后 verify 绿

## 步骤
- [step] 微信发 /诊断 看推理摘要

## 风险
- 全量 pytest 仍为技术债
"""
try:
    n = sync_plan_file_to_transcript(sk, ".butler/plan/session-plan.md", md)
    assert n >= 4, n
    graph = load_graph(sk)
    assert len(graph.get("nodes") or []) >= 4, graph
    assert len(graph.get("edges") or []) >= 3, graph
    stats = summarize_graph(sk)
    assert stats.get("edges", 0) >= 3, stats
    rows = load_transcript_tail(sk, max_lines=40)
    plan_sync = [r for r in rows if r.get("type") == "plan_step" and r.get("phase") == "sync"]
    assert len(plan_sync) >= 4, len(plan_sync)
    lines = format_reasoning_diagnostic_lines(sk)
    assert any("Plan 推理图" in ln for ln in lines), lines
    assert any("边" in ln and "0 边" not in ln for ln in lines), lines
    print("dot-lite-smoke: OK")
    print(f"  plan_step sync={len(plan_sync)} graph_nodes={stats.get('nodes')} graph_edges={stats.get('edges')}")
    for ln in lines:
        if "Plan 推理图" in ln:
            print(f"  {ln}")
finally:
    clear_plan_mode(sk)
PY
