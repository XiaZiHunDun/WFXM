"""Transcript tail summary for /诊断."""

from __future__ import annotations

from typing import Any


def format_transcript_diagnostic_lines(session_key: str) -> list[str]:
    try:
        from butler.core.session_transcript import load_transcript_tail, transcript_enabled
        from butler.core.session_todos import count_open_todos, session_todos_enabled
    except Exception:
        return []

    if not transcript_enabled():
        return ["Transcript: 已关闭 (BUTLER_SESSION_TRANSCRIPT=0)"]

    rows = load_transcript_tail(session_key, max_lines=80)
    if not rows:
        return ["Transcript: 暂无记录"]

    compact_scheduled = sum(1 for r in rows if r.get("type") == "compact_scheduled")
    compact_done = sum(1 for r in rows if r.get("type") == "compact_done")
    queue_ops = sum(1 for r in rows if r.get("type") in ("queue_op", "queue_drop"))
    last = rows[-1] if rows else {}
    last_type = str(last.get("type") or "-")

    lines = [
        f"Transcript: 近 {len(rows)} 条 · 压缩 {compact_done}/{compact_scheduled} 完成"
        f" · 队列事件 {queue_ops}",
        f"Transcript 末条: {last_type}",
    ]
    if session_todos_enabled():
        open_n = count_open_todos(session_key)
        lines.append(f"会话待办: 未完成 {open_n} 条 (发 /待办 查看)")
    pending = _after_commit_pending()
    if pending:
        lines.append(f"Post-commit 队列: 待发 {pending} 条")
    return lines


def _after_commit_pending() -> int:
    try:
        from butler.core.post_commit import pending_after_commit_count

        return pending_after_commit_count()
    except Exception:
        return 0


def summarize_compact_events(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {"compact_scheduled": 0, "compact_done": 0, "compact_boundary": 0}
    for row in rows:
        t = str(row.get("type") or "")
        if t in out:
            out[t] += 1
    return out
