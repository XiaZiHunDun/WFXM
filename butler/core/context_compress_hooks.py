"""Optional compaction sub-steps (P2-F) — fail-open via ``safe_best_effort``."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.core.context_compressor import SUMMARY_PREFIX, _prune_tool_outputs

MessageDict = dict[str, Any]


def prune_with_skill_rescue(messages: list[MessageDict]) -> tuple[list[MessageDict], list[MessageDict]]:
    pruned = _prune_tool_outputs(messages)

    def _run() -> tuple[list[MessageDict], list[MessageDict]]:
        from butler.core.skill_compact_rescue import extract_skill_rescue_messages

        return cast(
            tuple[list[MessageDict], list[MessageDict]],
            extract_skill_rescue_messages(pruned),
        )

    rescued = safe_best_effort(
        _run,
        label="context_compress.skill_rescue_prune",
        default=None,
    )
    if rescued is None:
        return pruned, []
    return cast(tuple[list[MessageDict], list[MessageDict]], rescued)


def resolve_replay_user(pruned: list[MessageDict], *, overflow_replay: bool) -> MessageDict | None:
    if not overflow_replay:
        return None

    def _run() -> MessageDict | None:
        from butler.core.turn_compaction import find_overflow_replay_user

        return cast(MessageDict | None, find_overflow_replay_user(pruned))

    return cast(
        MessageDict | None,
        safe_best_effort(
            _run,
            label="context_compress.overflow_replay_user",
            default=None,
        ),
    )


def merge_skill_rescue(head_tail: list[MessageDict], skill_rescued: list[MessageDict]) -> list[MessageDict]:
    if not skill_rescued:
        return head_tail

    def _run() -> list[MessageDict]:
        from butler.core.skill_compact_rescue import merge_skill_rescue_into_tail

        return cast(list[MessageDict], merge_skill_rescue_into_tail(head_tail, skill_rescued))

    merged = safe_best_effort(
        _run,
        label="context_compress.skill_rescue_merge",
        default=None,
    )
    return head_tail if merged is None else cast(list[MessageDict], merged)


def apply_summary_placement(
    system: list[MessageDict],
    head_tail: list[MessageDict],
    summary: str,
    initial_injection: Any,
) -> list[MessageDict]:
    summary_msg: MessageDict = {"role": "user", "content": SUMMARY_PREFIX + summary}

    def _run() -> list[MessageDict]:
        from butler.core.compaction_phase import (
            InitialContextInjection,
            apply_summary_placement as _apply,
        )

        injection = initial_injection
        if injection is None:
            injection = InitialContextInjection.DO_NOT_INJECT
        return cast(list[MessageDict], _apply(system, head_tail, summary_msg, injection))

    placed = safe_best_effort(
        _run,
        label="context_compress.summary_placement",
        default=None,
    )
    return system + [summary_msg] + head_tail if placed is None else cast(list[MessageDict], placed)


def extract_pre_compact_facts(session_key: str, middle: list[MessageDict]) -> None:
    def _run() -> None:
        from butler.core.fact_extraction import extract_pre_compact_facts as _extract

        _extract(session_key, middle)

    safe_best_effort(_run, label="context_compress.pre_compact_facts", default=None)


def append_compact_evidence(
    summary: str,
    middle: list[MessageDict],
    diagnostics: dict[str, Any] | None,
) -> str:
    def _run() -> str:
        from butler.core.evidence_extract import append_evidence_to_summary

        return str(append_evidence_to_summary(summary, middle, diagnostics))

    enriched = safe_best_effort(
        _run,
        label="context_compress.evidence_extract",
        default=None,
    )
    return summary if enriched is None else str(enriched)


def append_overflow_replay(compressed: list[MessageDict], replay_user: MessageDict) -> list[MessageDict]:
    def _run() -> list[MessageDict]:
        from butler.core.turn_compaction import append_overflow_replay as _append

        return cast(list[MessageDict], _append(compressed, replay_user))

    replayed = safe_best_effort(
        _run,
        label="context_compress.overflow_replay_append",
        default=None,
    )
    return compressed if replayed is None else cast(list[MessageDict], replayed)


__all__ = [
    "append_compact_evidence",
    "append_overflow_replay",
    "apply_summary_placement",
    "extract_pre_compact_facts",
    "merge_skill_rescue",
    "prune_with_skill_rescue",
    "resolve_replay_user",
]
