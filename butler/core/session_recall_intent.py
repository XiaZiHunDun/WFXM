"""Detect user intents that must answer from session tool truth, not memory."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

_BACKLOG_REL_PATH = Path("docs") / "interview-demo-backlog.md"
_BACKLOG_MAX_LINES = 60
_BACKLOG_MAX_CHARS = 3000


def _read_backlog_excerpt(workspace: str | Path | None) -> str | None:
    """Read ``docs/interview-demo-backlog.md`` excerpt for the inventory banner.

    Returns ``None`` when workspace is missing, file is absent, or read fails.
    The caller must still emit the banner — excerpt is a best-effort embed.
    """
    if not workspace:
        return None
    try:
        path = Path(str(workspace)) / _BACKLOG_REL_PATH
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()[:_BACKLOG_MAX_LINES]
        excerpt = "\n".join(lines)
        if len(excerpt) > _BACKLOG_MAX_CHARS:
            excerpt = excerpt[:_BACKLOG_MAX_CHARS] + "\n... (truncated)"
        return excerpt
    except OSError:
        return None

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

_LOCAL_PROJECT_INVENTORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"改进项"),
    re.compile(r"待办"),
    re.compile(r"有哪些任务"),
    re.compile(r"任务.*待做"),
    re.compile(r"架构.*(?:分析|改进|是否需要|要不要)"),
    re.compile(r"(?:分析|看看).*(?:架构|代码结构)"),
)

SESSION_READ_RECALL_BLOCKED_TOOLS = frozenset({
    "butler_recall",
    "butler_remember",
    "search_project_knowledge",
    "delegate_task",
    "search_files",
    "list_directory",
})

LOCAL_PROJECT_INVENTORY_BLOCKED_TOOLS = frozenset({
    "delegate_task",
    "web_search",
    "web_fetch",
    "search_files",
    "list_directory",
    "search_project_knowledge",
})


def is_session_read_recall_intent(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _RECALL_READ_PATTERNS)


def is_local_project_inventory_intent(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _LOCAL_PROJECT_INVENTORY_PATTERNS)


def _session_read_recall_gate_active_safe() -> bool:
    from butler.core.best_effort import safe_best_effort
    from butler.execution_context import is_session_read_recall_gate_active

    def _run() -> bool:
        return bool(is_session_read_recall_gate_active())

    result = safe_best_effort(
        _run,
        label="session_recall_intent.gate_active",
        default=False,
    )
    return bool(result)


def _local_project_inventory_gate_active_safe() -> bool:
    from butler.core.best_effort import safe_best_effort
    from butler.execution_context import is_local_project_inventory_gate_active

    def _run() -> bool:
        return bool(is_local_project_inventory_gate_active())

    result = safe_best_effort(
        _run,
        label="session_recall_intent.inventory_gate_active",
        default=False,
    )
    return bool(result)


def check_session_read_recall_tool_block(tool_name: str) -> str | None:
    """Block memory/delegate tools when answering from transcript read_file truth."""
    if not _session_read_recall_gate_active_safe():
        return None
    name = str(tool_name or "").strip().lower()
    if name in SESSION_READ_RECALL_BLOCKED_TOOLS:
        return (
            "本轮为 read_file 清单问题：只复述 ephemeral 横幅或 /本轮已读 事实，"
            "勿调用记忆检索、委派或目录搜索。"
        )
    return None


def check_local_project_inventory_tool_block(tool_name: str) -> str | None:
    if not _local_project_inventory_gate_active_safe():
        return None
    name = str(tool_name or "").strip().lower()
    if name in LOCAL_PROJECT_INVENTORY_BLOCKED_TOOLS:
        return (
            "本轮为项目待办/改进项/架构盘点：请 read_file 本地文档并直接总结，"
            "勿 delegate_task / web_search / web_fetch。"
        )
    if name.startswith("mcp_firecrawl"):
        return (
            "本轮为项目内盘点：勿 Firecrawl；请 read_file "
            "docs/interview-demo-backlog.md 等本地文件。"
        )
    return None


def detect_local_project_inventory_banner(
    user_text: str,
    *,
    workspace: str | Path | None = None,
) -> str | None:
    if not is_local_project_inventory_intent(user_text):
        return None
    parts: list[str] = [
        "[Intent: local_project_inventory]",
        "架构/改进项真相源（已附在下面）。",
        "**只读回答**：禁止 read_file / delegate_task / web_search / web_fetch / Firecrawl / list_directory / search_files。",
        "**严格格式**：3–8 行，每行「数字. 一句要点」；禁止加粗、## 标题、表格、嵌套列表。",
        "**禁止输出**：解释推理、'好的我来…'、'基于…'、'以上' 等开场/收尾；直接给要点。",
        "MagicMock/、LingWen1/LingWen1/ 为测试残留目录，勿当正式架构组件。",
    ]
    excerpt = _read_backlog_excerpt(workspace)
    if excerpt:
        parts.append("")
        parts.append(f"--- docs/interview-demo-backlog.md (前 {_BACKLOG_MAX_LINES} 行摘要) ---")
        parts.append(excerpt)
        parts.append("--- end ---")
    else:
        parts.append("")
        parts.append("(未读到 backlog；请 read_file docs/interview-demo-backlog.md 一次后输出)")
    return "\n".join(parts)


def detect_session_read_recall_banner(
    user_text: str,
    session_key: str,
    *,
    workspace: str | Path | None = None,
) -> str | None:
    if not is_session_read_recall_intent(user_text):
        return None
    from butler.core.session_tool_index import format_session_read_files_block

    return cast(str | None, format_session_read_files_block(
        session_key,
        workspace=workspace,
        title="[Intent: session_read_recall]",
    ))


__all__ = [
    "LOCAL_PROJECT_INVENTORY_BLOCKED_TOOLS",
    "SESSION_READ_RECALL_BLOCKED_TOOLS",
    "check_local_project_inventory_tool_block",
    "check_session_read_recall_tool_block",
    "detect_local_project_inventory_banner",
    "detect_session_read_recall_banner",
    "is_local_project_inventory_intent",
    "is_session_read_recall_intent",
]
