"""Explicit compaction turn (OpenCode CompactionPart / loop task subset)."""

from __future__ import annotations

from typing import Any, Callable

from butler.env_parse import env_truthy, int_env


def explicit_compaction_turn_enabled() -> bool:
    return bool(env_truthy("BUTLER_COMPACTION_EXPLICIT_TURN", default=True))


def should_run_compaction_turn(
    messages: list[dict[str, Any]],
    *,
    max_context_tokens: int,
    estimate_tokens: Callable[[list[dict[str, Any]]], int],
    diagnostics: dict[str, Any] | None,
    iteration: int,
    max_output_tokens: int | None = None,
) -> bool:
    """True when this loop iteration should run compression before LLM."""
    if not explicit_compaction_turn_enabled():
        return False
    from butler.core.context_budget import get_auto_compact_threshold, is_auto_compact_enabled

    if not is_auto_compact_enabled():
        return False
    diag = diagnostics if isinstance(diagnostics, dict) else {}
    if int(diag.get("compaction_turn_iteration") or 0) == iteration:
        return False
    estimated = max(0, int(estimate_tokens(messages)))
    threshold = get_auto_compact_threshold(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    return estimated >= int(threshold)


def run_compaction_turn(
    messages: list[dict[str, Any]],
    *,
    compress: Callable[..., list[dict[str, Any]]],
    diagnostics: dict[str, Any] | None = None,
    iteration: int = 0,
    session_key: str = "",
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Run pre/post compact hooks and force compress. Returns (did_compact, messages).
    """
    from butler.core.compaction_task_ops import (
        audit_session_key_safe,
        emit_compaction_completed_safe,
        estimate_tokens_safe,
        invoke_post_compact_hook_safe,
        invoke_pre_compact_hook_safe,
        record_compaction_turn_event_safe,
        run_post_compact_hooks_safe,
        run_pre_compact_hooks_safe,
    )

    diag = diagnostics if isinstance(diagnostics, dict) else {}
    before_est = estimate_tokens_safe(messages)
    if run_pre_compact_hooks_safe(
        before_est=before_est,
        message_count=len(messages),
        iteration=iteration,
        session_key=session_key,
        diag=diag,
    ):
        return False, messages

    invoke_pre_compact_hook_safe(
        messages=messages,
        before_est=before_est,
        iteration=iteration,
        session_key=session_key,
    )
    from butler.core.compaction_phase import (
        record_compaction_diagnostics,
        resolve_compaction_context,
    )

    phase, injection, reason = resolve_compaction_context(
        iteration=iteration,
        explicit_turn=True,
    )
    record_compaction_diagnostics(diag, phase=phase, reason=reason, injection=injection)
    diag["compaction_explicit_turn"] = True
    diag["compaction_turn_iteration"] = iteration

    compressed = compress(
        list(messages),
        threshold_ratio=0.0,
        min_messages_to_compress=int_env("BUTLER_COMPACTION_TURN_MIN_MSGS", 8, min=6),
        diagnostics=diag,
    )
    after_est = estimate_tokens_safe(compressed)
    did = len(compressed) < len(messages) or after_est < before_est
    if not did:
        return False, messages

    thread_id = audit_session_key_safe(session_key)
    emit_compaction_completed_safe(
        thread_id=thread_id,
        before_est=before_est,
        after_est=after_est,
        messages_before=len(messages),
        messages_after=len(compressed),
        remote=bool(diag.get("compaction_remote")),
    )
    run_post_compact_hooks_safe(
        before_est=before_est,
        after_est=after_est,
        messages_before=len(messages),
        messages_after=len(compressed),
        iteration=iteration,
        session_key=session_key,
        diag=diag,
    )
    invoke_post_compact_hook_safe(
        compressed=compressed,
        before_est=before_est,
        after_est=after_est,
        iteration=iteration,
        session_key=session_key,
    )
    sk = audit_session_key_safe(session_key)
    record_compaction_turn_event_safe(
        session_key=sk,
        iteration=iteration,
        messages_before=len(messages),
        messages_after=len(compressed),
        before_est=before_est,
        after_est=after_est,
    )
    diag["compaction_explicit_turn"] = True
    diag["compaction_turn_iteration"] = iteration
    diag["compaction_turn_messages_before"] = len(messages)
    diag["compaction_turn_messages_after"] = len(compressed)
    return True, compressed
