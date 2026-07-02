"""Registry handlers for ``butler_remember`` / ``butler_recall``."""

from __future__ import annotations

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
            "enum": [
                "experience",
                "profile",
                "project",
                "coding",
                "transcript",
                "observation",
                "hybrid",
            ],
            "default": "experience",
            "description": (
                "experience=跨项目; profile=画像; project=MEMORY; "
                "coding=L3/L4 编码经验; transcript=会话 transcript FTS; "
                "observation=workspace 工具观察(opt-in); "
                "hybrid=experience+project+coding 归一化合并(opt-in)"
            ),
        },
        "query": {"type": "string", "description": "FTS 检索词；profile 可留空"},
        "limit": {"type": "integer", "default": 8},
        "offset": {"type": "integer", "default": 0, "description": "transcript 滚动偏移"},
        "project": {"type": "string", "description": "可选项目名过滤"},
        "mode": {
            "type": "string",
            "enum": ["full", "index", "fetch", "timeline"],
            "default": "full",
            "description": "full=全文结果; index=仅索引; fetch=按 ids 拉全文; timeline=锚点时间线",
        },
        "ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "mode=fetch 时的 chunk_id 列表，如 experience:42",
        },
        "anchor_id": {
            "type": "string",
            "description": "mode=timeline 的锚点 chunk_id",
        },
        "depth": {"type": "integer", "default": 5, "description": "timeline 前后条数"},
    },
    "required": [],
}


def _memory_service():
    from butler.execution_context import get_current_orchestrator
    from butler.memory.facade import ButlerMemoryService

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
    except Exception as exc:
        logger.debug("memory service skipped: %s", exc)
    svc.initialize(session_id=session_key or "tool")
    if orch is not None:
        if getattr(orch, "butler_memory", None) is not None:
            svc._butler_global = orch.butler_memory
        pmem = getattr(orch, "_project_memory", None)
        if pmem is not None:
            svc._project_memory = pmem
            svc._project_root = getattr(pmem, "project_dir", None)
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
    mode: str = "full",
    ids: list | None = None,
    anchor_id: str = "",
    depth: int = 5,
    **_: Any,
) -> str:
    svc = _memory_service()
    payload: dict[str, Any] = {
        "scope": scope,
        "query": query,
        "limit": limit,
        "project": project,
        "mode": mode,
        "anchor_id": anchor_id,
        "depth": depth,
    }
    if ids is not None:
        payload["ids"] = ids
    return svc.handle_tool_call("butler_recall", payload)


_METRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "enum": ["summary", "session", "benchmark"],
            "default": "summary",
            "description": "summary=聚合指标; session=当前会话; benchmark=运行 7 项基准测试",
        },
        "session_id": {
            "type": "string",
            "description": "detail=session 时指定会话 ID",
        },
    },
    "required": [],
}


def tool_memory_metrics(
    detail: str = "summary",
    session_id: str = "",
    **_: Any,
) -> str:
    import json

    if detail == "benchmark":
        from butler.memory.memory_benchmark import run_benchmarks

        report = run_benchmarks()
        return json.dumps(report.summary(), ensure_ascii=False)

    from butler.memory.memory_metrics import get_collector

    collector = get_collector()
    if detail == "session":
        return json.dumps(
            collector.get_session_metrics(session_id),
            ensure_ascii=False,
        )
    return json.dumps(
        collector.get_aggregate().to_dict(),
        ensure_ascii=False,
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
        description=(
            "检索记忆：mode=full 全文；index 仅索引(~50tok/条)；"
            "fetch 按 ids 拉全文；timeline 锚点时间线。"
        ),
        schema=_RECALL_SCHEMA,
        handler=tool_butler_recall,
        toolset="memory",
    )
    register_fn(
        name="memory_metrics",
        description=(
            "记忆效果度量：summary=聚合统计; session=当前会话指标; "
            "benchmark=运行 7 项标准基准测试 (MB1-MB7)"
        ),
        schema=_METRICS_SCHEMA,
        handler=tool_memory_metrics,
        toolset="memory",
    )


__all__ = [
    "register_memory_tools",
    "tool_butler_remember",
    "tool_butler_recall",
    "tool_memory_metrics",
]
