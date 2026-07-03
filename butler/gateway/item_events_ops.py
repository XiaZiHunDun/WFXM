"""Thread item event best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def record_thread_item_safe(event: Any) -> None:
    def _run() -> None:
        from butler.gateway.item_event_sink import record_thread_item

        record_thread_item(event)

    safe_best_effort(_run, label="item_events.record_thread_item", default=None)
