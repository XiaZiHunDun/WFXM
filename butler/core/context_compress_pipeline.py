"""``compress_messages`` orchestration extracted from ``context_compressor`` (P1-C)."""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.core.context_compress_hooks import (
    append_compact_evidence,
    append_overflow_replay,
    apply_summary_placement,
    extract_pre_compact_facts,
    merge_skill_rescue,
    prune_with_skill_rescue,
    resolve_replay_user,
)
from butler.core.context_compress_support import (
    legacy_compaction_split_fallback,
    record_compress_completed,
    record_compress_scheduled,
    record_compress_started,
    record_overflow_replay,
    split_for_compaction_turn,
)
from butler.core.context_compressor import (
    _estimate_tokens,
    _split_head_tail,
    _summarize_middle,
    truncate_tool_responses_to_budget,
)
from butler.core.turn_compaction import _write_compaction_diagnostics
from butler.execution_context import get_audit_session_key

logger = logging.getLogger(__name__)

_CompactionSplit = tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]


def _split_for_compaction(
    pruned: list[dict[str, Any]],
    *,
    max_tokens: int,
    head_count: int,
    max_tail_messages: int,
    min_tail_messages: int,
    max_output_tokens: int | None,
    diagnostics: dict[str, Any] | None,
    protected_keywords: list[str] | None = None,
) -> _CompactionSplit:
    from functools import partial

    legacy_split_fn_with_keywords = partial(
        _split_head_tail, protect_keywords=protected_keywords
    )

    turn_split = split_for_compaction_turn(
        pruned,
        max_tokens=max_tokens,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
        max_output_tokens=max_output_tokens,
        diagnostics=diagnostics,
        estimate_fn=_estimate_tokens,
        legacy_split_fn=legacy_split_fn_with_keywords,
        write_diagnostics_fn=_write_compaction_diagnostics,
    )
    if turn_split is not None:
        return cast(_CompactionSplit, turn_split)
    return cast(
        _CompactionSplit,
        legacy_compaction_split_fallback(
            pruned,
            diagnostics=diagnostics,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
            legacy_split_fn=legacy_split_fn_with_keywords,
            write_diagnostics_fn=_write_compaction_diagnostics,
        ),
    )


def run_compress_messages(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 128000,
    threshold_ratio: float = 0.5,
    previous_summary: str = "",
    min_messages_to_compress: int = 12,
    head_count: int = 3,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
    overflow_replay: bool = False,
    max_output_tokens: int | None = None,
    initial_injection: Any = None,
    diagnostics: dict[str, Any] | None = None,
    protected_keywords: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Compress messages if over threshold. Returns (messages, summary, did_compress).

    Args:
        protected_keywords: List of keywords that, if found in middle messages,
            will protect those messages from summarization.
    """
    estimated = _estimate_tokens(messages)
    threshold = int(max_tokens * threshold_ratio)
    if estimated <= threshold or len(messages) < min_messages_to_compress:
        return messages, previous_summary, False

    session_key = get_audit_session_key(fallback="_global")
    record_compress_scheduled(
        session_key=session_key,
        messages_before=len(messages),
        tokens_estimated=estimated,
    )
    record_compress_started(session_key=session_key, overflow_replay=overflow_replay)

    pruned, skill_rescued = prune_with_skill_rescue(messages)
    replay_user = resolve_replay_user(pruned, overflow_replay=overflow_replay)
    system, middle, head_tail = _split_for_compaction(
        pruned,
        max_tokens=max_tokens,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
        max_output_tokens=max_output_tokens,
        diagnostics=diagnostics,
        protected_keywords=protected_keywords,
    )

    if not middle:
        if skill_rescued:
            head_tail = merge_skill_rescue(head_tail, skill_rescued)
            return system + head_tail, previous_summary, False
        return pruned, previous_summary, False

    extract_pre_compact_facts(session_key, middle)

    middle = truncate_tool_responses_to_budget(middle)
    summary, used_remote = _summarize_middle(middle, previous_summary)
    summary = append_compact_evidence(summary, middle, diagnostics)

    if not summary.strip():
        logger.warning(
            "Summary generation failed; preserving original messages instead of compressing"
        )
        head_tail = merge_skill_rescue(head_tail, skill_rescued)
        return system + head_tail + middle, previous_summary, False

    if isinstance(diagnostics, dict):
        diagnostics["compaction_remote"] = used_remote

    compressed = apply_summary_placement(system, head_tail, summary, initial_injection)
    if skill_rescued:
        tail_only = [m for m in compressed if m.get("role") != "system"]
        system_only = [m for m in compressed if m.get("role") == "system"]
        compressed = system_only + merge_skill_rescue(tail_only, skill_rescued)

    if overflow_replay and replay_user:
        compressed = append_overflow_replay(compressed, replay_user)
        record_overflow_replay(session_key=session_key, replay_user=replay_user)

    tokens_after = _estimate_tokens(compressed)
    logger.info(
        "Context compressed: %d→%d msgs, ~%d→%d tokens",
        len(messages),
        len(compressed),
        estimated,
        tokens_after,
    )
    record_compress_completed(
        session_key=session_key,
        summary_len=len(summary),
        messages_before=len(messages),
        messages_after=len(compressed),
        tokens_before=estimated,
        tokens_after=tokens_after,
        summary_chars=len(summary),
        remote=used_remote,
    )
    return compressed, summary, True


__all__ = ["run_compress_messages"]
