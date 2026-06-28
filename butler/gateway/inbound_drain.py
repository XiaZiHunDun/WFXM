"""Post-turn inbound queue drain (ENG-3 — extracted from message_handler)."""

from __future__ import annotations

import logging
import time as _time
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class InboundDrainHost(Protocol):
    def handle_message(
        self,
        text: str,
        *,
        session_key: str | None = None,
        platform: str = "unknown",
        external_id: str | None = None,
    ) -> str: ...

    @property
    def _session_registry(self) -> Any: ...

    def _queue_push_via_bridge(self) -> bool: ...


def drain_queued_inbound(
    handler: InboundDrainHost,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
    primary_reply: str = "",
) -> str:
    from butler.gateway.message_queue import (
        message_queue_enabled,
        newest_enqueued_at,
        pop_all_merged,
        pop_next,
    )
    from butler.gateway.queue_settings import collect_debounce_ms, get_queue_mode

    if not message_queue_enabled():
        return ""

    mode = get_queue_mode(session_key)
    parts: list[str] = []

    if mode == "collect":
        debounce_s = collect_debounce_ms(session_key) / 1000.0
        if debounce_s > 0:
            last_ts = newest_enqueued_at(session_key)
            if last_ts > 0:
                elapsed = _time.monotonic() - last_ts
                if elapsed < debounce_s:
                    _time.sleep(debounce_s - elapsed)
        item = pop_all_merged(session_key)
        if item is not None and not handler._session_registry.is_session_active(session_key):
            logger.info(
                "Gateway drain collect session=%s preview=%r",
                session_key,
                item.text[:80],
            )
            part = handler.handle_message(
                item.text,
                session_key=session_key,
                platform=item.platform or platform,
                external_id=item.external_id or external_id,
            )
            if part:
                parts.append(part)
    else:
        try:
            from butler.env_parse import int_env

            max_drain = int_env("BUTLER_GATEWAY_QUEUE_DRAIN_PER_TURN", 1, min=0)
        except ValueError:
            max_drain = 1
        if mode == "followup":
            try:
                from butler.env_parse import int_env

                max_drain = max(
                    max_drain,
                    int_env("BUTLER_GATEWAY_QUEUE_DRAIN_FOLLOWUP", 1, min=0),
                )
            except ValueError:
                pass
        for _ in range(max_drain):
            item = pop_next(session_key)
            if item is None:
                break
            if handler._session_registry.is_session_active(session_key):
                break
            logger.info(
                "Gateway drain queued session=%s priority=%s preview=%r",
                session_key,
                item.priority,
                item.text[:60],
            )
            part = handler.handle_message(
                item.text,
                session_key=session_key,
                platform=item.platform or platform,
                external_id=item.external_id or external_id,
            )
            if part:
                parts.append(part)

    if not parts:
        return ""
    combined = "\n\n---\n\n".join(parts) if len(parts) > 1 else parts[0]
    if handler._queue_push_via_bridge() and primary_reply.strip():
        from butler.gateway.outbound_bridge import get_current_bridge

        br = get_current_bridge()
        if br is not None:
            br.schedule_supplementary_reply(combined, kind="queued")
            return ""
    return combined


__all__ = ["InboundDrainHost", "drain_queued_inbound"]
