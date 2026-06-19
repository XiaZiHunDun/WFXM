"""Strip internal ops / approval phrases from user-visible WeChat text."""

from __future__ import annotations

import re

# Order matters: multiline MCP approval blocks before single-line phrases.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"（会话已从 transcript 恢复[^）]*）\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"MCP 工具需确认[^\n]*(?:\n\s+[^\n]+){0,8}",
        re.IGNORECASE,
    ),
    re.compile(r"反馈需要审批[^。\n]*[。\n]*"),
    re.compile(r"我直接用已有的搜索结果来回答。\s*"),
    re.compile(r"回复\s*/批准一次[^\n]*"),
    re.compile(r"回复\s*/始终允许[^\n]*"),
)


def scrub_internal_ops_leaks(text: str) -> str:
    """Remove harness/MCP approval noise; keep substantive answer body."""
    if not text:
        return text
    out = str(text)
    for pat in _PATTERNS:
        out = pat.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or str(text).strip()


__all__ = ["scrub_internal_ops_leaks"]
