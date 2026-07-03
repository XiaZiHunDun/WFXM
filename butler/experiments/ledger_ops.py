"""Experiment ledger best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def resolve_project_name_for_workspace_safe(workspace: Path) -> str:
    def _run() -> str:
        from butler.project.manager import get_project_manager

        ws = Path(workspace).expanduser().resolve()
        for project in get_project_manager().list_projects():
            if Path(project.workspace).resolve() == ws:
                return str(project.name)
        return ""

    result = safe_best_effort(
        _run,
        label="experiments_ledger.project_name",
        default="",
    )
    return str(result or "")


def apply_outcome_hooks_safe(
    workspace: Path,
    *,
    project: str,
    job_id: str,
    metric_name: str,
    metric_value: float,
    hypothesis: str,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.experiments.outcomes import (
            maybe_resolve_previous_pending,
            maybe_store_pending_from_metric,
        )

        ws = Path(workspace).expanduser().resolve()
        subj = str(job_id or metric_name)
        maybe_resolve_previous_pending(
            ws,
            project=project,
            subject=subj,
            outcome_value=str(metric_value),
        )
        pending_row = maybe_store_pending_from_metric(
            ws,
            project=project,
            job_id=job_id,
            metric_name=str(metric_name),
            metric_value=float(metric_value),
            hypothesis=hypothesis,
        )
        if pending_row:
            return {"outcome_pending_id": pending_row.get("row_id")}
        return {}

    result = safe_best_effort(
        _run,
        label="experiments_ledger.outcome_hooks",
        default={},
    )
    return result if isinstance(result, dict) else {}


def apply_crash_guard_safe(
    workspace: Path,
    *,
    hypothesis: str,
    job_id: str,
    status: str,
) -> dict[str, Any]:
    if str(status or "") != "crash":
        return {}

    def _run() -> dict[str, Any]:
        from butler.experiments.crash_guard import (
            consecutive_crash_count,
            should_block_experiment_run,
        )

        ws = Path(workspace).expanduser().resolve()
        out: dict[str, Any] = {}
        streak = consecutive_crash_count(ws, hypothesis=hypothesis, job_id=job_id)
        out["crash_streak"] = streak
        blocked, reason = should_block_experiment_run(
            ws,
            hypothesis=hypothesis,
            job_id=job_id,
        )
        if blocked:
            out["experiment_blocked"] = True
            out["block_reason"] = reason
        return out

    result = safe_best_effort(
        _run,
        label="experiments_ledger.crash_guard",
        default={},
    )
    return result if isinstance(result, dict) else {}
