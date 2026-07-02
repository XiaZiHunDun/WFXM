"""Sequential tool-batch execution and message assembly (P1-C)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.tool_guardrails import ToolCallGuardrailController, synthetic_result


def run_sequential_tool_calls(
    tool_calls: list[Any],
    *,
    dispatch_one: Callable[..., str],
    on_start: Callable[[str, dict], None],
    on_complete: Callable[[str, str], None],
    guardrails: ToolCallGuardrailController | None,
    batch_guard: Any,
    interrupt_check: Callable[[], bool],
) -> list[tuple[Any, str]]:
    """Execute tool calls one-by-one; honor interrupt and guardrail halt."""
    from butler.core.batch_sequence_guard import stale_skip_result
    from butler.core.tool_batch import finalize_fallback_tool_result

    pairs: list[tuple[Any, str]] = []
    batch_interrupted = False
    for tc in tool_calls:
        from butler.core.tool_batch_runner_ops import parse_tool_call_args_safe

        args = parse_tool_call_args_safe(tc)
        if batch_interrupted or interrupt_check():
            batch_interrupted = True
            result = finalize_fallback_tool_result(
                tc.name,
                args,
                {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
            )
            pairs.append((tc, result))
            continue
        if guardrails and guardrails.halt_decision:
            pairs.append((
                tc,
                finalize_fallback_tool_result(
                    tc.name,
                    args,
                    synthetic_result(guardrails.halt_decision),
                ),
            ))
            continue
        if batch_guard is not None and batch_guard.should_skip_stale_read(tc.name, args):
            pairs.append((
                tc,
                finalize_fallback_tool_result(
                    tc.name,
                    args,
                    stale_skip_result(tc.name, args, guard=batch_guard),
                ),
            ))
            continue
        on_start(tc.name, args)
        result = dispatch_one(tc.name, args, tool_call_id=str(tc.id or ""))
        on_complete(tc.name, result)
        pairs.append((tc, result))
        if interrupt_check():
            batch_interrupted = True
    return pairs


def append_tool_role_messages(
    pairs: list[tuple[Any, str]],
    messages: list[dict],
    *,
    session_key: str,
) -> None:
    from butler.core.steer import apply_steer_to_tool_results
    from butler.core.tool_result_storage import (
        maybe_spill_tool_result,
        normalize_empty_tool_result,
    )

    for tc, result in pairs:
        normalized = normalize_empty_tool_result(result, tool_name=tc.name)
        content = maybe_spill_tool_result(
            normalized,
            tool_name=tc.name,
            tool_use_id=tc.id or "",
            session_key=session_key,
        )
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": content,
        })
    apply_steer_to_tool_results(messages, len(pairs))


def extract_batch_followups(
    pairs: list[tuple[Any, str]],
) -> tuple[str | None, str | None]:
    """Return (clarification_question, waiting_confirmation_message) if any."""
    from butler.core.tool_batch import parse_tool_result_object

    clarification: str | None = None
    waiting: str | None = None
    for tc, result in pairs:
        payload = parse_tool_result_object(result)
        if isinstance(payload, dict) and payload.get("code") == "TWO_PHASE_PENDING":
            waiting = str(payload.get("error") or "").strip() or None
            if waiting:
                break
        if tc.name != "ask_clarification":
            continue
        if isinstance(payload, dict) and payload.get("code") == "CLARIFICATION":
            clarification = str(payload.get("question") or "").strip() or None
            if clarification:
                break
    return clarification, waiting


__all__ = [
    "append_tool_role_messages",
    "extract_batch_followups",
    "run_sequential_tool_calls",
]
