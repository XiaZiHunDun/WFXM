"""Tool call batch execution extracted from AgentLoop."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.parallel_tools import execute_tools_parallel
from butler.core.steer import apply_steer_to_tool_results
from butler.tool_guardrails import (
    ToolCallGuardrailController,
    append_guidance,
    synthetic_result,
)
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


def _tool_result_outcome(result: str) -> str:
    text = (result or "").strip()
    if not text:
        return "ok"
    head = text[:240].lower()
    if head.startswith("error:") or head.startswith('{"error"'):
        return "error"
    if text.startswith("{") and '"error"' in head:
        return "error"
    return "ok"


@dataclass(frozen=True)
class ToolBatchStats:
    """Counters produced while executing a tool batch."""

    tools_started: int = 0


def append_assistant_tool_calls(
    messages: list[dict],
    response: NormalizedResponse,
) -> None:
    """Append the assistant message that requested tool calls."""
    from butler.transport.reasoning_replay import store_reasoning_on_message

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
    messages: list[dict],
    config: LoopConfig,
    callbacks: LoopCallbacks,
    guardrails: ToolCallGuardrailController | None,
    dispatch_tool: Callable[[str, dict], str],
    interrupt_check: Callable[[], bool],
    prefetched: dict[str, str] | None = None,
) -> ToolBatchStats:
    """Run a tool batch and append tool role messages."""
    if not response.tool_calls:
        return ToolBatchStats()

    if callbacks.on_stream_boundary:
        callbacks.on_stream_boundary()

    append_assistant_tool_calls(messages, response)

    if guardrails and guardrails.halt_decision:
        return ToolBatchStats()

    tools_started = 0

    from butler.core.tool_call_limits import get_tool_call_limiter
    from butler.core.tool_retry import run_tool_with_retry
    from butler.core.tool_result_cache import get_cached_result, set_cached_result
    from butler.execution_context import get_current_session_key

    def _dispatch_one(name: str, args: dict, *, tool_call_id: str = "") -> str:
        if prefetched and tool_call_id and tool_call_id in prefetched:
            return prefetched[tool_call_id]
        session_key = str(get_current_session_key() or "").strip()
        cached = get_cached_result(name, args, session_key=session_key)
        if cached is not None:
            return cached
        blocked = get_tool_call_limiter().before_call(name)
        if blocked:
            return finalize_fallback_tool_result(name, args, blocked)
        if guardrails:
            before = guardrails.before_call(name, args)
            if before.action == "ask" and before.code == "doom_loop":
                try:
                    from butler.permission_doom_loop import check_doom_loop_ask

                    block_msg = check_doom_loop_ask(before, name, args)
                    if block_msg:
                        from butler.tool_guardrails import GuardrailDecision, synthetic_result

                        ask_dec = GuardrailDecision(
                            action="block",
                            code="doom_loop",
                            message=block_msg,
                            tool_name=name,
                        )
                        return finalize_fallback_tool_result(
                            name, args, synthetic_result(ask_dec)
                        )
                except Exception:
                    return finalize_fallback_tool_result(name, args, synthetic_result(before))
            if before.should_halt:
                return finalize_fallback_tool_result(name, args, synthetic_result(before))
        result = run_tool_with_retry(name, args, dispatch_tool)
        set_cached_result(name, args, result, session_key=session_key)
        if guardrails:
            after = guardrails.after_call(name, args, result)
            if after.should_halt:
                guardrails.set_halt_decision(after)
                try:
                    from butler.ops.retry_buckets import record_recovery_event

                    reason = str(getattr(after, "reason", "") or "tool_guardrail_halt")[:32]
                    record_recovery_event(reason or "tool_guardrail_halt")
                except Exception:
                    pass
                result = finalize_guardrail_halt_result(name, args, result, after)
            elif after.action == "warn":
                result = append_guidance(result, after)
        return result

    def _on_start(name: str, args: dict) -> None:
        nonlocal tools_started
        tools_started += 1
        if callbacks.on_tool_start:
            callbacks.on_tool_start(name, args)

    def _on_complete(name: str, result: str) -> None:
        try:
            from butler.ops.runtime_metrics import inc

            outcome = _tool_result_outcome(result)
            tool_label = str(name or "?")[:48]
            inc("tool_call", labels={"tool": tool_label, "outcome": outcome})
        except Exception:
            pass
        if callbacks.on_tool_complete:
            callbacks.on_tool_complete(name, result)

    def _precheck_tool(name: str, args: dict) -> str | None:
        if interrupt_check():
            return finalize_fallback_tool_result(
                name,
                args,
                {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
            )
        if guardrails and guardrails.halt_decision:
            return finalize_fallback_tool_result(
                name,
                args,
                synthetic_result(guardrails.halt_decision),
            )
        return None

    if config.enable_parallel_tools and len(response.tool_calls) > 1:
        pairs = execute_tools_parallel(
            response.tool_calls,
            lambda n, a: _dispatch_one(n, a),
            on_start=_on_start,
            on_complete=_on_complete,
            check_interrupt=interrupt_check,
            precheck_tool=_precheck_tool,
            prefetched=prefetched,
        )
    else:
        pairs = []
        batch_interrupted = False
        for tc in response.tool_calls:
            try:
                args = tc.args_dict()
            except Exception:
                args = {}
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
            _on_start(tc.name, args)
            result = _dispatch_one(tc.name, args, tool_call_id=str(tc.id or ""))
            _on_complete(tc.name, result)
            pairs.append((tc, result))
            if interrupt_check():
                batch_interrupted = True

    from butler.core.tool_result_storage import (
        maybe_spill_tool_result,
        normalize_empty_tool_result,
    )
    from butler.execution_context import get_current_session_key

    session_key = str(get_current_session_key() or "").strip()
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
    return ToolBatchStats(tools_started=tools_started)


def dispatch_tool_with_envelope(
    tool_dispatcher: Callable[[str, dict], str] | None,
    name: str,
    args: dict,
) -> str:
    """Dispatch through the configured handler and normalize failures."""
    if tool_dispatcher:
        try:
            result = tool_dispatcher(name, args)
            return finalize_unenveloped_failure_result(name, args, result)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return finalize_fallback_tool_result(
                name,
                args,
                {
                    "error": f"Tool execution failed: {exc}",
                    "code": "TOOL_DISPATCH_ERROR",
                },
            )
    return finalize_fallback_tool_result(
        name,
        args,
        {
            "error": f"No tool dispatcher configured, cannot run '{name}'",
            "code": "TOOL_DISPATCH_ERROR",
        },
    )


def finalize_fallback_tool_result(name: str, args: dict, result: Any) -> str:
    from butler.tools.registry import finalize_tool_result

    return finalize_tool_result(name, args, result)


def finalize_guardrail_halt_result(
    name: str,
    args: dict,
    result: str,
    decision: Any,
) -> str:
    from butler.tools.registry import finalize_tool_result, pop_last_tool_audit_for_tool

    pop_last_tool_audit_for_tool(name)
    payload = parse_tool_result_object(result)
    if payload is None:
        payload = {"error": result or decision.message}
    else:
        payload = dict(payload)
    for key in ("ok", "tool", "code"):
        payload.pop(key, None)
    payload["error"] = decision.message
    payload["guardrail"] = {
        "action": decision.action,
        "code": decision.code,
        "count": decision.count,
    }
    return finalize_tool_result(name, args, payload)


def finalize_unenveloped_failure_result(name: str, args: dict, result: str) -> str:
    payload = parse_tool_result_object(result)
    if not isinstance(payload, dict):
        return result
    if payload.get("ok") is False and payload.get("tool") and payload.get("code"):
        return result
    failed = (
        "error" in payload
        or payload.get("success") is False
        or (isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0)
    )
    if failed:
        payload = dict(payload)
        payload.setdefault("code", "TOOL_ERROR")
        return finalize_fallback_tool_result(name, args, payload)
    return result


def parse_tool_result_object(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None
