"""Session-scoped metrics for gateway completion pushes (/诊断)."""

from __future__ import annotations


def record_completion_push_sent(*, session_key: str = "") -> None:
    from butler.ops.runtime_metrics import inc

    inc("gateway_completion_push", labels={"outcome": "sent"}, session_key=session_key)


def record_completion_push_failed(*, session_key: str = "") -> None:
    from butler.ops.runtime_metrics import inc

    inc("gateway_completion_push", labels={"outcome": "failed"}, session_key=session_key)


def record_completion_push_enqueued(*, session_key: str = "") -> None:
    from butler.ops.runtime_metrics import inc

    inc("gateway_completion_push", labels={"outcome": "enqueued"}, session_key=session_key)


def reset_completion_telemetry(session_key: str | None = None) -> None:
    from butler.ops.runtime_metrics import reset_counters_named, reset_session

    if session_key is None:
        reset_counters_named("gateway_completion_push")
        return
    reset_session(session_key)


def completion_push_stats(session_key: str = "") -> dict[str, int]:
    from butler.ops.runtime_metrics import counter_value

    return {
        "sent": counter_value(
            "gateway_completion_push",
            labels={"outcome": "sent"},
            session_key=session_key,
        ),
        "failed": counter_value(
            "gateway_completion_push",
            labels={"outcome": "failed"},
            session_key=session_key,
        ),
        "enqueued": counter_value(
            "gateway_completion_push",
            labels={"outcome": "enqueued"},
            session_key=session_key,
        ),
    }


def push_queue_pending_count(*, chat_id: str = "") -> int:
    """Count queued rows (best-effort; optional chat_id filter)."""
    try:
        from butler.runtime.push_queue import count_pending_pushes

        return count_pending_pushes(chat_id=chat_id or None)
    except Exception:
        return 0
