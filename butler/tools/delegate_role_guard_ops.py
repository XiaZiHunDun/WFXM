"""Delegate role guard context lookup best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def turn_user_text_from_epoch_safe(session_key: str) -> str | None:
    def _run() -> str:
        from butler.core.session_epoch import last_user_query_in_epoch

        query = last_user_query_in_epoch(session_key)
        if not str(query or "").strip():
            raise ValueError("no epoch user query")
        return str(query).strip()

    result = safe_best_effort(
        _run,
        label="delegate_role_guard.epoch_query",
        default=None,
    )
    text = str(result or "").strip()
    return text or None


def is_lead_project_turn_safe() -> bool | None:
    """Return lead-turn bool, or ``None`` when the check path failed."""

    def _run() -> bool:
        from butler.execution_context import get_current_orchestrator
        from butler.project.lead import is_lead_project

        orch = get_current_orchestrator()
        if orch is None:
            return False
        proj = orch.project_manager.get_current()
        if proj is None:
            return False
        name = str(getattr(proj, "name", "") or "")
        return bool(name) and is_lead_project(name, project=proj)

    result = safe_best_effort(
        _run,
        label="delegate_role_guard.lead_turn",
        default=None,
    )
    return bool(result) if isinstance(result, bool) else None
