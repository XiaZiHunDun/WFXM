"""Compaction lifecycle hooks extracted from ``compress_messages`` (P1-C)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_compress_scheduled(
    *,
    session_key: str,
    messages_before: int,
    tokens_estimated: int,
) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_compact_scheduled

        record_compact_scheduled(
            session_key,
            source="context_compressor",
            messages_before=messages_before,
            tokens_estimated=tokens_estimated,
        )

    safe_best_effort(_run, label="context_compress.scheduled")


def record_compress_started(
    *,
    session_key: str,
    overflow_replay: bool,
) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_compact_started

        record_compact_started(
            session_key,
            source="context_compressor",
            trigger="reactive" if overflow_replay else "preemptive",
        )

    safe_best_effort(_run, label="context_compress.started")


__all__ = ["record_compact_scheduled", "record_compress_started"]
