"""Workflow runner best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def interpolate_var_pool_safe(var_pool: Any, text: str) -> str:
    def _run() -> str:
        return str(var_pool.interpolate(text))

    result = safe_best_effort(_run, label="workflow_runner.interpolate", default=text)
    return str(result if result is not None else text)


def record_plan_snapshot_safe(session_key: str, snap_json: str) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_plan_snapshot

        record_plan_snapshot(session_key, snap_json)

    safe_best_effort(_run, label="workflow_runner.plan_snapshot", default=None)


def record_workflow_step_safe(
    session_key: str,
    *,
    workflow: str,
    step_id: str,
    phase: str,
    step_index: int,
    step_total: int,
) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_workflow_step

        record_workflow_step(
            session_key,
            workflow=workflow,
            step_id=step_id,
            phase=phase,
            step_index=step_index,
            step_total=step_total,
        )

    safe_best_effort(_run, label="workflow_runner.record_step", default=None)


def write_workflow_step_checkpoint_safe(
    workspace: Path,
    workflow_name: str,
    *,
    step_id: str,
    completed_steps: list[str],
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.workflows.workflow_run_snapshot import write_workflow_step_checkpoint

        write_workflow_step_checkpoint(
            workspace,
            workflow_name,
            step_id=step_id,
            completed_steps=list(completed_steps),
            session_key=session_key,
        )

    safe_best_effort(_run, label="workflow_runner.step_checkpoint", default=None)


def project_workspace_safe(orch: Any, *, session_key: str = "") -> Any:
    def _run() -> Any:
        proj = orch.project_manager.get_current(session_key=session_key)
        if proj is None:
            return None
        return proj.workspace

    return safe_best_effort(_run, label="workflow_runner.project_workspace", default=None)


def save_workflow_pause_safe(
    *,
    workflow: str,
    step_id: str,
    session_key: str,
    execution_order: list[str],
) -> None:
    def _run() -> None:
        from butler.workflows.pause_state import WorkflowPauseState, save_workflow_pause

        save_workflow_pause(
            WorkflowPauseState(
                workflow=workflow,
                step_id=step_id,
                session_key=session_key,
                execution_order=list(execution_order),
                completed_steps=[],
            ),
        )

    safe_best_effort(_run, label="workflow_runner.save_pause", default=None)


def workflow_max_parallel_default_safe() -> int | None:
    def _run() -> int:
        from butler.core.meta_flags import workflow_max_parallel_default

        return int(workflow_max_parallel_default())

    return safe_best_effort(_run, label="workflow_runner.max_parallel", default=None)


def get_current_project_safe(orch: Any, *, session_key: str = "") -> Any | None:
    def _run() -> Any:
        return orch.project_manager.get_current(session_key=session_key)

    return safe_best_effort(_run, label="workflow_runner.current_project", default=None)


def write_workflow_run_snapshot_for_project_safe(
    orch: Any,
    workflow_name: str,
    graph: Any,
    *,
    session_key: str,
) -> None:
    proj = get_current_project_safe(orch, session_key=session_key)
    if proj is None:
        return
    write_workflow_run_snapshot_safe(
        Path(proj.workspace),
        workflow_name,
        graph,
        session_key=session_key,
    )
    workspace: Path,
    workflow_name: str,
    graph: Any,
    *,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.workflows.workflow_run_snapshot import write_workflow_run_snapshot

        write_workflow_run_snapshot(
            workspace,
            workflow_name,
            graph,
            session_key=session_key,
        )

    safe_best_effort(_run, label="workflow_runner.run_snapshot", default=None)


def run_workflow_handlers_safe(
    handlers: list[Any],
    *,
    workflow_name: str,
    session_key: str,
    workspace: Path | None,
    success: bool,
    summary: str,
    step_outcomes: dict[str, str],
) -> None:
    def _run() -> None:
        from butler.workflows.callbacks import WorkflowCallbackContext, run_workflow_handlers

        run_workflow_handlers(
            handlers,
            event="workflow_finished",
            ctx=WorkflowCallbackContext(
                workflow_name=workflow_name,
                session_key=session_key,
                workspace=workspace,
                success=success,
                summary=summary,
                step_outcomes=step_outcomes,
            ),
        )

    safe_best_effort(_run, label="workflow_runner.handlers", default=None)


def append_pending_outcome_safe(
    workspace: Path,
    *,
    project: str,
    subject: str,
    hypothesis: str,
) -> None:
    def _run() -> None:
        from butler.experiments.outcomes import append_pending

        append_pending(
            workspace,
            project=project,
            subject=subject,
            hypothesis=hypothesis,
            source="workflow",
        )

    safe_best_effort(_run, label="workflow_runner.append_outcome", default=None)


def current_audit_session_key_safe(fallback: str = "workflow") -> str:
    def _run() -> str:
        from butler.execution_context import get_audit_session_key

        return str(get_audit_session_key(fallback=fallback) or "")

    result = safe_best_effort(_run, label="workflow_runner.audit_session_key", default="")
    return str(result or "")
