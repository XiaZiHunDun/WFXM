"""Reasoning trace + plan reason graph (Sprint A/B/C)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from butler.core.plan_reason_graph import (
    append_edge,
    append_node,
    clear_graph,
    load_graph,
    summarize_graph,
)
from butler.core.reasoning_trace import (
    format_reasoning_diagnostic_lines,
    get_plan_mode_graph_appendix,
    maybe_record_llm_reasoning,
    maybe_sync_plan_step_to_graph,
    plan_reason_graph_enabled,
    reasoning_trace_enabled,
    record_reasoning_step as trace_record_reasoning_step,
    record_verify_fail_reflect,
    summarize_reasoning_text,
)
from butler.core.session_transcript import (
    load_transcript_tail,
    record_plan_step,
    record_reflect_step,
)
from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines
from butler.plan.mode import clear_plan_mode, set_plan_mode


@pytest.fixture
def butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_REASONING_TRACE", "1")
    return tmp_path


def test_summarize_reasoning_text_truncates():
    long = "x" * 400
    out = summarize_reasoning_text(long, max_len=50)
    assert len(out) <= 50
    assert out.endswith("…")


def test_record_reasoning_step_in_transcript(butler_home):
    sk = "test:reasoning:_"
    trace_record_reasoning_step(
        sk,
        phase="tool_plan",
        summary="先读 agent_loop 再改 tool_batch",
        tool_intent="read_file,search_files",
        iteration=2,
    )
    rows = load_transcript_tail(sk, max_lines=10)
    assert any(r.get("type") == "reasoning_step" for r in rows)
    payload = next(r for r in rows if r.get("type") == "reasoning_step")
    assert "先读 agent_loop" in str(payload)


def test_maybe_record_llm_reasoning_from_response(butler_home):
    sk = "test:llm:reason:_"
    loop = SimpleNamespace(_session_key=sk)
    tc = SimpleNamespace(name="read_file")
    response = SimpleNamespace(
        reasoning="需要先确认配置默认值",
        content="",
        tool_calls=[tc],
    )
    maybe_record_llm_reasoning(loop, response, iteration=1)
    rows = load_transcript_tail(sk, max_lines=5)
    assert any(r.get("type") == "reasoning_step" for r in rows)


def test_record_reflect_step_and_diagnostics(butler_home):
    sk = "test:reflect:_"
    record_reflect_step(
        sk,
        trigger="verify_fail",
        cause="AssertionError in test_foo",
        strategy="structural: retry with narrower patch",
        detail="fix_count=1",
    )
    lines = format_reasoning_diagnostic_lines(sk)
    assert any("最近反思" in ln for ln in lines)
    diag = format_transcript_diagnostic_lines(sk)
    assert any("推理摘要" in ln for ln in diag)


def test_record_verify_fail_reflect(butler_home):
    sk = "test:verify:reflect:_"
    diag = SimpleNamespace(message="assert 1 == 2", rule="E999", source="pytest")
    verify = SimpleNamespace(
        passed=False,
        diagnostics=[diag],
        output_tail="FAILED test_demo",
        error_count=1,
    )
    state = SimpleNamespace(
        session_key=sk,
        fix_count=1,
        max_fix_rounds=4,
        verify_result=verify,
        _last_fix_hint="",
        _coding_knowledge_ctx=None,
    )
    record_verify_fail_reflect(state, verify)
    rows = load_transcript_tail(sk, max_lines=5)
    assert any(r.get("type") == "reflect_step" for r in rows)


def test_plan_reason_graph_append_and_sync(butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_PLAN_REASON_GRAPH", "1")
    assert plan_reason_graph_enabled()
    sk = "test:plan:graph:_"
    set_plan_mode(sk, True)
    try:
        record_plan_step(
            sk,
            title="agent_loop 在 butler/core",
            step_kind="fact",
            evidence="butler/core/agent_loop.py",
            detail="Loop 主入口",
        )
        graph = load_graph(sk)
        assert len(graph.get("nodes") or []) >= 1
        node = append_node(sk, text="需验证 guardrails", role="hypothesis", title="假设")
        edge = append_edge(sk, from_id=node["id"], to_id=node["id"], rel="refines")
        assert edge["rel"] == "refines"
        stats = summarize_graph(sk)
        assert stats["nodes"] >= 2
        rows = load_transcript_tail(sk, max_lines=20)
        assert any(r.get("type") == "reason_graph" for r in rows)
        maybe_sync_plan_step_to_graph(
            sk,
            title="ignored",
            step_kind="step",
            detail="改 agent_loop_phases",
        )
    finally:
        clear_plan_mode(sk)
        clear_graph(sk)


def test_plan_graph_appendix_only_when_enabled(monkeypatch):
    monkeypatch.delenv("BUTLER_PLAN_REASON_GRAPH", raising=False)
    assert get_plan_mode_graph_appendix() == ""
    monkeypatch.setenv("BUTLER_PLAN_REASON_GRAPH", "1")
    assert "DoT-lite" in get_plan_mode_graph_appendix()


def test_reasoning_trace_disabled(monkeypatch, butler_home):
    monkeypatch.setenv("BUTLER_REASONING_TRACE", "0")
    assert not reasoning_trace_enabled()
    sk = "test:off:_"
    trace_record_reasoning_step(sk, summary="hidden")
    rows = load_transcript_tail(sk, max_lines=5)
    assert not rows


def test_load_plan_mode_appendix_includes_graph_when_enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_PLAN_REASON_GRAPH", "1")
    from butler.plan.mode import load_plan_mode_system_appendix

    body = load_plan_mode_system_appendix()
    assert "step_kind" in body or "fact" in body
    assert "DoT-lite" in body


def test_record_stuck_reflect(butler_home):
    sk = "test:stuck:_"
    loop = SimpleNamespace(
        _session_key=sk,
        _guardrails=SimpleNamespace(
            halt_decision=SimpleNamespace(code="ping_pong", message="read loop", action="block"),
        ),
    )
    from butler.core.reasoning_trace import record_stuck_reflect

    record_stuck_reflect(loop, "工具循环检测")
    rows = load_transcript_tail(sk, max_lines=5)
    assert any(r.get("type") == "reflect_step" for r in rows)


def test_plan_markdown_sync(butler_home, monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_PLAN_REASON_GRAPH", "0")
    sk = "test:plan:sync:_"
    set_plan_mode(sk, True)
    try:
        md = """## 已知事实
- agent_loop 在 butler/core/agent_loop.py 证据: grep

## 步骤
- [step] 改 agent_loop_phases 挂 reasoning hook

## 风险
- 勿破坏 gateway 测试
"""
        from butler.plan.markdown_sync import (
            extract_plan_steps_from_markdown,
            sync_plan_file_to_transcript,
        )

        steps = extract_plan_steps_from_markdown(md)
        assert len(steps) >= 3
        n = sync_plan_file_to_transcript(sk, ".butler/plan/session-plan.md", md)
        assert n >= 3
        rows = load_transcript_tail(sk, max_lines=30)
        plan_rows = [r for r in rows if r.get("type") == "plan_step" and r.get("phase") == "sync"]
        assert len(plan_rows) >= 3
    finally:
        clear_plan_mode(sk)
