"""Best-effort compaction report helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def load_checkpoint_safe(session_key: str) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        from butler.core.compaction_checkpoint import load_checkpoint

        loaded = load_checkpoint(session_key)
        return loaded if isinstance(loaded, dict) else None

    result = safe_best_effort(_run, label="compaction_status.load_checkpoint", default=None)
    return result if result is None or isinstance(result, dict) else None


def last_compact_transcript_line(session_key: str) -> str:
    def _run() -> str:
        from butler.core.session_epoch import load_epoch_transcript_rows

        rows = load_epoch_transcript_rows(session_key, max_lines=120)
        done = [r for r in rows if str(r.get("type") or "") == "compact_done"]
        if not done:
            return ""
        last = done[-1]
        after = last.get("tokens_after")
        summary_chars = last.get("summary_chars")
        ts = str(last.get("ts") or "").strip()
        detail = f"tokens≈{after}" if after is not None else ""
        if summary_chars:
            detail = f"{detail} · 摘要{summary_chars}字".strip(" ·")
        if ts:
            detail = f"{ts} · {detail}".strip(" ·")
        return f"最近 transcript 压缩: {detail or '已完成'}"

    result = safe_best_effort(
        _run,
        label="compaction_status.transcript_compact",
        default="",
    )
    return result if isinstance(result, str) else ""
