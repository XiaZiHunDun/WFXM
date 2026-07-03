"""Continue gateway turns when session todos remain open after loop completion.

Implements an OMO todo-continuation-enforcer subset.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from butler.core.agent_loop import AgentLoop, LoopResult, LoopStatus
from butler.core.loop_types import LoopTransitionReason

logger = logging.getLogger(__name__)

CONTINUATION_USER_MESSAGE = (
    "[系统续跑] 上一轮已结束，但会话待办仍未完成。"
    "请根据当前待办列表继续执行，完成后更新 session_todos。"
    "不要重复已完成的步骤。"
)


def todo_continuation_enabled() -> bool:
    from butler.env_parse import env_truthy

    return env_truthy("BUTLER_TODO_CONTINUATION", default=True)


def max_continuations() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_TODO_CONTINUATION_MAX", 2, min=0)
    except ValueError:
        return 2


def stagnation_limit() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_TODO_STAGNATION_MAX", 2, min=2)
    except ValueError:
        return 2


def _open_todo_count(session_key: str) -> int:
    from butler.core.session_todos import count_open_todos, session_todos_enabled

    if not session_todos_enabled():
        return 0
    return count_open_todos(session_key)


def should_continue_for_todos(
    result: LoopResult,
    session_key: str,
    *,
    goal_loop_active: bool = False,
) -> bool:
    if goal_loop_active:
        return False
    if not todo_continuation_enabled():
        return False
    if result.status != LoopStatus.COMPLETED:
        return False
    if max_continuations() <= 0:
        return False
    return _open_todo_count(session_key) > 0


def run_with_todo_continuation(
    loop: AgentLoop,
    user_message: str,
    session_key: str,
    *,
    run_fn: Callable[..., LoopResult] | None = None,
    run_callbacks: Any = None,
) -> LoopResult:
    """Run loop; if completed with open todos, inject continuation user messages (capped)."""
    from butler.core.todo_continuation_ops import is_goal_loop_active_safe

    goal_active = is_goal_loop_active_safe(session_key)

    runner = run_fn or (lambda msg: loop.run(msg, run_callbacks=run_callbacks))
    result = runner(user_message)
    if not should_continue_for_todos(result, session_key, goal_loop_active=goal_active):
        return result

    max_n = max_continuations()
    prev_open = _open_todo_count(session_key)
    stagnant = 0
    continuations = 0
    merged_diag = dict(result.diagnostics or {})

    while continuations < max_n:
        open_now = _open_todo_count(session_key)
        if open_now <= 0:
            break
        if open_now >= prev_open:
            stagnant += 1
        else:
            stagnant = 0
        if stagnant >= stagnation_limit():
            merged_diag["todo_continuation_stagnant"] = True
            logger.info(
                "Todo continuation stopped (stagnation) session=%s open=%d",
                session_key,
                open_now,
            )
            break

        continuations += 1
        prev_open = open_now
        loop.diagnostics["todo_continuation_attempt"] = continuations
        next_result = runner(CONTINUATION_USER_MESSAGE)
        merged_diag.update(next_result.diagnostics or {})
        merged_diag["todo_continuation_count"] = continuations
        result = next_result
        if next_result.status != LoopStatus.COMPLETED:
            break
        if not should_continue_for_todos(next_result, session_key, goal_loop_active=goal_active):
            break

    if continuations:
        merged_diag["loop_transition_reason"] = LoopTransitionReason.TURN_COMPLETED.value
        merged_diag["todo_continuation_applied"] = True
        result.diagnostics = merged_diag

    return result
