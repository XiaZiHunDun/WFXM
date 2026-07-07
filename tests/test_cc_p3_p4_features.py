"""P3/P4 Claude Code提炼: tool budget, stop hook reentry, token budget, transcript, permissions."""

from __future__ import annotations

import json

import pytest

from butler.config import reload_butler_settings
from butler.core.agent_loop import AgentLoop
from butler.core.loop_types import LoopCallbacks, LoopConfig, LoopTransitionReason
from butler.core.reactive_compact import group_messages_by_api_round, try_reactive_compact
from butler.core.tool_result_storage import (
    EMPTY_TOOL_RESULT_TEMPLATE,
    enforce_message_tool_budget,
    message_tool_budget_max_chars,
    normalize_empty_tool_result,
    reset_replacement_state,
    spill_threshold_chars,
)
from butler.core.turn_token_budget import TurnBudgetState, continuation_limits
from butler.permissions import evaluate_permission


def test_per_tool_spill_threshold_read_file_never_spills(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "10")
    assert spill_threshold_chars("read_file") == 0
    assert spill_threshold_chars("grep") >= 256


def test_normalize_empty_tool_result():
    out = normalize_empty_tool_result("", tool_name="grep")
    assert "grep" in out
    assert EMPTY_TOOL_RESULT_TEMPLATE.format(tool_name="grep") == out


def test_enforce_message_tool_budget_truncates(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_MESSAGE_MAX_CHARS", "500")
    reset_replacement_state("sess-budget")
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "t1", "content": "a" * 400},
        {"role": "tool", "tool_call_id": "t2", "content": "b" * 400},
    ]
    out = enforce_message_tool_budget(messages, session_key="sess-budget", max_chars=500)
    total = sum(len(m["content"]) for m in out if m.get("role") == "tool")
    assert total <= 600


def test_turn_budget_state_continuation():
    state = TurnBudgetState(1000)
    assert state.should_continue(100, max_continuations=3, min_delta_tokens=10)
    state.record_continuation(100)
    assert state.continuations_used == 1


def test_group_messages_by_api_round():
    msgs = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "tool", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]
    rounds = group_messages_by_api_round(msgs)
    assert len(rounds) >= 2


def test_try_reactive_compact_drops_old_rounds():
    msgs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ] * 3

    def _shrink(m: list[dict]) -> list[dict]:
        return m[-4:]

    ok, new_msgs, reason = try_reactive_compact(msgs, compress_fn=_shrink, max_rounds_to_drop=2)
    assert ok
    assert reason == "ok"
    assert len(new_msgs) < len(msgs)


def test_reactive_compact_turn_mode_writes_strategy():
    """try_reactive_compact turn-mode 成功时写 compaction_strategy='turns:N' + reactive_compact_strategy."""
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(10):
        msgs.append({"role": "user", "content": f"u-{i}"})
        msgs.append({"role": "assistant", "content": f"a-{i}" * 60})
    diag: dict = {}

    def fake_compress(messages: list[dict]) -> list[dict]:
        return [{"role": "system", "content": "ok"}]

    ok, new_msgs, reason = try_reactive_compact(
        msgs, compress_fn=fake_compress, use_turn_tail=True, diagnostics=diag
    )
    assert ok is True
    assert reason == "ok"
    assert diag.get("compaction_strategy", "").startswith("turns:")
    assert "reactive_compact_strategy" in diag


def test_permission_deny_rule(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir()
    (ws / ".butler" / "permissions.yaml").write_text(
        "rules:\n  - tool: terminal\n    action: deny\n    reason: no shell\n",
        encoding="utf-8",
    )
    decision = evaluate_permission("terminal", {"command": "ls"}, workspace=ws)
    assert decision is not None
    assert not decision.allowed
    assert decision.action == "deny"


def test_stop_hook_reentry_continues_loop(monkeypatch):
    monkeypatch.setenv("BUTLER_TURN_TOKEN_BUDGET", "0")
    calls = {"stop": 0, "llm": 0}

    class FakeClient:
        provider_name = "test"
        model = "test"

        def complete(self, **kwargs):
            calls["llm"] += 1
            from butler.transport.types import NormalizedResponse

            if calls["llm"] == 1:
                return NormalizedResponse(content="done once", tool_calls=[])
            return NormalizedResponse(content="done twice", tool_calls=[])

        def stream(self, **kwargs):
            return self.complete(**kwargs)

    def _stop_hooks(**kwargs):
        calls["stop"] += 1
        from butler.hooks.runner import StopHookResult

        if calls["stop"] == 1:
            return StopHookResult(blocked=True, block_message="need more work")
        return StopHookResult()

    monkeypatch.setattr("butler.core.agent_loop_ops.run_stop_hooks", _stop_hooks)

    loop = AgentLoop(FakeClient(), config=LoopConfig(max_iterations=5, stream=False))
    result = loop.run("hello")
    assert calls["llm"] >= 2
    assert result.transition_reason == LoopTransitionReason.TURN_COMPLETED.value


def test_cache_safe_delegate_v2_fingerprints():
    from butler.core.cache_safe_delegate import compute_cache_safe_bundle

    tools = [{"type": "function", "function": {"name": "read_file"}}]
    bundle = compute_cache_safe_bundle(
        parent_system="parent " * 100,
        child_system="child",
        tools=tools,
        messages=[{"role": "user", "content": "hi"}],
    )
    assert bundle.get("cache_safe_v2") is True
    assert bundle.get("tools_fingerprint")
