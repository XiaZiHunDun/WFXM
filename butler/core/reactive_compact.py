"""Reactive context compaction on API 413 / payload errors (CC reactiveCompact subset)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def group_messages_by_api_round(messages: list[dict]) -> list[list[dict]]:
    """Split history at assistant messages with new ids (CC grouping.ts)."""
    if not messages:
        return []
    rounds: list[list[dict]] = []
    current: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and current:
            rounds.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        rounds.append(current)
    return rounds


def try_reactive_compact(
    messages: list[dict],
    *,
    compress_fn: Callable[[list[dict]], list[dict]],
    min_rounds_to_drop: int = 1,
    max_rounds_to_drop: int = 3,
) -> tuple[bool, list[dict], str]:
    """
    Drop oldest API rounds then compress. Returns (ok, new_messages, reason).
    """
    rounds = group_messages_by_api_round(messages)
    if len(rounds) <= min_rounds_to_drop + 1:
        return False, messages, "too_few_groups"

    system_msgs = [m for m in messages if m.get("role") == "system"]
    tail_rounds = rounds[-max(1, len(rounds) - max_rounds_to_drop) :]
    flattened: list[dict] = []
    for r in tail_rounds:
        flattened.extend(r)

    if system_msgs and (not flattened or flattened[0].get("role") != "system"):
        flattened = list(system_msgs[:1]) + flattened

    try:
        compressed = compress_fn(flattened)
    except Exception as exc:
        logger.warning("Reactive compact failed: %s", exc)
        return False, messages, "error"

    if len(compressed) >= len(messages):
        return False, messages, "exhausted"
    return True, compressed, "ok"


def apply_reactive_compact_to_messages(
    messages: list[dict],
    *,
    compress_fn: Callable[[list[dict]], list[dict]],
    diagnostics: dict[str, Any] | None = None,
) -> bool:
    ok, new_msgs, reason = try_reactive_compact(messages, compress_fn=compress_fn)
    if diagnostics is not None:
        diagnostics["reactive_compact_applied"] = ok
        diagnostics["reactive_compact_reason"] = reason
        if ok:
            diagnostics["reactive_context_compact"] = True
    if ok:
        messages[:] = new_msgs
    return ok
