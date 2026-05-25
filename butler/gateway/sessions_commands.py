"""WeChat slash: /会话 — recent transcript sessions."""

from __future__ import annotations

import os
from typing import Any


def handle_sessions_command(
    orchestrator: Any,
    arg: str,
    *,
    session_key: str = "",
) -> str:
    from butler.cli.sessions_cli import list_sessions

    try:
        limit = int(os.getenv("BUTLER_SESSIONS_LIST_LIMIT", "20"))
    except ValueError:
        limit = 20
    text = (arg or "").strip()
    search = ""
    if text and text.lower() not in ("list", "列表"):
        search = text
    rows = list_sessions(search=search, limit=limit)
    if not rows:
        return "暂无会话记录（~/.butler/sessions/）。"
    proj = orchestrator.project_manager.get_current(session_key=session_key)
    proj_name = str(getattr(proj, "name", "") or "") if proj else ""
    lines = [f"最近会话（当前项目: {proj_name or '未选择'}）:"]
    for row in rows[:limit]:
        mark = "←" if row.get("session_key") == session_key else " "
        lines.append(
            f"{mark} {row.get('session_key')} | lines={row.get('transcript_lines')} "
            f"| {row.get('updated_at', '')[:19]}"
        )
    lines.append("CLI: butler sessions list [--search]")
    return "\n".join(lines)


__all__ = ["handle_sessions_command"]
