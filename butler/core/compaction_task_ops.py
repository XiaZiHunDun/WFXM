"""Best-effort helpers for explicit compaction turns (P0-A)."""

from __future__ import annotations

from typing import Any, Callable

from butler.core.best_effort import safe_best_effort
from butler.core.context_compressor import _estimate_tokens
from butler.core.hook_context_adapter import adapt_hook_context_lines, apply_hook_context_to_diagnostics, to_hook_context_view
from butler.hooks.runner import run_pre_compact_hooks
from butler.core.events_sink import invoke_hook
from butler.execution_context import get_audit_session_key
from butler.core.events_sink import emit_context_compaction
from butler.core.compaction_context_adapter import adapt_hook_contexts, apply_compaction_view_to_diagnostics, to_loop_compaction_view
from butler.core.hook_context_adapter import apply_hook_context_to_diagnostics, to_hook_context_view
from butler.hooks.runner import run_post_compact_hooks
from butler.core.session_transcript import record_generic_event


def estimate_tokens_safe(messages: list[dict]) -> int:
    def _run() -> int:

        return int(_estimate_tokens(messages))

    result = safe_best_effort(_run, label="compaction_task.estimate_tokens", default=0)
    return int(result) if isinstance(result, int) else 0


def run_pre_compact_hooks_safe(
    *,
    before_est: int,
    message_count: int,
    iteration: int,
    session_key: str,
    diag: dict[str, Any],
) -> bool:
    """Return True if blocked."""

    def _run() -> bool:

        pre = run_pre_compact_hooks(
            estimated_tokens=before_est,
            message_count=message_count,
            iteration=iteration,
            session_key=session_key,
        )
        if pre.blocked:
            diag["compaction_turn_blocked"] = pre.blocked[:500]
            return True
        if pre.contexts:
            adapted = adapt_hook_context_lines(pre.contexts, source="pre_compact_hook")
            if adapted:
                diag["compaction_pre_hook_context"] = adapted
                view = to_hook_context_view(adapted, source="pre_compact_merged")
                apply_hook_context_to_diagnostics(view, diag)
        return False

    result = safe_best_effort(_run, label="compaction_task.pre_hooks", default=False)
    return bool(result)


def invoke_pre_compact_hook_safe(
    *,
    messages: list[dict],
    before_est: int,
    iteration: int,
    session_key: str,
) -> None:
    def _run() -> None:

        invoke_hook(
            "pre_compact",
            messages=messages,
            estimated_tokens=before_est,
            iteration=iteration,
            session_key=session_key,
        )

    safe_best_effort(_run, label="compaction_task.pre_compact_hook", default=None)


def audit_session_key_safe(session_key: str) -> str:
    if str(session_key or "").strip():
        return str(session_key).strip()

    def _run() -> str:

        return str(get_audit_session_key(fallback="_global"))

    result = safe_best_effort(_run, label="compaction_task.audit_session_key", default="_global")
    return result if isinstance(result, str) and result else "_global"


def emit_compaction_completed_safe(
    *,
    thread_id: str,
    before_est: int,
    after_est: int,
    messages_before: int,
    messages_after: int,
    remote: bool,
) -> None:
    def _run() -> None:

        emit_context_compaction(
            phase="completed",
            thread_id=thread_id,
            tokens_before=before_est,
            tokens_after=after_est,
            messages_before=messages_before,
            messages_after=messages_after,
            source="compaction_turn",
            remote=remote,
        )

    safe_best_effort(_run, label="compaction_task.emit_compaction", default=None)


def run_post_compact_hooks_safe(
    *,
    before_est: int,
    after_est: int,
    messages_before: int,
    messages_after: int,
    iteration: int,
    session_key: str,
    diag: dict[str, Any],
) -> None:
    def _run() -> None:

        hook_contexts = run_post_compact_hooks(
            estimated_tokens_before=before_est,
            estimated_tokens_after=after_est,
            message_count_before=messages_before,
            message_count_after=messages_after,
            iteration=iteration,
            session_key=session_key,
        )
        if not hook_contexts:
            return
        adapted = adapt_hook_contexts(hook_contexts, source="post_compact_hook")
        if not adapted:
            return
        diag["compaction_hook_context"] = adapted
        hook_view = to_hook_context_view(adapted, source="post_compact_merged")
        apply_hook_context_to_diagnostics(hook_view, diag)
        view = to_loop_compaction_view(adapted, source="post_compact_merged")
        apply_compaction_view_to_diagnostics(view, diag)

    safe_best_effort(_run, label="compaction_task.post_hooks", default=None)


def invoke_post_compact_hook_safe(
    *,
    compressed: list[dict],
    before_est: int,
    after_est: int,
    iteration: int,
    session_key: str,
) -> None:
    def _run() -> None:

        invoke_hook(
            "post_compact",
            messages=compressed,
            estimated_tokens_before=before_est,
            estimated_tokens_after=after_est,
            iteration=iteration,
            session_key=session_key,
        )

    safe_best_effort(_run, label="compaction_task.post_compact_hook", default=None)


def record_compaction_turn_event_safe(
    *,
    session_key: str,
    iteration: int,
    messages_before: int,
    messages_after: int,
    before_est: int,
    after_est: int,
) -> None:
    def _run() -> None:

        record_generic_event(
            session_key,
            "compaction_turn",
            {
                "iteration": iteration,
                "messages_before": messages_before,
                "messages_after": messages_after,
                "tokens_before": before_est,
                "tokens_after": after_est,
            },
        )

    safe_best_effort(_run, label="compaction_task.transcript_event", default=None)
