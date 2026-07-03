"""Recall layer access telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_experience_access_safe(experience_store: object, row_ids: list[int]) -> None:
    def _run() -> None:
        experience_store.record_access(row_ids)

    safe_best_effort(_run, label="recall_layers.record_access", default=None)
