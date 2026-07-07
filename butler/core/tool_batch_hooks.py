"""Hook helpers for ``process_tool_calls`` (P1-C)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.core.loop_types import LoopCallbacks
from butler.tool_guardrails import ToolCallGuardrailController, synthetic_result
from butler.execution_context import get_current_workflow_step
from butler.core.delegate_context import get_parent_messages
from butler.core.session_transcript import record_tool_action
from butler.execution_context import get_current_session_key
from butler.ops.runtime_metrics import inc
from butler.ops.cost_tracker import get_session_cost
from butler.core.pim_state import on_pim_tool_success
from butler.core.tool_batch_finalize import finalize_fallback_tool_result
from butler.core.batch_sequence_guard import stale_skip_result


@dataclass
class ToolBatchHookState:
    tools_started: int = 0


def transcript_source_for_batch() -> str:
    def _probe() -> str:

        if get_current_workflow_step():
            return "workflow"

        if get_parent_messages():
            return "delegate"
        return "loop"

    return safe_best_effort(_probe, label="tool_batch.transcript_source", default="loop") or "loop"


def build_tool_batch_hooks(
    *,
    callbacks: LoopCallbacks,
    guardrails: ToolCallGuardrailController | None,
    batch_guard: Any,
    interrupt_check: Callable[[], bool],
) -> tuple[Callable[[str, dict[str, Any]], None], Callable[[str, str], None], Callable[[str, dict[str, Any]], str | None], ToolBatchHookState]:
    """Return (on_start, on_complete, precheck_tool, mutable hook state)."""
    state = ToolBatchHookState()

    def on_start(name: str, args: dict[str, Any]) -> None:
        state.tools_started += 1

        def _record_transcript() -> None:
            import json as _json


            sk = str(get_current_session_key() or "").strip()
            if sk:
                record_tool_action(
                    sk,
                    tool_name=name,
                    args_preview=_json.dumps(args, ensure_ascii=False, default=str)[:400],
                    source=transcript_source_for_batch(),
                )

        safe_best_effort(_record_transcript, label="tool_batch.transcript_on_start")
        if callbacks.on_tool_start:
            callbacks.on_tool_start(name, args)

    def on_complete(name: str, result: str) -> None:
        from butler.core.tool_batch import _tool_result_outcome

        def _record_metrics() -> None:

            outcome = _tool_result_outcome(result)
            tool_label = str(name or "?")[:48]
            inc("tool_call", labels={"tool": tool_label, "outcome": outcome})

        safe_best_effort(_record_metrics, label="tool_batch.metrics_on_complete")

        def _record_cost() -> None:

            session_key = str(get_current_session_key() or "").strip()
            if session_key:
                get_session_cost(session_key).record_tool_call(name)

        safe_best_effort(_record_cost, label="tool_batch.cost_on_complete")

        def _record_pim() -> None:

            outcome = _tool_result_outcome(result)
            if outcome == "ok":
                on_pim_tool_success(name)

        safe_best_effort(_record_pim, label="tool_batch.pim_on_complete")
        if callbacks.on_tool_complete:
            callbacks.on_tool_complete(name, result)

    def precheck_tool(name: str, args: dict[str, Any]) -> str | None:

        if interrupt_check():
            return cast(
                str,
                finalize_fallback_tool_result(
                    name,
                    args,
                    {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
                ),
            )
        if guardrails and guardrails.halt_decision:
            return cast(
                str,
                finalize_fallback_tool_result(
                    name,
                    args,
                    synthetic_result(guardrails.halt_decision),
                ),
            )
        if batch_guard is not None and batch_guard.should_skip_stale_read(name, args):

            return cast(
                str,
                finalize_fallback_tool_result(
                    name,
                    args,
                    stale_skip_result(name, args, guard=batch_guard),
                ),
            )
        return None

    return on_start, on_complete, precheck_tool, state


__all__ = [
    "ToolBatchHookState",
    "build_tool_batch_hooks",
    "transcript_source_for_batch",
]
