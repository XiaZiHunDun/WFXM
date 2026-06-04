"""Transcript tail summary for /诊断."""

from __future__ import annotations

from typing import Any
import logging


logger = logging.getLogger(__name__)

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
    compact_started = sum(1 for r in rows if r.get("type") == "compact_started")
    compact_done = sum(1 for r in rows if r.get("type") == "compact_done")
    compact_failed = sum(1 for r in rows if r.get("type") == "compact_failed")
    overflow_replay = sum(1 for r in rows if r.get("type") == "overflow_replay")
    queue_ops = sum(1 for r in rows if r.get("type") in ("queue_op", "queue_drop"))
    last = rows[-1] if rows else {}
    last_type = str(last.get("type") or "-")

    lines = [
        f"Transcript: 近 {len(rows)} 条 · 压缩 {compact_done}/{compact_scheduled} 完成"
        f" · started={compact_started} · failed={compact_failed}"
        f" · 队列事件 {queue_ops}",
        f"Transcript 末条: {last_type}",
    ]
    if overflow_replay:
        lines.append(
            f"⚠️ 续跑提示: 本会话触发了 {overflow_replay} 次 413/overflow 续跑"
            f" (overflow_replay 事件), 上下文已被强制重放, 可考虑精简后重试"
        )
    if session_todos_enabled():
        open_n = count_open_todos(session_key)
        lines.append(f"会话待办: 未完成 {open_n} 条 (发 /待办 查看)")
    pending = _after_commit_pending()
    if pending:
        lines.append(f"Post-commit 队列: 待发 {pending} 条")
    try:
        from butler.mcp.diagnostics import format_mcp_diagnostic_lines

        lines.extend(format_mcp_diagnostic_lines(session_key))
    except Exception as exc:
        logger.debug("format transcript diagnostic lines skipped: %s", exc)
    return lines


def _after_commit_pending() -> int:
    try:
        from butler.core.post_commit import pending_after_commit_count

        return pending_after_commit_count()
    except Exception:
        return 0


def summarize_compact_events(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {
        "compact_scheduled": 0,
        "compact_started": 0,
        "compact_done": 0,
        "compact_failed": 0,
        "compact_boundary": 0,
        "overflow_replay": 0,
    }
    for row in rows:
        t = str(row.get("type") or "")
        if t in out:
            out[t] += 1
    return out
