"""Best-effort helpers for ``ButlerMemoryService`` (P0-A / P2-F)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def emit_write_metric(scope: str, success: bool, *, content: str = "") -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector
        from butler.memory.metrics_persist import flush_memory_metrics

        get_collector().on_write(scope, success, content=content)
        flush_memory_metrics()

    safe_best_effort(_run, label="memory.facade.write_metric", default=None)


def emit_recall_metric(
    scope: str,
    query: str,
    count: int,
    *,
    hit_texts: list[str] | None = None,
) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector
        from butler.memory.metrics_persist import flush_memory_metrics

        get_collector().on_recall(scope, query, count, hit_texts=hit_texts)
        flush_memory_metrics()

    safe_best_effort(_run, label="memory.facade.recall_metric", default=None)


def resolve_active_project_name() -> str:
    def _from_orchestrator() -> str:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch is not None else None
        if pm is None:
            return ""
        if hasattr(pm, "resolve_active_project_name"):
            return str(pm.resolve_active_project_name() or "").strip()
        cur = pm.get_current() if hasattr(pm, "get_current") else None
        if cur is not None:
            return str(getattr(cur, "name", "") or "").strip()
        return str(getattr(pm, "current_project", "") or "").strip()

    name = safe_best_effort(
        _from_orchestrator,
        label="memory.facade.active_project_orchestrator",
        default=None,
    )
    if name:
        return name

    def _from_manager() -> str:
        from butler.project.manager import get_project_manager

        pm = get_project_manager()
        if hasattr(pm, "resolve_active_project_name"):
            return str(pm.resolve_active_project_name() or "").strip()
        cur = pm.get_current() if hasattr(pm, "get_current") else None
        if cur is not None:
            return str(getattr(cur, "name", "") or "").strip()
        return str(getattr(pm, "current_project", "") or "").strip()

    return safe_best_effort(
        _from_manager,
        label="memory.facade.active_project_manager",
        default="",
    ) or ""


def discover_project_root() -> Path | None:
    raw = __import__("os").environ.get("BUTLER_PROJECT_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    def _run() -> Path | None:
        from butler.project.manager import get_project_manager

        pm = get_project_manager()
        cur = pm.get_current()
        if cur:
            return Path(cur.workspace).resolve()
        return None

    return safe_best_effort(
        _run,
        label="memory.facade.project_root_discovery",
        default=None,
    )


def manager_current_project() -> str:
    def _run() -> str:
        from butler.project.manager import get_project_manager

        return get_project_manager().current_project or ""

    return safe_best_effort(
        _run,
        label="memory.facade.manager_current_project",
        default="",
    ) or ""


def butler_home_configured() -> bool:
    def _run() -> bool:
        from butler.config import get_butler_home

        return bool(get_butler_home())

    result = safe_best_effort(
        _run,
        label="memory.facade.butler_home_check",
        default=None,
    )
    return True if result is None else bool(result)


def close_butler_memory(memory: Any) -> None:
    safe_best_effort(
        memory.close,
        label="memory.facade.close_on_tenant_switch",
        default=None,
    )


def refresh_project_facts(project_memory: Any) -> None:
    safe_best_effort(
        project_memory.refresh_facts,
        label="memory.facade.refresh_project_facts",
        default=None,
    )


def record_recall_telemetry(payload: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval

        record_last_retrieval(get_current_session_key() or "", payload)

    safe_best_effort(_run, label="memory.facade.recall_telemetry", default=None)


def strip_private_tags_safe(content: str) -> tuple[str, bool] | None:
    def _run() -> tuple[str, bool]:
        from butler.memory.private_tags import strip_private_tags

        return strip_private_tags(content)

    return safe_best_effort(
        _run,
        label="memory.facade.strip_private_tags",
        default=None,
    )


def owner_write_approval_result(args: dict[str, Any]) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.memory.owner_write_pending import (
            queue_owner_write,
            scope_requires_write_approval,
        )

        scope = str(args.get("scope") or "")
        action = str(args.get("action", "append") or "append").strip().lower()
        content = str(args.get("content") or "").strip()
        if not scope_requires_write_approval(scope, action):
            return {}
        item = queue_owner_write(
            scope=scope,
            content=content,
            action=action,
            old_content=str(args.get("old_content", "") or "").strip(),
            category=str(args.get("category", "") or "general"),
            section=str(args.get("section", "Notes") or "Notes"),
        )
        return {
            "ok": True,
            "scope": scope,
            "classification": "pending",
            "pending_id": item.get("id"),
            "action": action,
            "hint": "已进入所有者记忆待审；Owner 可用 /记忆待审 与 /批准记忆",
        }

    result = safe_best_effort(
        _run,
        label="memory.facade.owner_write_approval",
        default=None,
    )
    if result is None:
        return None
    if not result:
        return None
    return result


def prefetch_global_context(butler_global: Any, *, root: Path | None) -> str:
    def _run() -> str:
        current = manager_current_project()
        if not current and root is not None:
            current = root.name
        return butler_global.get_system_context(current)

    return safe_best_effort(
        _run,
        label="memory.facade.prefetch_global",
        default="",
    ) or ""


def prefetch_project_context(project_memory: Any) -> str:
    return safe_best_effort(
        lambda: project_memory.get_full_context(max_lines=30),
        label="memory.facade.prefetch_project",
        default="",
    ) or ""


def load_project_memory(root: Path) -> Any | None:
    def _run() -> Any:
        from butler.memory import ProjectMemory

        pm = ProjectMemory(root)
        refresh_project_facts(pm)
        return pm

    return safe_best_effort(
        _run,
        label="memory.facade.load_project_memory",
        default=None,
    )


def dispatch_memory_tool(service: Any, tool_name: str, args: dict[str, Any]) -> str:
    import json

    if tool_name == "butler_remember":
        return service._remember(args)
    if tool_name == "butler_recall":
        return service._recall(args)
    return json.dumps({"ok": False, "error": f"unknown tool {tool_name}"})


def run_tool_call_safe(fn: Callable[[], str], *, label: str) -> str:
    import json

    try:
        return fn()
    except Exception as exc:
        logger.error("ButlerMemoryProvider tool failure [%s]: %s", label, exc)
        return json.dumps({"ok": False, "error": str(exc)})


__all__ = [
    "butler_home_configured",
    "close_butler_memory",
    "discover_project_root",
    "dispatch_memory_tool",
    "emit_recall_metric",
    "emit_write_metric",
    "load_project_memory",
    "manager_current_project",
    "owner_write_approval_result",
    "prefetch_global_context",
    "prefetch_project_context",
    "record_recall_telemetry",
    "refresh_project_facts",
    "resolve_active_project_name",
    "run_tool_call_safe",
    "strip_private_tags_safe",
]
