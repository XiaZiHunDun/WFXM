"""Best-effort forwarding shims for the events sink (P0-A)."""

from __future__ import annotations

from typing import Any, cast

from butler.contracts.events import UrgentInbound
from butler.contracts.sink_registry import get_events_sink
from butler.core.best_effort import safe_best_effort


def invoke_hook_safe(name: str, **kwargs: Any) -> list[Any]:
    def _run() -> list[Any]:
        hooked = get_events_sink().invoke_hook(name, **kwargs)
        return cast(list[Any], hooked)

    result = safe_best_effort(_run, label="events_sink.invoke_hook", default=[])
    return result if isinstance(result, list) else []


def emit_context_compaction_safe(
    *,
    phase: str,
    thread_id: str = "",
    tokens_before: int = 0,
    tokens_after: int = 0,
    messages_before: int = 0,
    messages_after: int = 0,
    source: str = "context",
    remote: bool = False,
) -> None:
    def _run() -> None:
        get_events_sink().emit_context_compaction(
            phase=phase,
            thread_id=thread_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=messages_before,
            messages_after=messages_after,
            source=source,
            remote=remote,
        )

    safe_best_effort(_run, label="events_sink.emit_context_compaction", default=None)


def pop_urgent_inbound_safe(session_key: str) -> UrgentInbound | None:
    def _run() -> UrgentInbound | None:
        return get_events_sink().pop_urgent_inbound(session_key)

    return safe_best_effort(_run, label="events_sink.pop_urgent_inbound", default=None)
