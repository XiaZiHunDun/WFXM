"""Best-effort helpers for owner feedback (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_owner_feedback_pmf_safe(*, session_key: str, trigger: str) -> None:
    def _run() -> None:
        from butler.ops.owner_pmf_metrics import record_owner_feedback_pmf

        record_owner_feedback_pmf(session_key=session_key, trigger=trigger)

    safe_best_effort(_run, label="owner_feedback.pmf", default=None)
