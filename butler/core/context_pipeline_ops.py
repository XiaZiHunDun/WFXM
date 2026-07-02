"""Best-effort context pipeline step helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import (
    record_best_effort_skip,
    safe_best_effort,
)

logger = logging.getLogger(__name__)


def audit_session_key_safe(*, fallback: str = "") -> str:
    def _run() -> str:
        from butler.execution_context import get_audit_session_key

        return get_audit_session_key(fallback=fallback)

    result = safe_best_effort(
        _run,
        label="context_pipeline.audit_session_key",
        default=fallback,
    )
    return str(result or fallback)


def capture_compaction_checkpoint_safe(
    *,
    session_key: str,
    open_todos: int,
    compression_summary: str,
    max_iterations: int,
    attached_loop: Any,
) -> None:
    def _run() -> None:
        from butler.core.compaction_checkpoint import capture_checkpoint, capture_from_loop

        capture_checkpoint(
            session_key,
            open_todos=open_todos,
            compression_summary=compression_summary,
            max_iterations=max_iterations,
        )
        if attached_loop is not None:
            capture_from_loop(
                session_key,
                loop=attached_loop,
                compression_summary=compression_summary,
            )

    safe_best_effort(_run, label="context_pipeline.compaction_checkpoint", default=None)


def resolve_compaction_injection_safe(
    diagnostics: dict[str, Any],
) -> Any | None:
    def _run() -> Any:
        from butler.core.compaction_phase import (
            record_compaction_diagnostics,
            resolve_compaction_context,
        )

        iteration = int(diagnostics.get("compaction_turn_iteration") or 0)
        reactive = bool(diagnostics.get("reactive_context_compact"))
        phase, injection, reason = resolve_compaction_context(
            iteration=max(1, iteration),
            explicit_turn=bool(diagnostics.get("compaction_explicit_turn")),
            reactive=reactive,
        )
        record_compaction_diagnostics(
            diagnostics, phase=phase, reason=reason, injection=injection
        )
        return injection

    return safe_best_effort(
        _run,
        label="context_pipeline.compaction_injection",
        default=None,
    )


def should_skip_post_compact_reanchor_safe(diagnostics: dict[str, Any]) -> bool:
    def _run() -> bool:
        from butler.core.compaction_phase import should_skip_post_compact_reanchor

        return bool(should_skip_post_compact_reanchor(diagnostics))

    result = safe_best_effort(
        _run,
        label="context_pipeline.skip_reanchor",
        default=False,
    )
    return bool(result)


def restore_compaction_checkpoint_safe(
    session_key: str,
    diagnostics: dict[str, Any],
) -> None:
    def _run() -> None:
        from butler.core.compaction_checkpoint import restore_into_diagnostics

        restore_into_diagnostics(session_key, diagnostics)

    safe_best_effort(_run, label="context_pipeline.checkpoint_restore", default=None)


def apply_unified_tool_masking_safe(messages: list[dict]) -> list[dict]:
    def _run() -> list[dict]:
        from butler.core.tool_output_masking import apply_unified_tool_masking

        return apply_unified_tool_masking(list(messages))

    result = safe_best_effort(
        _run,
        label="context_pipeline.tool_masking",
        default=None,
    )
    if isinstance(result, list):
        return result
    return list(messages)


def compress_inline_tool_messages_safe(messages: list[dict]) -> list[dict]:
    def _run() -> list[dict]:
        from butler.core.inline_tool_compress import compress_inline_tool_messages

        return compress_inline_tool_messages(list(messages))

    result = safe_best_effort(
        _run,
        label="context_pipeline.inline_tool_compress",
        default=None,
    )
    if isinstance(result, list):
        return result
    return list(messages)


def apply_model_transforms_safe(
    messages: list[dict],
    *,
    client: Any,
    diagnostics: dict[str, Any] | None,
) -> list[dict]:
    def _run() -> list[dict]:
        from butler.core.context_transform_registry import apply_model_transforms

        if client is None:
            return list(messages)
        provider = str(getattr(client, "provider_name", "") or "")
        model = str(getattr(client, "model", "") or "")
        return apply_model_transforms(
            list(messages),
            provider=provider,
            model=model,
            diagnostics=diagnostics,
        )

    result = safe_best_effort(
        _run,
        label="context_pipeline.model_transform",
        default=None,
    )
    if isinstance(result, list):
        return result
    return list(messages)


def apply_preemptive_compact_safe(
    messages: list[dict],
    *,
    max_context_tokens: int,
    estimate_tokens: Any,
    compress: Any,
    diagnostics: dict[str, Any] | None,
) -> list[dict]:
    try:
        from butler.core.preemptive_compact import (
            ContextPrecheckOverflow,
            apply_preemptive_pipeline,
            preemptive_compact_enabled,
        )

        if not preemptive_compact_enabled():
            return list(messages)
        out, decision = apply_preemptive_pipeline(
            list(messages),
            max_context_tokens=max_context_tokens,
            estimate_tokens=estimate_tokens,
            compress=compress,
            diagnostics=diagnostics,
        )
        if decision.route == "overflow_fail":
            raise ContextPrecheckOverflow(
                decision.message,
                estimated=decision.estimated_tokens,
                threshold=decision.threshold_tokens,
            )
        return out
    except Exception as exc:
        from butler.core.preemptive_compact import ContextPrecheckOverflow

        if isinstance(exc, ContextPrecheckOverflow):
            raise
        logger.debug("Preemptive compact skipped: %s", exc)
        record_best_effort_skip("context_pipeline.preemptive_compact", exc)
        return list(messages)


def annotate_api_message_boundary_safe(
    messages: list[dict],
    diagnostics: dict[str, Any] | None,
) -> None:
    def _run() -> None:
        from butler.core.message_context_adapter import annotate_api_message_boundary

        annotate_api_message_boundary(messages, diagnostics, source="prepare_messages")

    safe_best_effort(_run, label="context_pipeline.api_message_acl", default=None)
