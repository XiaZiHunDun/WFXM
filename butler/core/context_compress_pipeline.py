"""``compress_messages`` orchestration extracted from ``context_compressor`` (P1-C)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.context_compress_support import (
    record_compress_completed,
    record_compress_scheduled,
    record_compress_started,
    record_overflow_replay,
)
from butler.core.context_compressor import (
    SUMMARY_PREFIX,
    _estimate_tokens,
    _prune_tool_outputs,
    _split_head_tail,
    _summarize_middle,
    truncate_tool_responses_to_budget,
)
from butler.core.turn_compaction import _write_compaction_diagnostics
from butler.execution_context import get_audit_session_key

logger = logging.getLogger(__name__)


def _prune_with_skill_rescue(
    messages: list[dict],
) -> tuple[list[dict], list[dict]]:
    pruned = _prune_tool_outputs(messages)
    skill_rescued: list[dict] = []
    try:
        from butler.core.skill_compact_rescue import extract_skill_rescue_messages

        pruned, skill_rescued = extract_skill_rescue_messages(pruned)
    except Exception as exc:
        logger.debug("Skill compact rescue skipped: %s", exc)
    return pruned, skill_rescued


def _resolve_replay_user(pruned: list[dict], *, overflow_replay: bool) -> dict | None:
    if not overflow_replay:
        return None
    try:
        from butler.core.turn_compaction import find_overflow_replay_user

        return find_overflow_replay_user(pruned)
    except Exception as exc:
        logger.debug("compress messages skipped: %s", exc)
        return None


def _split_for_compaction(
    pruned: list[dict],
    *,
    max_tokens: int,
    head_count: int,
    max_tail_messages: int,
    min_tail_messages: int,
    max_output_tokens: int | None,
    diagnostics: dict[str, Any] | None,
) -> tuple[list[dict], list[dict], list[dict]]:
    try:
        from butler.core.turn_compaction import split_head_tail_turns, turn_compaction_enabled

        if turn_compaction_enabled():
            system, middle, head_tail = split_head_tail_turns(
                pruned,
                max_context_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                head_count=head_count,
                min_tail_messages=min_tail_messages,
                estimate_fn=_estimate_tokens,
                diagnostics=diagnostics,
            )
            if not middle:
                legacy_system, legacy_middle, legacy_head_tail = _split_head_tail(
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
    except Exception as exc:
        logger.debug("Turn compaction fallback: %s", exc)
        if isinstance(diagnostics, dict):
            _write_compaction_diagnostics(
                diagnostics,
                strategy="legacy_split",
                tail_turns_kept=0,
                split_turn_applied=False,
                preserved_recent_budget=0,
                tail_token_count=0,
                tail_start_index=0,
            )
            diagnostics["compaction_turn_fallback"] = "legacy_split"
    return _split_head_tail(
        pruned,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
    )


def _merge_skill_rescue(
    head_tail: list[dict],
    skill_rescued: list[dict],
) -> list[dict]:
    if not skill_rescued:
        return head_tail
    try:
        from butler.core.skill_compact_rescue import merge_skill_rescue_into_tail

        return merge_skill_rescue_into_tail(head_tail, skill_rescued)
    except Exception as exc:
        logger.debug("Skill rescue merge skipped: %s", exc)
        return head_tail


def _apply_summary_placement(
    system: list[dict],
    head_tail: list[dict],
    summary: str,
    initial_injection: Any,
) -> list[dict]:
    summary_msg = {"role": "user", "content": SUMMARY_PREFIX + summary}
    try:
        from butler.core.compaction_phase import (
            InitialContextInjection,
            apply_summary_placement,
        )

        injection = initial_injection
        if injection is None:
            injection = InitialContextInjection.DO_NOT_INJECT
        return apply_summary_placement(system, head_tail, summary_msg, injection)
    except Exception:
        return system + [summary_msg] + head_tail


def run_compress_messages(
    messages: list[dict],
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
) -> tuple[list[dict], str, bool]:
    """Compress messages if over threshold. Returns (messages, summary, did_compress)."""
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

    pruned, skill_rescued = _prune_with_skill_rescue(messages)
    replay_user = _resolve_replay_user(pruned, overflow_replay=overflow_replay)
    system, middle, head_tail = _split_for_compaction(
        pruned,
        max_tokens=max_tokens,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
        max_output_tokens=max_output_tokens,
        diagnostics=diagnostics,
    )

    if not middle:
        if skill_rescued:
            head_tail = _merge_skill_rescue(head_tail, skill_rescued)
            return system + head_tail, previous_summary, False
        return pruned, previous_summary, False

    try:
        from butler.core.fact_extraction import extract_pre_compact_facts

        extract_pre_compact_facts(session_key, middle)
    except Exception as exc:
        logger.debug("Fact extraction skipped: %s", exc)

    middle = truncate_tool_responses_to_budget(middle)
    summary, used_remote = _summarize_middle(middle, previous_summary)
    try:
        from butler.core.evidence_extract import append_evidence_to_summary

        summary = append_evidence_to_summary(summary, middle, diagnostics)
    except Exception as exc:
        logger.debug("Compact evidence extract skipped: %s", exc)

    if not summary.strip():
        logger.warning(
            "Summary generation failed; preserving original messages instead of compressing"
        )
        head_tail = _merge_skill_rescue(head_tail, skill_rescued)
        return system + head_tail + middle, previous_summary, False

    if isinstance(diagnostics, dict):
        diagnostics["compaction_remote"] = used_remote

    compressed = _apply_summary_placement(system, head_tail, summary, initial_injection)
    if skill_rescued:
        tail_only = [m for m in compressed if m.get("role") != "system"]
        system_only = [m for m in compressed if m.get("role") == "system"]
        compressed = system_only + _merge_skill_rescue(tail_only, skill_rescued)

    if overflow_replay and replay_user:
        try:
            from butler.core.turn_compaction import append_overflow_replay

            compressed = append_overflow_replay(compressed, replay_user)
        except Exception as exc:
            logger.debug("compress messages skipped: %s", exc)
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
