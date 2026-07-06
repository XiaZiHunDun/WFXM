"""Auto-generate session titles from first user message."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TITLE_LEN = 40
_COMMAND_RE = re.compile(r"^/\S+")


def generate_session_title(first_message: str) -> str:
    """Generate a short descriptive title from the first user message."""
    text = (first_message or "").strip()
    if not text:
        return "新会话"

    if _COMMAND_RE.match(text):
        cmd = text.split()[0]
        return f"命令: {cmd}"

    clean = re.sub(r"\s+", " ", text)
    if len(clean) <= _MAX_TITLE_LEN:
        return clean

    words = clean[:_MAX_TITLE_LEN].rsplit(" ", 1)
    return words[0] + "…" if len(words) > 1 else clean[:_MAX_TITLE_LEN] + "…"


def format_session_list(sessions: list[dict[str, Any]], *, limit: int = 10) -> str:
    """Format session list sorted by last activity with preview."""
    if not sessions:
        return "暂无历史会话。"

    sorted_sessions = sorted(
        sessions,
        key=lambda s: s.get("last_active", ""),
        reverse=True,
    )[:limit]

    lines = ["会话列表（按最近活跃排序）:", ""]
    for i, sess in enumerate(sorted_sessions, 1):
        title = sess.get("title") or sess.get("session_key", "?")
        last_msg = (sess.get("last_message_preview") or "")[:50]
        last_active = sess.get("last_active", "?")
        mark = "▸ " if sess.get("current") else "  "
        lines.append(f"{mark}{i}. {title}")
        if last_msg:
            lines.append(f"     最后: {last_msg}")
        lines.append(f"     活跃: {last_active}")
    return "\n".join(lines)


__all__ = ["format_session_list", "generate_session_title"]
