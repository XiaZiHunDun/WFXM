"""Optional compaction sub-steps (P2-F) — fail-open via ``safe_best_effort``."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.context_compressor import SUMMARY_PREFIX, _prune_tool_outputs


def prune_with_skill_rescue(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    pruned = _prune_tool_outputs(messages)

    def _run() -> tuple[list[dict], list[dict]]:
        from butler.core.skill_compact_rescue import extract_skill_rescue_messages

        return extract_skill_rescue_messages(pruned)

    rescued = safe_best_effort(
        _run,
        label="context_compress.skill_rescue_prune",
        default=None,
    )
    if rescued is None:
        return pruned, []
    return rescued


def resolve_replay_user(pruned: list[dict], *, overflow_replay: bool) -> dict | None:
    if not overflow_replay:
        return None

    def _run() -> dict | None:
        from butler.core.turn_compaction import find_overflow_replay_user

        return find_overflow_replay_user(pruned)

    return safe_best_effort(
        _run,
        label="context_compress.overflow_replay_user",
        default=None,
    )


def merge_skill_rescue(head_tail: list[dict], skill_rescued: list[dict]) -> list[dict]:
    if not skill_rescued:
        return head_tail

    def _run() -> list[dict]:
        from butler.core.skill_compact_rescue import merge_skill_rescue_into_tail

        return merge_skill_rescue_into_tail(head_tail, skill_rescued)

    merged = safe_best_effort(
        _run,
        label="context_compress.skill_rescue_merge",
        default=None,
    )
    return head_tail if merged is None else merged


def apply_summary_placement(
    system: list[dict],
    head_tail: list[dict],
    summary: str,
    initial_injection: Any,
) -> list[dict]:
    summary_msg = {"role": "user", "content": SUMMARY_PREFIX + summary}

    def _run() -> list[dict]:
        from butler.core.compaction_phase import (
            InitialContextInjection,
            apply_summary_placement as _apply,
        )

        injection = initial_injection
        if injection is None:
            injection = InitialContextInjection.DO_NOT_INJECT
        return _apply(system, head_tail, summary_msg, injection)

    placed = safe_best_effort(
        _run,
        label="context_compress.summary_placement",
        default=None,
    )
    return system + [summary_msg] + head_tail if placed is None else placed


def extract_pre_compact_facts(session_key: str, middle: list[dict]) -> None:
    def _run() -> None:
        from butler.core.fact_extraction import extract_pre_compact_facts as _extract

        _extract(session_key, middle)

    safe_best_effort(_run, label="context_compress.pre_compact_facts", default=None)


def append_compact_evidence(
    summary: str,
    middle: list[dict],
    diagnostics: dict[str, Any] | None,
) -> str:
    def _run() -> str:
        from butler.core.evidence_extract import append_evidence_to_summary

        return append_evidence_to_summary(summary, middle, diagnostics)

    enriched = safe_best_effort(
        _run,
        label="context_compress.evidence_extract",
        default=None,
    )
    return summary if enriched is None else enriched


def append_overflow_replay(compressed: list[dict], replay_user: dict) -> list[dict]:
    def _run() -> list[dict]:
        from butler.core.turn_compaction import append_overflow_replay as _append

        return _append(compressed, replay_user)

    replayed = safe_best_effort(
        _run,
        label="context_compress.overflow_replay_append",
        default=None,
    )
    return compressed if replayed is None else replayed


__all__ = [
    "append_compact_evidence",
    "append_overflow_replay",
    "apply_summary_placement",
    "extract_pre_compact_facts",
    "merge_skill_rescue",
    "prune_with_skill_rescue",
    "resolve_replay_user",
]
