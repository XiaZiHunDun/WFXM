"""Turn-based context tail selection (OpenCode compaction.ts subset)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from butler.env_parse import env_truthy

# OpenCode compaction.ts defaults
_DEFAULT_TAIL_TURNS = 2
_MIN_PRESERVE_RECENT = 2_000
_MAX_PRESERVE_RECENT = 8_000
_DEFAULT_PRESERVE_RATIO = 0.25

_SUMMARY_MARKERS = (
    "[CONTEXT COMPACTION",
    "[POST-COMPACT ANCHORS",
)


def _strategy_label(
    tail_turns_kept: int,
    split_applied: bool,
    middle_present: bool,
) -> str:
    """Generate human-readable compaction strategy tag for /诊断 output."""
    if not middle_present:
        return "no_op"
    base = f"turns:{tail_turns_kept}"
    return f"{base}+split" if split_applied else base


@dataclass(frozen=True)
class TurnSpan:
    """Half-open index range [start, end) in a non-system message list."""

    start: int
    end: int


def turn_compaction_enabled() -> bool:
    return env_truthy("BUTLER_COMPACTION_USE_TURNS", default=True)


def tail_turns_limit() -> int:
    try:
        return max(0, int(os.getenv("BUTLER_COMPACTION_TAIL_TURNS", str(_DEFAULT_TAIL_TURNS))))
    except ValueError:
        return _DEFAULT_TAIL_TURNS


def split_turn_enabled() -> bool:
    return env_truthy("BUTLER_COMPACTION_SPLIT_TURN", default=True)


def preserve_recent_token_budget(
    max_context_tokens: int,
    *,
    max_output_tokens: int | None = None,
) -> int:
    """Tokens to keep for recent turns (OpenCode preserveRecentBudget)."""
    from butler.core.context_budget import get_effective_context_window

    usable = get_effective_context_window(max_context_tokens, max_output_tokens=max_output_tokens)
    try:
        fixed = int(os.getenv("BUTLER_COMPACTION_PRESERVE_RECENT_TOKENS", "").strip() or 0)
    except ValueError:
        fixed = 0
    if fixed > 0:
        return max(_MIN_PRESERVE_RECENT, min(_MAX_PRESERVE_RECENT, fixed))
    try:
        ratio = float(os.getenv("BUTLER_COMPACTION_PRESERVE_RECENT_RATIO", str(_DEFAULT_PRESERVE_RATIO)))
    except ValueError:
        ratio = _DEFAULT_PRESERVE_RATIO
    scaled = int(usable * ratio)
    return min(_MAX_PRESERVE_RECENT, max(_MIN_PRESERVE_RECENT, scaled))


def is_compaction_summary_message(msg: dict[str, Any]) -> bool:
    if msg.get("role") != "user":
        return False
    text = str(msg.get("content") or "")
    return any(m in text for m in _SUMMARY_MARKERS)


def group_messages_into_turns(rest: list[dict]) -> list[TurnSpan]:
    """Each turn starts at a non-summary user message."""
    turns: list[TurnSpan] = []
    i = 0
    n = len(rest)
    while i < n:
        msg = rest[i]
        if msg.get("role") != "user" or is_compaction_summary_message(msg):
            i += 1
            continue
        start = i
        i += 1
        while i < n and rest[i].get("role") != "user":
            i += 1
        turns.append(TurnSpan(start=start, end=i))
    return turns


def _estimate_messages_tokens(
    messages: list[dict],
    estimate_fn: Callable[[list[dict]], int] | None = None,
) -> int:
    if estimate_fn is not None:
        return max(0, int(estimate_fn(messages)))
    from butler.core.context_compressor import _estimate_tokens

    return _estimate_tokens(messages)


def _split_turn_suffix(
    rest: list[dict],
    turn: TurnSpan,
    *,
    budget: int,
    estimate_fn: Callable[[list[dict]], int] | None,
) -> TurnSpan | None:
    """Keep largest suffix of a turn within token budget (OpenCode splitTurn)."""
    if budget <= 0 or turn.end - turn.start <= 1:
        return None
    for start in range(turn.start + 1, turn.end):
        suffix = rest[start:turn.end]
        if _estimate_messages_tokens(suffix, estimate_fn) <= budget:
            return TurnSpan(start=start, end=turn.end)
    return None


def select_tail_start_index(
    rest: list[dict],
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
    tail_turns: int | None = None,
    split_turn: bool | None = None,
    estimate_fn: Callable[[list[dict]], int] | None = None,
) -> int:
    """
    Return index in ``rest`` where preserved tail begins.
    ``0`` means entire ``rest`` is kept (no middle to compact).
    """
    limit = tail_turns if tail_turns is not None else tail_turns_limit()
    if limit <= 0 or not rest:
        return 0

    turns = group_messages_into_turns(rest)
    if not turns:
        return 0

    budget = preserve_recent_token_budget(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    recent = turns[-limit:]
    total = 0
    keep_start: int | None = None
    do_split = split_turn_enabled() if split_turn is None else split_turn

    for turn in reversed(recent):
        chunk = rest[turn.start : turn.end]
        size = _estimate_messages_tokens(chunk, estimate_fn)
        if total + size <= budget:
            total += size
            keep_start = turn.start
            continue
        remaining = budget - total
        if do_split and remaining > 0:
            split = _split_turn_suffix(rest, turn, budget=remaining, estimate_fn=estimate_fn)
            if split is not None:
                keep_start = split.start
            elif keep_start is None:
                keep_start = turn.start
        elif keep_start is None:
            keep_start = turn.start
        break

    if keep_start is None or keep_start <= 0:
        return 0
    return keep_start


def split_head_tail_turns(
    messages: list[dict],
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
    head_count: int = 3,
    min_tail_messages: int = 4,
    estimate_fn: Callable[[list[dict]], int] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (system, middle, head_tail) using turn + token tail selection."""
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= head_count + min_tail_messages:
        return system, [], rest

    head = rest[:head_count]
    body = rest[head_count:]
    tail_start = select_tail_start_index(
        body,
        max_context_tokens=max_context_tokens,
        max_output_tokens=max_output_tokens,
        estimate_fn=estimate_fn,
    )

    if tail_start <= 0:
        return system, [], head + body

    from butler.core.compaction_cutoff import find_safe_tail_start

    tail_start = find_safe_tail_start(body, tail_start)
    middle = body[:tail_start]
    tail = body[tail_start:]
    if not middle:
        return system, [], head + tail
    return system, middle, head + tail


def find_overflow_replay_user(messages: list[dict]) -> dict[str, Any] | None:
    """Last real user message before compaction (OpenCode overflow replay)."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        if is_compaction_summary_message(msg):
            continue
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        return dict(msg)
    return None


def append_overflow_replay(
    compressed: list[dict],
    replay: dict[str, Any] | None,
) -> list[dict]:
    if not replay:
        return compressed
    content = str(replay.get("content") or "").strip()
    if not content:
        return compressed
    for msg in compressed:
        if msg.get("role") == "user" and "[OVERFLOW REPLAY" in str(msg.get("content") or ""):
            return compressed
    in_tail = any(
        msg.get("role") == "user" and str(msg.get("content") or "").strip() == content
        for msg in compressed
    )
    if in_tail:
        marker = {
            "role": "user",
            "content": "[OVERFLOW REPLAY — continue the latest user task above]",
        }
    else:
        marker = {
            "role": "user",
            "content": "[OVERFLOW REPLAY — resume from this task]\n\n" + content,
        }
    return list(compressed) + [marker]
