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


def record_compress_completed(
    *,
    session_key: str,
    summary_len: int,
    messages_before: int,
    messages_after: int,
    tokens_before: int,
    tokens_after: int,
    summary_chars: int,
    remote: bool,
) -> None:
    def _transcript() -> None:
        from butler.core.session_transcript import (
            record_compact_boundary,
            record_compact_done,
        )

        record_compact_boundary(session_key, summary_len)
        record_compact_done(
            session_key,
            source="context_compressor",
            messages_after=messages_after,
            tokens_after=tokens_after,
            summary_chars=summary_chars,
        )

    safe_best_effort(_transcript, label="context_compress.done")

    def _emit() -> None:
        from butler.core.events_sink import emit_context_compaction

        emit_context_compaction(
            phase="completed",
            thread_id=session_key,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=messages_before,
            messages_after=messages_after,
            source="context_compressor",
            remote=remote,
        )

    safe_best_effort(_emit, label="context_compress.emit")


def record_overflow_replay(*, session_key: str, replay_user: dict) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_overflow_replay

        content = str(replay_user.get("content") or "")
        record_overflow_replay(
            session_key,
            source="context_compressor",
            content_preview=content,
            replayed_chars=len(content),
        )

    safe_best_effort(_run, label="context_compress.overflow_replay")


def auxiliary_summarize_middle(prompt: str) -> str | None:
    def _run() -> str:
        from butler.transport.auxiliary_client import auxiliary_complete

        return auxiliary_complete(
            prompt,
            task="compression",
            system="You compress conversation history into structured handoff notes.",
        )

    return safe_best_effort(
        _run,
        label="context_compressor.auxiliary_summarize",
        default=None,
    )


def split_for_compaction_turn(
    pruned: list[dict],
    *,
    max_tokens: int,
    head_count: int,
    max_tail_messages: int,
    min_tail_messages: int,
    max_output_tokens: int | None,
    diagnostics: dict | None,
    estimate_fn,
    legacy_split_fn,
    write_diagnostics_fn,
) -> tuple[list[dict], list[dict], list[dict]] | None:
    def _run() -> tuple[list[dict], list[dict], list[dict]]:
        from butler.core.turn_compaction import split_head_tail_turns, turn_compaction_enabled

        if not turn_compaction_enabled():
            raise RuntimeError("turn compaction disabled")
        system, middle, head_tail = split_head_tail_turns(
            pruned,
            max_context_tokens=max_tokens,
            max_output_tokens=max_output_tokens,
            head_count=head_count,
            min_tail_messages=min_tail_messages,
            estimate_fn=estimate_fn,
            diagnostics=diagnostics,
        )
        if not middle:
            legacy_system, legacy_middle, legacy_head_tail = legacy_split_fn(
                pruned,
                head_count=head_count,
                max_tail_messages=max_tail_messages,
                min_tail_messages=min_tail_messages,
            )
            if legacy_middle:
                system, middle, head_tail = (
                    legacy_system,
                    legacy_middle,
                    legacy_head_tail,
                )
                if isinstance(diagnostics, dict):
                    diagnostics["compaction_turn_fallback"] = "legacy_split"
        return system, middle, head_tail

    return safe_best_effort(
        _run,
        label="context_compress.turn_split",
        default=None,
    )


def legacy_compaction_split_fallback(
    pruned: list[dict],
    *,
    diagnostics: dict | None,
    head_count: int,
    max_tail_messages: int,
    min_tail_messages: int,
    legacy_split_fn,
    write_diagnostics_fn,
) -> tuple[list[dict], list[dict], list[dict]]:
    if isinstance(diagnostics, dict):
        write_diagnostics_fn(
            diagnostics,
            strategy="legacy_split",
            tail_turns_kept=0,
            split_turn_applied=False,
            preserved_recent_budget=0,
            tail_token_count=0,
            tail_start_index=0,
        )
        diagnostics["compaction_turn_fallback"] = "legacy_split"
    return legacy_split_fn(
        pruned,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
    )


__all__ = [
    "auxiliary_summarize_middle",
    "legacy_compaction_split_fallback",
    "record_compress_completed",
    "record_compress_scheduled",
    "record_compress_started",
    "record_overflow_replay",
    "split_for_compaction_turn",
]
