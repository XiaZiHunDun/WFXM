"""Best-effort transcript export helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.session_transcript_ops import load_tail_rows_safe


def load_transcript_export_rows(path: Path, *, limit: int) -> list[dict[str, Any]] | None:
    result = load_tail_rows_safe(path, max_lines=limit)
    return result if isinstance(result, list) else None


def list_recent_tasks_safe(session_key: str, *, limit: int = 10) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]]:
        from butler.runtime.task_store import list_recent_tasks

        tasks = list_recent_tasks(session_key, limit=limit)
        return tasks if isinstance(tasks, list) else []

    result = safe_best_effort(
        _run,
        label="transcript_export.recent_tasks",
        default=None,
    )
    return result if isinstance(result, list) else None


def get_last_report_safe(session_key: str) -> Any | None:
    def _run() -> Any:
        from butler.report import get_last_report

        return get_last_report(session_key)

    return safe_best_effort(
        _run,
        label="transcript_export.last_report",
        default=None,
    )


def resolve_export_workspace_safe(session_key: str = "") -> Path | None:
    def _run() -> Path | None:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        sk = str(session_key or get_current_session_key() or "").strip()
        proj = pm.get_current(session_key=sk)
        if proj is None:
            return None
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="transcript_export.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
