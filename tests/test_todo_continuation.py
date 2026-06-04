"""Tests for todo continuation enforcer."""

from __future__ import annotations

from unittest.mock import MagicMock

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.core.loop_types import LoopTransitionReason
from butler.core.todo_continuation import (
    max_continuations,
    should_continue_for_todos,
    todo_continuation_enabled,
)


def _completed_result() -> LoopResult:
    return LoopResult(
        status=LoopStatus.COMPLETED,
        transition_reason=LoopTransitionReason.TURN_COMPLETED.value,
        final_response="done",
        reasoning=None,
        messages=[],
        iterations=1,
        total_tokens=10,
        tool_calls_made=0,
        elapsed_seconds=0.1,
        diagnostics={},
    )


def test_should_continue_when_open_todos(monkeypatch):
    monkeypatch.setenv("BUTLER_TODO_CONTINUATION", "1")
    assert todo_continuation_enabled()
    monkeypatch.setattr(
        "butler.core.todo_continuation._open_todo_count",
        lambda _sk: 2,
    )
    assert should_continue_for_todos(_completed_result(), "sess")


def test_should_not_continue_when_goal_loop(monkeypatch):
    monkeypatch.setenv("BUTLER_TODO_CONTINUATION", "1")
    monkeypatch.setattr(
        "butler.core.todo_continuation._open_todo_count",
        lambda _sk: 2,
    )
    assert not should_continue_for_todos(
        _completed_result(),
        "sess",
        goal_loop_active=True,
    )


def test_run_with_todo_continuation_caps(monkeypatch):
    monkeypatch.setenv("BUTLER_TODO_CONTINUATION", "1")
    monkeypatch.setenv("BUTLER_TODO_CONTINUATION_MAX", "2")
    monkeypatch.setattr(
        "butler.core.todo_continuation._open_todo_count",
        lambda _sk: 1,
    )
    monkeypatch.setattr(
        "butler.core.goal_loop.is_goal_loop_active",
        lambda _sk: False,
    )
    loop = MagicMock()  # noqa: magicmock-no-spec — todo continuation facade (loop)
    calls: list[str] = []

    def fake_run(msg: str) -> LoopResult:
        calls.append(msg)
        return _completed_result()

    from butler.core.todo_continuation import run_with_todo_continuation

    run_with_todo_continuation(loop, "hello", "sess", run_fn=fake_run)
    assert calls[0] == "hello"
    assert 1 < len(calls) <= 1 + max_continuations()
