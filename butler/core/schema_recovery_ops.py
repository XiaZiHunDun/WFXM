"""Best-effort helpers for schema recovery telemetry (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_schema_recovery_event_safe() -> None:
    def _run() -> None:
        from butler.ops.retry_buckets import record_recovery_event

        record_recovery_event("schema_recovery")

    safe_best_effort(_run, label="schema_recovery.retry_bucket", default=None)
