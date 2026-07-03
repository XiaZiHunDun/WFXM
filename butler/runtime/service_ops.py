"""Runtime service best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def record_job_outcome_safe(
    project_name: str,
    job_id: str,
    *,
    success: bool,
    audit_path: str,
) -> None:
    def _run() -> None:
        from butler.runtime.failure_tracker import record_job_outcome

        record_job_outcome(
            project_name,
            job_id,
            success=success,
            audit_path=audit_path,
        )

    safe_best_effort(_run, label="runtime_service.job_outcome", default=None)


def record_experiment_ledger_safe(
    workspace: Path,
    job_id: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.experiments.ledger import maybe_record_from_job_result

        row = maybe_record_from_job_result(workspace, job_id, result)
        return row if isinstance(row, dict) else {}

    payload = safe_best_effort(
        _run,
        label="runtime_service.experiment_ledger",
        default=None,
    )
    return payload if isinstance(payload, dict) and payload else None


def drain_push_queue_safe(*, max_items: int = 2) -> None:
    def _run() -> None:
        from butler.runtime.push_queue import drain_push_queue

        drain_push_queue(max_items=max_items)

    safe_best_effort(_run, label="runtime_service.push_queue_drain", default=None)
