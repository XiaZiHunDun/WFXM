"""Reactive context compaction on API 413 / payload errors (CC reactiveCompact subset)."""

from __future__ import annotations

from typing import Any, Callable, cast

from butler.core.reactive_compact_ops import (
    compress_rounds_loud,
    record_reactive_started_safe,
    try_turn_tail_compact_loud,
)


def group_messages_by_api_round(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split history at assistant messages with new ids (CC grouping.ts)."""
    if not messages:
        return []
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
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
    messages: list[dict[str, Any]],
    *,
    compress_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    min_rounds_to_drop: int = 1,
    max_rounds_to_drop: int = 3,
    use_turn_tail: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[bool, list[dict[str, Any]], str]:
    """
    Drop oldest API rounds then compress. Returns (ok, new_messages, reason).
    """
    if use_turn_tail:
        turn_result = try_turn_tail_compact_loud(
            messages,
            compress_fn=compress_fn,
            min_rounds_to_drop=min_rounds_to_drop,
            max_rounds_to_drop=max_rounds_to_drop,
            diagnostics=diagnostics,
        )
        if turn_result is not None:
            return cast(tuple[bool, list[dict[str, Any]], str], turn_result)

    rounds = group_messages_by_api_round(messages)
    if len(rounds) <= min_rounds_to_drop + 1:
        return False, messages, "too_few_groups"

    record_reactive_started_safe()
    system_msgs = [m for m in messages if m.get("role") == "system"]
    tail_rounds = rounds[-max(1, len(rounds) - max_rounds_to_drop) :]
    flattened: list[dict[str, Any]] = []
    for r in tail_rounds:
        flattened.extend(r)

    if system_msgs and (not flattened or flattened[0].get("role") != "system"):
        flattened = list(system_msgs[:1]) + flattened

    ok, compressed, reason = compress_rounds_loud(compress_fn, flattened)
    if not ok:
        return False, messages, reason
    if len(compressed) >= len(messages):
        return False, messages, "exhausted"
    return True, compressed, "ok"


def apply_reactive_compact_to_messages(
    messages: list[dict[str, Any]],
    *,
    compress_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
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
