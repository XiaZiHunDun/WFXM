"""Tool-pair repair telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_tool_pair_repair_event_safe(session_key: str, count: int) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            str(session_key or ""),
            "tool_pair_repair",
            {"count": int(count)},
        )

    safe_best_effort(_run, label="tool_pair_repair.record_event", default=None)
