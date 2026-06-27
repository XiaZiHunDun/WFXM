"""Gateway implementation of :class:`butler.contracts.events.EventsSink`."""

from __future__ import annotations

from typing import Any


class TranscriptEventsSink:
    """Forward events to ``butler.core.session_transcript`` (file SSOT)."""

    def record_generic_event(
        self,
        session_key: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(session_key, event_type, data)

    def record_tool_action(
        self,
        *,
        session_key: str,
        tool_name: str,
        args_preview: str = "",
        source: str = "",
    ) -> None:
        from butler.core.session_transcript import record_tool_action

        record_tool_action(
            session_key,
            tool_name=tool_name,
            args_preview=args_preview,
            source=source,
        )


def register_gateway_events_sink() -> None:
    from butler.contracts.sink_registry import set_events_sink

    set_events_sink(TranscriptEventsSink())


__all__ = ["TranscriptEventsSink", "register_gateway_events_sink"]
