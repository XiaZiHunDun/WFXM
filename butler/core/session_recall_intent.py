"""Detect user intents that must answer from session tool truth, not memory."""

from __future__ import annotations

import re

_RECALL_READ_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"刚才读过哪些文件"),
    re.compile(r"刚才读(?:过|了)哪些"),
    re.compile(r"读过哪些文件"),
    re.compile(r"列个清单"),
    re.compile(r"列一下.*清单"),
    re.compile(r"把我们刚才读过"),
    re.compile(r"本轮.*read_file", re.I),
    re.compile(r"哪些文件.*读过"),
)

SESSION_READ_RECALL_BLOCKED_TOOLS = frozenset({
    "butler_recall",
    "butler_remember",
    "search_project_knowledge",
    "delegate_task",
    "search_files",
    "list_directory",
})


def is_session_read_recall_intent(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _RECALL_READ_PATTERNS)


def check_session_read_recall_tool_block(tool_name: str) -> str | None:
    """Block memory/delegate tools when answering from transcript read_file truth."""
    try:
        from butler.execution_context import is_session_read_recall_gate_active
    except Exception:
        return None
    if not is_session_read_recall_gate_active():
        return None
    name = str(tool_name or "").strip().lower()
    if name in SESSION_READ_RECALL_BLOCKED_TOOLS:
        return (
            "本轮为 read_file 清单问题：只复述 ephemeral 横幅或 /本轮已读 事实，"
            "勿调用记忆检索、委派或目录搜索。"
        )
    return None


def detect_session_read_recall_banner(
    user_text: str,
    session_key: str,
    *,
    workspace: str | Path | None = None,
) -> str | None:
    if not is_session_read_recall_intent(user_text):
        return None
    from butler.core.session_tool_index import format_session_read_files_block

    return format_session_read_files_block(
        session_key,
        workspace=workspace,
        title="[Intent: session_read_recall]",
    )


__all__ = [
    "SESSION_READ_RECALL_BLOCKED_TOOLS",
    "check_session_read_recall_tool_block",
    "detect_session_read_recall_banner",
    "is_session_read_recall_intent",
]
