"""Memory unified-recall lines for ``butler doctor`` / health (P3-H)."""

from __future__ import annotations

from butler.memory.observer_queue import observer_queue_enabled
from butler.memory.unified_recall_config import observation_recall_enabled, unified_recall_enabled
from butler.ops.rag_diagnostics_ops import append_unified_recall_flag_lines
from butler.ops.transcript_diagnostics import transcript_fts_drift


def format_memory_recall_doctor_lines() -> list[str]:
    lines: list[str] = []
    append_unified_recall_flag_lines(lines)
    lines.append(f"  Observation 队列: {'开' if observer_queue_enabled() else '关'}")
    lines.append("  experience 默认合并 coding: 开（recall_router + prefetch）")
    drift = transcript_fts_drift()
    if drift.get("fts_enabled"):
        stale = " ⚠ 陈旧" if drift.get("transcript_fts_stale") else ""
        lines.append(
            f"  P3-H transcript scope: 开 "
            f"(jsonl {drift.get('transcript_jsonl_lines', 0)} / "
            f"fts {drift.get('transcript_fts_rows', 0)}){stale}"
        )
    else:
        lines.append("  P3-H transcript scope: 关（BUTLER_TRANSCRIPT_FTS=0）")
    if unified_recall_enabled() and observation_recall_enabled() and observer_queue_enabled():
        lines.append("  gateway lead 剖面 P3-H: ✓（hybrid + observation 就绪）")
    elif unified_recall_enabled() or observation_recall_enabled():
        lines.append("  gateway lead 剖面 P3-H: 部分（见上项 env）")
    return lines


__all__ = ["format_memory_recall_doctor_lines"]
