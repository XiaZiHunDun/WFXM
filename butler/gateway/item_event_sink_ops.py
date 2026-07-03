"""Thread item event payload best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def serialize_thread_item_event_safe(event: Any) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        if not isinstance(payload, dict):
            raise ValueError("thread item payload must be a dict")
        return payload

    result = safe_best_effort(
        _run,
        label="item_event_sink.serialize",
        default=None,
    )
    return result if isinstance(result, dict) else None
