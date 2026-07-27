"""Human gate workflow best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def auto_resume_workflow_safe(session_key: str, workflow_name: str) -> str | None:
    def _run() -> str:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            raise ValueError("orchestrator unavailable")
        pm = orch.project_manager
        proj = pm.get_current(session_key=session_key)
        if proj is None:
            raise ValueError("project unavailable")
        from butler.workflows.runner import run_workflow_for_project

        reply = run_workflow_for_project(
            proj,
            workflow_name,
            session_key=session_key,
            orchestrator=orch,
        )
        if not reply:
            raise ValueError("empty workflow reply")
        return str(reply)

    result = safe_best_effort(
        _run,
        label="human_gate.auto_resume",
        default=None,
    )
    return str(result) if isinstance(result, str) else None


def workflow_auto_resume_reply_safe(
    session_key: str,
    workflow_name: str,
    step_id: str,
    *,
    enabled: bool,
    resume_fn: Callable[[str, str], str | None],
    confirmed_hint_fn: Callable[..., str],
) -> str | None:
    if not enabled:
        return None

    def _run() -> str:
        resume_reply = resume_fn(session_key, workflow_name)
        if not resume_reply:
            raise ValueError("no resume reply")
        head = confirmed_hint_fn(
            workflow=workflow_name,
            auto_resumed=True,
            step_id=step_id,
        )
        return f"{head}\n\n{resume_reply}"

    result = safe_best_effort(
        _run,
        label="human_gate.workflow_auto_resume",
        default=None,
    )
    return str(result) if isinstance(result, str) else None
