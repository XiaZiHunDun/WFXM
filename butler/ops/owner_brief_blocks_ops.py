"""Owner brief overnight jobs best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def list_overnight_jobs_rows_safe(project_name: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Return ``(rows, error)`` where ``error`` is ``runtime_disabled`` or ``unavailable``."""

    def _runtime_enabled() -> bool:
        from butler.runtime.service import runtime_enabled

        return bool(runtime_enabled())

    enabled = safe_best_effort(
        _runtime_enabled,
        label="owner_brief.runtime_enabled",
        default=None,
    )
    if enabled is False:
        return None, "runtime_disabled"
    if enabled is not True:
        return None, "unavailable"

    def _run() -> list[dict[str, Any]]:
        from butler.runtime.service import list_jobs_status

        rows = list_jobs_status(project_name)
        if not isinstance(rows, list):
            raise ValueError("jobs status must be a list")
        return rows

    result = safe_best_effort(
        _run,
        label="owner_brief.overnight_jobs",
        default=None,
    )
    if isinstance(result, list):
        return result, None
    return None, "unavailable"
