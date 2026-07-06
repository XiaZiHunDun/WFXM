"""Transcript event retention weights for tombstone / compaction (Manus event_stream subset)."""

from __future__ import annotations

from typing import Any

# Higher = more likely kept when transcript file is trimmed.
_TRANSCRIPT_KEEP_PRIORITY: dict[str, int] = {
    "compact_boundary": 100,
    "compact_done": 95,
    "compact_scheduled": 90,
    "plan_step": 85,
    "workflow_step": 80,
    "knowledge_inject": 75,
    "tool_observation": 70,
    "assistant": 60,
    "user": 55,
    "todo_updated": 50,
    "tool_spill_pointer": 45,
    "transcript_revert": 40,
    "queue_op": 10,
    "queue_drop": 10,
    "tombstone": 5,
}


def transcript_source_boost(source: str) -> int:
    """Semantic source tag boost for retention (workflow / delegate / loop)."""
    src = str(source or "").strip().lower()
    boosts = {
        "workflow": 12,
        "delegate": 10,
        "loop": 0,
        "context": 2,
        "memory_prefetch": 4,
        "context_compressor": 3,
        "hygiene": 2,
    }
    return boosts.get(src, 0)


def transcript_keep_priority(entry_type: str, *, source: str = "") -> int:
    base = _TRANSCRIPT_KEEP_PRIORITY.get(str(entry_type or "").strip(), 30)
    return base + transcript_source_boost(source)


def select_transcript_rows_for_retention(
    rows: list[dict[str, Any]],
    *,
    keep_count: int,
) -> list[dict[str, Any]]:
    """Pick rows to retain by priority, preserving relative order among kept."""
    if keep_count >= len(rows):
        return list(rows)
    if keep_count <= 0:
        return []

    indexed = list(enumerate(rows))
    indexed.sort(
        key=lambda pair: (
            -transcript_keep_priority(
                str(pair[1].get("type") or ""),
                source=str(pair[1].get("source") or ""),
            ),
            pair[0],
        ),
    )
    keep_indices = sorted(idx for idx, _ in indexed[:keep_count])
    return [rows[i] for i in keep_indices]


__all__ = [
    "select_transcript_rows_for_retention",
    "transcript_keep_priority",
    "transcript_source_boost",
]
