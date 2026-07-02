"""Single-tool dispatch path extracted from ``process_tool_calls`` (P1-C)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.tool_guardrails import (
    GuardrailDecision,
    ToolCallGuardrailController,
    append_guidance,
    synthetic_result,
)


def dispatch_one_tool(
    name: str,
    args: dict,
    *,
    tool_call_id: str = "",
    batch_guard: Any = None,
    prefetched: dict[str, str] | None = None,
    guardrails: ToolCallGuardrailController | None = None,
    dispatch_tool: Callable[[str, dict], str],
) -> str:
    """Run guardrails, cache, limits, and dispatch for one tool call."""
    from butler.core.tool_batch import (
        _capture_pre_edit_snapshot,
        _dev_engine_post_edit,
        _plan_mode_post_edit,
        finalize_fallback_tool_result,
        finalize_guardrail_halt_result,
    )
    from butler.core.tool_call_limits import get_tool_call_limiter
    from butler.core.tool_retry import run_tool_with_retry
    from butler.core.tool_result_cache import get_cached_result, set_cached_result
    from butler.execution_context import get_current_session_key

    def _two_phase_block() -> str | None:
        from butler.core.two_phase_confirm import two_phase_block_message

        block = two_phase_block_message(name, args, tool_call_id=tool_call_id)
        if not block:
            return None
        return finalize_fallback_tool_result(
            name,
            args,
            {
                "ok": False,
                "code": "TWO_PHASE_PENDING",
                "error": block,
                "tool": name,
            },
        )

    blocked = safe_best_effort(_two_phase_block, label="tool_dispatch.two_phase")
    if isinstance(blocked, str):
        return blocked

    def _boundary_block() -> str | None:
        from butler.permissions.tool_boundary_registry import validate_tool_boundary

        violation = validate_tool_boundary(name, args)
        if violation is None:
            return None
        return finalize_fallback_tool_result(name, args, violation.to_error_payload())

    boundary_blocked = safe_best_effort(_boundary_block, label="tool_dispatch.boundary")
    if isinstance(boundary_blocked, str):
        return boundary_blocked

    if batch_guard is not None and batch_guard.should_skip_stale_read(name, args):
        from butler.core.batch_sequence_guard import (
            STALE_PREFETCH_CODE,
            STALE_SKIP_CODE,
            stale_skip_result,
        )

        code = (
            STALE_PREFETCH_CODE
            if prefetched and tool_call_id and tool_call_id in prefetched
            else STALE_SKIP_CODE
        )
        payload = stale_skip_result(name, args, guard=batch_guard, code=code)
        return finalize_fallback_tool_result(name, args, payload)

    if prefetched and tool_call_id and tool_call_id in prefetched:
        result = prefetched[tool_call_id]
        if batch_guard is not None:
            batch_guard.note_tool_result(name, args, result)
        return result

    session_key = str(get_current_session_key() or "").strip()
    cached = get_cached_result(name, args, session_key=session_key)
    if cached is not None:
        result = cached
        pending_warn = None
        if guardrails:
            before = guardrails.before_call(name, args)
            if before.action == "warn" and before.code == "doom_loop_soft_nudge":
                pending_warn = before
            if before.should_halt:
                return finalize_fallback_tool_result(name, args, synthetic_result(before))
            after = guardrails.after_call(name, args, result)
            if after.should_halt:
                guardrails.set_halt_decision(after)
                return finalize_guardrail_halt_result(name, args, result, after)
            if after.action == "warn":
                result = append_guidance(result, after)
            elif pending_warn is not None:
                result = append_guidance(result, pending_warn)
        return result

    limited = get_tool_call_limiter().before_call(name)
    if limited:
        return finalize_fallback_tool_result(name, args, limited)

    pending_warn = None
    if guardrails:
        before = guardrails.before_call(name, args)
        if before.action == "warn" and before.code == "doom_loop_soft_nudge":
            pending_warn = before
        if before.action == "ask" and before.code == "doom_loop":
            from butler.core.tool_dispatch_doom import handle_doom_loop_ask

            doom_result = handle_doom_loop_ask(
                before, name, args, session_key=session_key,
            )
            if doom_result is not None:
                return doom_result
        if before.should_halt:
            return finalize_fallback_tool_result(name, args, synthetic_result(before))

    _capture_pre_edit_snapshot(name, args)
    result = run_tool_with_retry(name, args, dispatch_tool)

    def _emit_tool_event() -> None:
        from butler.core.structured_events import args_digest, emit_tool_action
        from butler.execution_context import get_current_session_key

        outcome = "error" if '"error"' in str(result)[:200].lower() else "ok"
        emit_tool_action(
            tool_name=name,
            args_digest_value=args_digest(args),
            outcome=outcome,
            session_key=str(get_current_session_key() or ""),
        )

    safe_best_effort(_emit_tool_event, label="tool_dispatch.structured_event")

    def _apply_error_policy() -> None:
        nonlocal result
        from butler.core.tool_error_policy import (
            apply_tool_error_policy,
            should_halt_loop_on_tool_error,
        )

        result = apply_tool_error_policy(result, tool_name=name)
        if should_halt_loop_on_tool_error(result, tool_name=name) and guardrails:
            guardrails.set_halt_decision(
                GuardrailDecision(
                    action="block",
                    code="tool_error_stop",
                    message="工具错误策略: stop（勿重复同调用）",
                    tool_name=name,
                )
            )

    safe_best_effort(_apply_error_policy, label="tool_dispatch.error_policy")

    mutation_failed = False
    from butler.core.tool_dispatch_ops import annotate_mutation_not_landed_safe

    result, mutation_failed = annotate_mutation_not_landed_safe(name, result)

    set_cached_result(name, args, result, session_key=session_key)

    if guardrails:
        after = guardrails.after_call(
            name, args, result, failed=True if mutation_failed else None,
        )
        if after.should_halt:
            guardrails.set_halt_decision(after)

            def _record_recovery() -> None:
                from butler.ops.retry_buckets import record_recovery_event

                reason = str(getattr(after, "reason", "") or "tool_guardrail_halt")[:32]
                record_recovery_event(reason or "tool_guardrail_halt")

            safe_best_effort(_record_recovery, label="tool_dispatch.recovery_event")
            result = finalize_guardrail_halt_result(name, args, result, after)
        elif after.action == "warn":
            result = append_guidance(result, after)
        elif pending_warn is not None:
            result = append_guidance(result, pending_warn)

    if batch_guard is not None:
        batch_guard.note_tool_result(name, args, result)
    _dev_engine_post_edit(name, args, result)
    _plan_mode_post_edit(name, args, result)
    return result


__all__ = ["dispatch_one_tool"]
