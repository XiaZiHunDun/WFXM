"""Explicit compaction turn (OpenCode CompactionPart / loop task subset)."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from butler.env_parse import env_truthy, int_env

logger = logging.getLogger(__name__)


def explicit_compaction_turn_enabled() -> bool:
    return env_truthy("BUTLER_COMPACTION_EXPLICIT_TURN", default=True)


def should_run_compaction_turn(
    messages: list[dict],
    *,
    max_context_tokens: int,
    estimate_tokens: Callable[[list[dict]], int],
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
    return estimated >= threshold


def run_compaction_turn(
    messages: list[dict],
    *,
    compress: Callable[..., list[dict]],
    diagnostics: dict[str, Any] | None = None,
    iteration: int = 0,
    session_key: str = "",
) -> tuple[bool, list[dict]]:
    """
    Run pre/post compact hooks and force compress. Returns (did_compact, messages).
    """
    diag = diagnostics if isinstance(diagnostics, dict) else {}
    before_est = 0
    try:
        from butler.core.context_compressor import _estimate_tokens

        before_est = _estimate_tokens(messages)
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
    try:
        from butler.hooks.runner import run_post_compact_hooks, run_pre_compact_hooks

        block = run_pre_compact_hooks(
            estimated_tokens=before_est,
            message_count=len(messages),
            iteration=iteration,
            session_key=session_key,
        )
        if block:
            diag["compaction_turn_blocked"] = block[:500]
            return False, messages
    except Exception as exc:
        logger.debug("pre_compact hooks skipped: %s", exc)

    try:
        from butler.core.events_sink import invoke_hook

        invoke_hook(
            "pre_compact",
            messages=messages,
            estimated_tokens=before_est,
            iteration=iteration,
            session_key=session_key,
        )
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
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
    after_est = before_est
    try:
        from butler.core.context_compressor import _estimate_tokens

        after_est = _estimate_tokens(compressed)
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
    did = len(compressed) < len(messages) or after_est < before_est
    if not did:
        return False, messages

    thread_id = str(session_key or "").strip()
    if not thread_id:
        try:
            from butler.execution_context import get_audit_session_key

            thread_id = get_audit_session_key(fallback="_global")
        except Exception:
            thread_id = "_global"
    try:
        from butler.core.events_sink import emit_context_compaction

        remote = bool(diag.get("compaction_remote"))
        emit_context_compaction(
            phase="completed",
            thread_id=thread_id,
            tokens_before=before_est,
            tokens_after=after_est,
            messages_before=len(messages),
            messages_after=len(compressed),
            source="compaction_turn",
            remote=remote,
        )
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
    try:
        from butler.hooks.runner import run_post_compact_hooks

        run_post_compact_hooks(
            estimated_tokens_before=before_est,
            estimated_tokens_after=after_est,
            message_count_before=len(messages),
            message_count_after=len(compressed),
            iteration=iteration,
            session_key=session_key,
        )
    except Exception as exc:
        logger.debug("post_compact hooks skipped: %s", exc)

    try:
        from butler.core.events_sink import invoke_hook

        invoke_hook(
            "post_compact",
            messages=compressed,
            estimated_tokens_before=before_est,
            estimated_tokens_after=after_est,
            iteration=iteration,
            session_key=session_key,
        )
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
    sk = session_key
    if not sk:
        try:
            from butler.execution_context import get_audit_session_key

            sk = get_audit_session_key(fallback="_global")
        except Exception:
            sk = "_global"
    try:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            sk,
            "compaction_turn",
            {
                "iteration": iteration,
                "messages_before": len(messages),
                "messages_after": len(compressed),
                "tokens_before": before_est,
                "tokens_after": after_est,
            },
        )
    except Exception as exc:
        logger.debug("run compaction turn skipped: %s", exc)
    diag["compaction_explicit_turn"] = True
    diag["compaction_turn_iteration"] = iteration
    diag["compaction_turn_messages_before"] = len(messages)
    diag["compaction_turn_messages_after"] = len(compressed)
    return True, compressed
