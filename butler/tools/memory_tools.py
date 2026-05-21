"""Registry handlers for ``butler_remember`` / ``butler_recall``."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_REMEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["owner_profile", "owner_experience", "project_notes"],
            "description": (
                "owner_profile=用户偏好/称呼(全局 profile); "
                "owner_experience=跨项目经验(FTS); "
                "project_notes=当前项目 MEMORY.md 章节"
            ),
        },
        "content": {"type": "string", "description": "要记住的内容"},
        "category": {
            "type": "string",
            "description": "owner_experience 可选分类",
        },
        "section": {
            "type": "string",
            "description": "project_notes 的章节，如 Architecture/Decisions/Notes",
            "default": "Notes",
        },
    },
    "required": ["scope", "content"],
}

_RECALL_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["experience", "profile"],
            "default": "experience",
        },
        "query": {"type": "string", "description": "FTS 检索词；profile 可留空"},
        "limit": {"type": "integer", "default": 8},
        "project": {"type": "string", "description": "可选项目名过滤"},
    },
    "required": [],
}


def _memory_service():
    from butler.execution_context import get_current_orchestrator
    from butler.memory_plugin import ButlerMemoryService

    orch = get_current_orchestrator()
    if orch is not None and getattr(orch, "memory_provider", None) is not None:
        provider = orch.memory_provider
        provider._reload_butler_global()
        provider._reload_project_branch()
        return provider

    svc = ButlerMemoryService()
    session_key = ""
    try:
        from butler.execution_context import get_current_session_key

        session_key = get_current_session_key() or ""
    except Exception:
        pass
    svc.initialize(session_id=session_key or "tool")
    return svc


def tool_butler_remember(
    scope: str,
    content: str,
    category: str = "",
    section: str = "Notes",
    **_: Any,
) -> str:
    svc = _memory_service()
    return svc.handle_tool_call(
        "butler_remember",
        {
            "scope": scope,
            "content": content,
            "category": category,
            "section": section,
        },
    )


def tool_butler_recall(
    scope: str = "experience",
    query: str = "",
    limit: int = 8,
    project: str = "",
    **_: Any,
) -> str:
    svc = _memory_service()
    return svc.handle_tool_call(
        "butler_recall",
        {
            "scope": scope,
            "query": query,
            "limit": limit,
            "project": project,
        },
    )


def register_memory_tools(register_fn) -> None:
    """Register memory tools into the Butler tool registry."""
    register_fn(
        name="butler_remember",
        description=(
            "写入 Butler 分层记忆：owner_profile=用户偏好(全局); "
            "project_notes=当前项目 MEMORY.md; owner_experience=跨项目经验。"
        ),
        schema=_REMEMBER_SCHEMA,
        handler=tool_butler_remember,
        toolset="memory",
    )
    register_fn(
        name="butler_recall",
        description="检索 Owner profile 全文，或按关键词搜索 experience(FTS，不含临时会话回声)。",
        schema=_RECALL_SCHEMA,
        handler=tool_butler_recall,
        toolset="memory",
    )


__all__ = [
    "register_memory_tools",
    "tool_butler_remember",
    "tool_butler_recall",
]
