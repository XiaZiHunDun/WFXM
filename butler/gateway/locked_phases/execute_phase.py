from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.goal_loop import maybe_run_goal_continuation
from butler.core.todo_continuation import run_with_todo_continuation
from butler.core.loop_types import LoopResult
from butler.execution_context import use_local_project_inventory_gate, use_session_read_recall_gate

from .state import LockedTurnState


def _phase_execute_turn(state: LockedTurnState) -> None:
    with use_session_read_recall_gate(state.session_read_recall_gate):
        with use_local_project_inventory_gate(state.local_project_inventory_gate):
            _phase_execute_turn_inner(state)


def _phase_execute_turn_inner(state: LockedTurnState) -> None:
    ephemeral_system = state.ephemeral_system

    def _run_turn(msg: str) -> "LoopResult":
        run_kwargs: dict[str, Any] = {}
        if ephemeral_system:
            run_kwargs["ephemeral_system"] = ephemeral_system
        try:
            if state.run_callbacks is not None:
                return state.loop.run(
                    msg, run_callbacks=state.run_callbacks, **run_kwargs,
                )
            return state.loop.run(msg, **run_kwargs)
        except TypeError:
            if state.run_callbacks is not None:
                return state.loop.run(msg, run_callbacks=state.run_callbacks)
            return state.loop.run(msg)

    def _run_with_continuations() -> "LoopResult":
        result = run_with_todo_continuation(
            state.loop,
            state.augmented,
            state.session_key,
            run_fn=_run_turn,
            run_callbacks=state.run_callbacks,
        )
        return maybe_run_goal_continuation(
            state.loop,
            result,
            state.session_key,
            run_fn=_run_turn,
        )

    result = safe_best_effort(
        _run_with_continuations,
        label="locked_phases.todo_goal_continuation",
    )
    if result is None:
        result = _run_turn(state.augmented)
    state.result = result