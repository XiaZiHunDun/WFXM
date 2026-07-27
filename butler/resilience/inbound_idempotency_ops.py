"""Inbound idempotency telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def inc_inbound_idempotency_reserve_safe(session_key: str) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc("inbound_idempotency_reserve", session_key=session_key)

    safe_best_effort(_run, label="inbound_idempotency.reserve_metric", default=None)


def record_duplicate_skip_telemetry_safe(
    session_key: str,
    *,
    reason: str,
    external_id: str = "",
    preview: str = "",
) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc
        from butler.core.session_transcript import record_generic_event

        inc(
            "inbound_duplicate_skip",
            labels={"reason": str(reason or "?")[:24]},
            session_key=session_key,
        )
        record_generic_event(
            session_key,
            "inbound_duplicate_skip",
            {
                "reason": reason,
                "external_id": (external_id or "")[:64],
                "preview": (preview or "")[:120],
            },
        )

    safe_best_effort(_run, label="inbound_idempotency.duplicate_skip", default=None)
