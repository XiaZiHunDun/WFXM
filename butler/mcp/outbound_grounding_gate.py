"""L3: correct LLM replies that drift from MCP list tool summaries."""

from __future__ import annotations

import re
from typing import Any


def _names_from_summary(summary: str) -> list[str]:
    names: list[str] = []
    for line in str(summary or "").splitlines():
        text = line.strip()
        if not text:
            continue
        m = re.match(r"^\d+\.\s+\*?\*?([^*—\-]+)", text)
        if m:
            names.append(m.group(1).strip())
            continue
        text = text.lstrip("-•* ").strip()
        if not text:
            continue
        token = text.split()[0].strip("`").strip("*")
        if token and not token.endswith("."):
            names.append(token)
    return names


def _reply_grounded(assistant_text: str, summary: str, *, min_hits: int = 1) -> bool:
    reply = str(assistant_text or "")
    if not reply.strip():
        return False
    names = _names_from_summary(summary)
    if not names:
        return True
    hits = 0
    for name in names[:5]:
        core = name.strip("`").strip("*")
        parts = [core]
        if "/" in core:
            parts.extend(p.strip() for p in core.split("/", 1))
        if any(p and p in reply for p in parts):
            hits += 1
    return hits >= min(min_hits, len(names))


def try_correct_ungrounded_list_reply(
    user_text: str,
    assistant_text: str,
    messages: list[dict[str, Any]],
) -> str | None:
    """If a grounded direct reply exists but assistant text omits tool facts, replace it."""
    from butler.mcp.github_grounding import (
        try_github_issue_list_direct_reply,
        try_github_repo_list_direct_reply,
    )
    from butler.mcp.todoist_grounding import try_todoist_project_list_direct_reply

    for fn in (
        try_github_repo_list_direct_reply,
        try_github_issue_list_direct_reply,
        try_todoist_project_list_direct_reply,
    ):
        direct = fn(messages, user_text=user_text)
        if not direct:
            continue
        summary_line = ""
        for line in direct.splitlines():
            if line.strip().startswith(("1.", "-", "•")) or "/" in line:
                summary_line = line
                break
        if _reply_grounded(assistant_text, summary_line or direct):
            return None
        return direct
    return None
