"""Tool call batch execution extracted from AgentLoop."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, cast

from butler.core.best_effort import safe_best_effort
from butler.core.batch_sequence_guard import (
    BatchSequenceGuard,
    batch_stale_guard_enabled,
    reorder_reads_before_destructive,
)
from butler.core.finish_tool_truncate import truncate_tool_calls_at_finish
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.parallel_tools import execute_tools_parallel
from butler.core.tool_batch_hooks import build_tool_batch_hooks
from butler.core.tool_batch_post_edit import (
    _EDIT_TOOL_NAMES,
    _OP_NAME_MAP,
    capture_pre_edit_snapshot as _capture_pre_edit_snapshot,
    dev_engine_post_edit as _dev_engine_post_edit,
    fetch_pre_edit_snapshot as _fetch_pre_edit_snapshot,
    plan_mode_post_edit as _plan_mode_post_edit,
    tool_result_outcome as _tool_result_outcome,
)
from butler.core.tool_batch_runner import (
    append_tool_role_messages,
    extract_batch_followups,
    run_sequential_tool_calls,
)
from butler.execution_context import get_current_session_key
from butler.tool_guardrails import ToolCallGuardrailController
from butler.transport.reasoning_replay import store_reasoning_on_message
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolBatchStats:
    """Counters produced while executing a tool batch."""

    tools_started: int = 0
    clarification_question: str | None = None
    waiting_confirmation_message: str | None = None


def append_assistant_tool_calls(
    messages: list[dict[str, Any]],
    response: NormalizedResponse,
) -> None:
    """Append the assistant message that requested tool calls."""
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
    store_reasoning_on_message(assistant_msg, response.reasoning)
    tool_call_records = []
    for tc in response.tool_calls or []:
        tc_id = tc.id or f"call_{uuid.uuid4().hex[:8]}"
        if not tc.id:
            tc.id = tc_id
        tool_call_records.append({
            "id": tc_id,
            "type": "function",
            "function": {"name": tc.name, "arguments": tc.arguments},
        })
    assistant_msg["tool_calls"] = tool_call_records
    messages.append(assistant_msg)


def process_tool_calls(
    *,
    response: NormalizedResponse,
    messages: list[dict[str, Any]],
    config: LoopConfig,
    callbacks: LoopCallbacks,
    guardrails: ToolCallGuardrailController | None,
    dispatch_tool: Callable[[str, dict[str, Any]], str],
    interrupt_check: Callable[[], bool],
    prefetched: dict[str, str] | None = None,
) -> ToolBatchStats:
    """Run a tool batch and append tool role messages."""
    if not response.tool_calls:
        return ToolBatchStats()

    def _maybe_truncate_finish() -> None:
        truncated = truncate_tool_calls_at_finish(list(response.tool_calls))
        if len(truncated) < len(response.tool_calls):
            response.tool_calls = truncated

    safe_best_effort(_maybe_truncate_finish, label="tool_batch.finish_truncate")

    def _maybe_reorder_reads() -> None:
        response.tool_calls = reorder_reads_before_destructive(list(response.tool_calls))

    safe_best_effort(_maybe_reorder_reads, label="tool_batch.reorder_reads")
    if callbacks.on_stream_boundary:
        callbacks.on_stream_boundary()

    append_assistant_tool_calls(messages, response)

    if guardrails and guardrails.halt_decision:
        return ToolBatchStats()

    tools_started = 0
    batch_guard = None

    def _init_batch_guard() -> None:
        nonlocal batch_guard
        if batch_stale_guard_enabled():
            batch_guard = BatchSequenceGuard()

    safe_best_effort(_init_batch_guard, label="tool_batch.stale_guard_init")

    on_start, on_complete, precheck_tool, hook_state = build_tool_batch_hooks(
        callbacks=callbacks,
        guardrails=guardrails,
        batch_guard=batch_guard,
        interrupt_check=interrupt_check,
    )

    def _dispatch_one(name: str, args: dict[str, Any], *, tool_call_id: str = "") -> str:
        from butler.contracts.tool_dispatch_registry import get_tool_dispatch

        port = get_tool_dispatch()
        if port is not None:
            return cast(
                str,
                port.dispatch_one_tool(
                    name,
                    args,
                    tool_call_id=tool_call_id,
                    batch_guard=batch_guard,
                    prefetched=prefetched,
                    guardrails=guardrails,
                    dispatch_tool=dispatch_tool,
                ),
            )
        from butler.core.tool_dispatch import dispatch_one_tool

        return cast(
            str,
            dispatch_one_tool(
                name,
                args,
                tool_call_id=tool_call_id,
                batch_guard=batch_guard,
                prefetched=prefetched,
                guardrails=guardrails,
                dispatch_tool=dispatch_tool,
            ),
        )

    if config.enable_parallel_tools and len(response.tool_calls) > 1:
        pairs = execute_tools_parallel(
            response.tool_calls,
            lambda n, a, *, tool_call_id="": _dispatch_one(n, a, tool_call_id=tool_call_id),
            on_start=on_start,
            on_complete=on_complete,
            check_interrupt=interrupt_check,
            precheck_tool=precheck_tool,
            prefetched=prefetched,
        )
    else:
        pairs = run_sequential_tool_calls(
            list(response.tool_calls),
            dispatch_one=_dispatch_one,
            on_start=on_start,
            on_complete=on_complete,
            guardrails=guardrails,
            batch_guard=batch_guard,
            interrupt_check=interrupt_check,
        )

    session_key = str(get_current_session_key() or "").strip()
    append_tool_role_messages(pairs, messages, session_key=session_key)
    clarification, waiting = extract_batch_followups(pairs)

    return ToolBatchStats(
        tools_started=hook_state.tools_started,
        clarification_question=clarification,
        waiting_confirmation_message=waiting,
    )


from butler.core.tool_batch_finalize import (  # noqa: E402 — P1-C re-exports
    dispatch_tool_with_envelope,
    finalize_fallback_tool_result,
    finalize_guardrail_halt_result,
    finalize_unenveloped_failure_result,
    parse_tool_result_object,
)
