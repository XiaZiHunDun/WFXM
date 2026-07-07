"""Reactive compact transcript and turn-tail helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def record_reactive_failed_safe(reason: str) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_compact_failed
        from butler.execution_context import get_audit_session_key

        record_compact_failed(
            get_audit_session_key(fallback="_global"),
            source="reactive",
            reason=reason,
        )

    safe_best_effort(_run, label="reactive_compact.failed_event", default=None)


def record_reactive_started_safe() -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_compact_started
        from butler.execution_context import get_audit_session_key

        record_compact_started(
            get_audit_session_key(fallback="_global"),
            source="reactive",
            trigger="overflow",
        )

    safe_best_effort(_run, label="reactive_compact.started_event", default=None)


def try_turn_tail_compact_loud(
    messages: list[dict[str, Any]],
    *,
    compress_fn: Callable[..., list[dict[str, Any]]],
    min_rounds_to_drop: int,
    max_rounds_to_drop: int,
    diagnostics: dict[str, Any] | None,
) -> tuple[bool, list[dict[str, Any]], str] | None:
    """Return None if turn-tail path not applicable; else (ok, msgs, reason)."""
    try:
        from butler.core.turn_compaction import (
            group_messages_into_turns,
            turn_compaction_enabled,
        )

        if not turn_compaction_enabled():
            return None
        system_msgs = [m for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        turns = group_messages_into_turns(rest)
        if len(turns) <= min_rounds_to_drop + 1:
            return False, messages, "too_few_turns"
        record_reactive_started_safe()
        keep_turns = turns[-max(1, len(turns) - max_rounds_to_drop) :]
        tail_start = keep_turns[0].start
        flattened = list(system_msgs[:1]) + rest[tail_start:]
        try:
            compressed = _compress_with_overflow_replay(compress_fn, flattened)
        except Exception as exc:
            logger.warning("Reactive compact failed: %s", exc)
            record_reactive_failed_safe("compress_error")
            return False, messages, "error"
        if len(compressed) >= len(messages):
            return False, messages, "exhausted"
        if diagnostics is not None:
            strategy = f"turns:{len(keep_turns)}"
            diagnostics["compaction_strategy"] = strategy
            diagnostics["reactive_compact_strategy"] = strategy
        return True, compressed, "ok"
    except Exception as exc:
        logger.debug("reactive turn-tail compact skipped: %s", exc)
        return None


def compress_rounds_loud(
    compress_fn: Callable[..., list[dict[str, Any]]],
    flattened: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], str]:
    try:
        compressed = _compress_with_overflow_replay(compress_fn, flattened)
    except Exception as exc:
        logger.warning("Reactive compact failed: %s", exc)
        record_reactive_failed_safe("compress_error")
        return False, flattened, "error"
    return True, compressed, "ok"


def _compress_with_overflow_replay(
    compress_fn: Callable[..., list[dict[str, Any]]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        return compress_fn(list(messages), overflow_replay=True)
    except TypeError:
        return compress_fn(list(messages))
