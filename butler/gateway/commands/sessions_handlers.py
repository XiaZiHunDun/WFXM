"""WeChat slash: /会话 — recent transcript sessions."""

from __future__ import annotations

from butler.env_parse import int_env
from typing import Any

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def handle_sessions_command(
    orchestrator: Any,
    arg: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> str:
    # Sprint 11 SEC-11-7: list_sessions 返全量 session_key（含 chat_id），
    # 信息泄露风险。仅 Owner 可看。
    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return str(owner_required_message())
    from butler.cli.sessions_cli import list_sessions

    try:
        limit = int_env("BUTLER_SESSIONS_LIST_LIMIT", 20)
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
