"""Bot loop guard best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_bot_loop_suppressed_event_safe(*, chat_id: str, sender_id: str, count: int) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            f"wx:{chat_id}",
            "bot_loop_suppressed",
            {"sender": sender_id, "count": count},
        )

    safe_best_effort(_run, label="bot_loop_guard.suppressed_event", default=None)
