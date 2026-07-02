"""Best-effort helpers for memory recall paths (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def stack_tags_for_project_safe(project_id: str) -> frozenset[str]:
    def _run() -> frozenset[str]:
        from butler.memory.memory_scope import stack_tags_for_project

        return stack_tags_for_project(project_id)

    result = safe_best_effort(
        _run,
        label="recall.stack_tags",
        default=frozenset(),
    )
    return result if isinstance(result, frozenset) else frozenset()


def resolve_observation_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_current()
        if proj is not None and getattr(proj, "workspace", None):
            return Path(proj.workspace).expanduser().resolve()
        return None

    result = safe_best_effort(
        _run,
        label="recall.observation_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def record_scope_retrieval_safe(
    payload: dict[str, Any],
    *,
    session_key: str = "",
) -> None:
    def _run() -> None:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval

        sk = str(session_key or "").strip() or str(get_current_session_key() or "")
        if sk:
            record_last_retrieval(sk, payload)

    safe_best_effort(_run, label="recall.telemetry", default=None)
