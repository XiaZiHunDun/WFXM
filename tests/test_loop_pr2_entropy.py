"""PR2: soft doom-loop nudge, 75% budget warning, compaction IN-PROGRESS."""

from __future__ import annotations

import pytest

from butler.core.compaction_prompt import build_compaction_user_prompt
from butler.core.loop_budget_nudge import (
    maybe_inject_loop_budget_nudges,
    should_nudge_iteration_budget,
    should_nudge_token_budget,
)
from butler.tool_guardrails import ToolCallGuardrailController, doom_loop_threshold


@pytest.mark.module_test
def test_doom_loop_soft_nudge_before_hard_block(monkeypatch):
    monkeypatch.setenv("BUTLER_DOOM_LOOP_THRESHOLD", "3")
    monkeypatch.setenv("BUTLER_DOOM_LOOP_SOFT_NUDGE", "1")
    ctrl = ToolCallGuardrailController()
    args = {"path": "/tmp/x"}
    d1 = ctrl.before_call("read_file", args)
    assert d1.allows_execution
    d2 = ctrl.before_call("read_file", args)
    assert d2.action == "warn"
    assert d2.code == "doom_loop_soft_nudge"
    d3 = ctrl.before_call("read_file", args)
    assert d3.action in {"block", "ask"}
    assert d3.code == "doom_loop"


@pytest.mark.module_test
def test_iteration_budget_nudge_at_75_percent(monkeypatch):
    monkeypatch.setenv("BUTLER_LOOP_BUDGET_WARN_RATIO", "0.75")
    assert should_nudge_iteration_budget(15, 20) is True
    assert should_nudge_iteration_budget(14, 20) is False


@pytest.mark.module_test
def test_token_budget_nudge_at_75_percent(monkeypatch):
    monkeypatch.setenv("BUTLER_LOOP_BUDGET_WARN_RATIO", "0.75")
    assert should_nudge_token_budget(380_000, 500_000) is True
    assert should_nudge_token_budget(100_000, 500_000) is False


@pytest.mark.module_test
def test_maybe_inject_loop_budget_nudges_once_per_turn():
    messages: list[dict] = []
    diag: dict = {}
    assert maybe_inject_loop_budget_nudges(
        messages,
        diag,
        iteration=8,
        max_iterations=10,
        total_tokens=400_000,
        budget_tokens=500_000,
    )
    assert len(messages) == 2
    assert diag.get("loop_iteration_budget_nudge")
    assert diag.get("loop_token_budget_nudge")
    assert maybe_inject_loop_budget_nudges(
        messages,
        diag,
        iteration=9,
        max_iterations=10,
        total_tokens=450_000,
        budget_tokens=500_000,
    ) is False
    assert len(messages) == 2


@pytest.mark.module_test
def test_compaction_prompt_requires_in_progress_marker():
    prompt = build_compaction_user_prompt(transcript="user: hi\nassistant: ok")
    assert "IN-PROGRESS:" in prompt
    assert "Do not mark incomplete work as Done" in prompt or "Do not mark incomplete" in prompt


@pytest.mark.module_test
def test_doom_loop_threshold_default():
    assert doom_loop_threshold() >= 0
