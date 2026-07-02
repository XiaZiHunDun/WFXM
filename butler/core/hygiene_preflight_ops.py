"""Hygiene preflight transcript and status helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def record_hygiene_compact_scheduled(
    *,
    messages_before: int,
    tokens_estimated: int,
) -> None:
    def _run() -> None:
        from butler.execution_context import get_audit_session_key
        from butler.core.session_transcript import (
            record_compact_scheduled,
            record_compact_started,
        )

        sk = get_audit_session_key(fallback="_global")
        record_compact_scheduled(
            sk,
            source="hygiene",
            messages_before=messages_before,
            tokens_estimated=tokens_estimated,
        )
        record_compact_started(sk, source="hygiene", trigger="preflight")

    safe_best_effort(_run, label="hygiene_preflight.compact_scheduled", default=None)


def record_hygiene_compact_failed_event() -> None:
    def _run() -> None:
        from butler.execution_context import get_audit_session_key
        from butler.core.session_transcript import record_compact_failed

        record_compact_failed(
            get_audit_session_key(fallback="_global"),
            source="hygiene",
            reason="compress_error",
        )

    safe_best_effort(_run, label="hygiene_preflight.compact_failed_event", default=None)


def derive_compaction_status_safe(diagnostics: dict[str, Any]) -> str | None:
    def _run() -> str:
        from butler.core.compaction_status import derive_compaction_status

        return str(derive_compaction_status(diagnostics))

    result = safe_best_effort(
        _run,
        label="hygiene_preflight.compaction_status",
        default=None,
    )
    return result if isinstance(result, str) else None


def record_hygiene_compact_done(
    *,
    messages_after: int,
    tokens_after: int,
) -> None:
    def _run() -> None:
        from butler.execution_context import get_audit_session_key
        from butler.core.session_transcript import record_compact_done

        record_compact_done(
            get_audit_session_key(fallback="_global"),
            source="hygiene",
            messages_after=messages_after,
            tokens_after=tokens_after,
        )

    safe_best_effort(_run, label="hygiene_preflight.compact_done", default=None)
