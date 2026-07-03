"""Compaction steer/inbound bridge best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def pop_compaction_urgent_inbound_text_safe(session_key: str) -> str | None:
    def _run() -> str:
        from butler.core.events_sink import pop_urgent_inbound

        item = pop_urgent_inbound(session_key)
        if item is None or not str(getattr(item, "text", "") or "").strip():
            raise ValueError("no urgent inbound")
        return str(item.text).strip()

    result = safe_best_effort(
        _run,
        label="compaction_steer_bridge.urgent_inbound",
        default=None,
    )
    text = str(result or "").strip()
    return text or None


def pop_compaction_steer_text_safe(session_key: str) -> str | None:
    def _run() -> str:
        from butler.core.steer import drain_steer, pending_steer

        steer_text = pending_steer(session_key)
        if not str(steer_text or "").strip():
            raise ValueError("no pending steer")
        drain_steer(session_key)
        return str(steer_text).strip()

    result = safe_best_effort(
        _run,
        label="compaction_steer_bridge.steer",
        default=None,
    )
    text = str(result or "").strip()
    return text or None
