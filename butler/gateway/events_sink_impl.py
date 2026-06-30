"""Concrete :class:`EventsSink` that delegates to the existing gateway modules.

Registered into ``butler.contracts.sink_registry`` at module-import time.
Core never imports this directly — it only sees the contracts Protocol.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.contracts.events import UrgentInbound
from butler.contracts.sink_registry import set_events_sink

logger = logging.getLogger(__name__)


class GatewayEventsSink:
    """Adapter from contracts :class:`EventsSink` to gateway facilities."""

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

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]:
        from butler.gateway.hooks import invoke_hook as _invoke_hook

        return cast(list[Any], _invoke_hook(name, **kwargs))

    def emit_context_compaction(
        self,
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
        from butler.gateway.item_events import (
            context_compaction_item,
            emit_thread_item,
        )

        emit_thread_item(
            context_compaction_item(
                phase=phase,
                thread_id=thread_id,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                messages_before=messages_before,
                messages_after=messages_after,
                source=source,
                remote=remote,
            )
        )

    def pop_urgent_inbound(self, session_key: str) -> UrgentInbound | None:
        from butler.gateway.message_queue import pop_urgent_inbound as _pop

        item = _pop(session_key)
        if item is None:
            return None
        return UrgentInbound(text=item.text)


def install_gateway_events_sink() -> GatewayEventsSink:
    """Install the gateway sink and return it (idempotent)."""
    sink = GatewayEventsSink()
    set_events_sink(sink)
    return sink


install_gateway_events_sink()


__all__ = ["GatewayEventsSink", "install_gateway_events_sink"]
