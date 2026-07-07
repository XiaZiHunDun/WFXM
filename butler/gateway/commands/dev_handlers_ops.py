"""Dev slash command best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def resolve_project_from_orchestrator_safe(
    orchestrator: Any,
    *,
    session_key: str,
) -> Any:
    sk = str(session_key or "").strip()

    def _run() -> Any:
        if sk:
            return orchestrator.project_manager.get_current(session_key=sk)
        return orchestrator.project_manager.active_project

    return safe_best_effort(
        _run,
        label="dev_handlers.resolve_orchestrator",
        default=None,
    )


def resolve_project_from_handler_singleton_safe(*, session_key: str) -> Any:
    sk = str(session_key or "").strip()

    def _run() -> Any:
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = getattr(ButlerMessageHandler, "_instance", None)
        if handler and hasattr(handler, "_orchestrator"):
            pm = handler._orchestrator.project_manager
            if sk:
                return pm.get_current(session_key=sk)
            return pm.active_project
        return None

    return safe_best_effort(
        _run,
        label="dev_handlers.resolve_handler_singleton",
        default=None,
    )


def resolve_project_from_manager_safe(*, session_key: str) -> Any:
    sk = str(session_key or "").strip()

    def _run() -> Any:
        from butler.project.manager import ProjectManager

        pm = ProjectManager()
        if sk:
            return pm.get_current(session_key=sk)
        return pm.active_project

    return safe_best_effort(
        _run,
        label="dev_handlers.resolve_project_manager",
        default=None,
    )


def get_orchestrator_safe() -> Any:
    def _run() -> Any:
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = getattr(ButlerMessageHandler, "_instance", None)
        if handler and hasattr(handler, "_orchestrator"):
            return handler._orchestrator
        return None

    return safe_best_effort(
        _run,
        label="dev_handlers.get_orchestrator",
        default=None,
    )


def format_runtime_jobs_line_safe(jobs_path: Any) -> str | None:
    def _run() -> str | None:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(jobs_path.read_text(encoding="utf-8")) or {}
        jobs = data.get("jobs", [])
        active = sum(1 for j in jobs if j.get("enabled", True))
        if jobs:
            return f"⏰ 定时任务: {active} 个活跃 / {len(jobs)} 总计"
        return None

    return safe_best_effort(
        _run,
        label="dev_handlers.runtime_jobs_summary",
        default=None,
    )
