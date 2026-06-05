"""Layering seam for gateway side-effects (R1-3 fix).

The v4 architecture puts ``butler/core/`` below ``butler/gateway/`` in the
dependency graph. Three core modules
(``context_compressor``, ``compaction_task``, ``compaction_steer_bridge``)
historically reached upward into gateway at runtime to:

  - invoke named in-process hooks (``butler.gateway.hooks.invoke_hook``)
  - emit thread-item events
    (``butler.gateway.item_events.context_compaction_item`` /
    ``emit_thread_item``)
  - pop urgent inbound items
    (``butler.gateway.message_queue.pop_urgent_inbound``)

That coupling meant CLI / Loop unit tests could not run without gateway being
importable. This module defines an :class:`EventsSink` Protocol that gateway
implements; core modules call the convenience shims below instead of touching
gateway directly.

The default sink is no-op (:class:`NullEventsSink`); the gateway side installs
a real implementation at runtime via :func:`set_events_sink`. Tests that
want to assert behaviour can swap in custom sinks the same way.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UrgentInbound:
    """Minimal DTO returned by :meth:`EventsSink.pop_urgent_inbound`.

    Mirrors the only field the core caller uses (``text``) so the core layer
    does not need to import gateway's ``QueuedInbound`` type.
    """

    text: str


@runtime_checkable
class EventsSink(Protocol):
    """Protocol implemented by the gateway side.

    Core only sees this contract; gateway registers an implementation at
    runtime. Adding a new side-effect that core needs = add a method here
    + a corresponding gateway implementation.
    """

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]: ...

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
    ) -> None: ...

    def pop_urgent_inbound(self, session_key: str) -> UrgentInbound | None: ...


class NullEventsSink:
    """No-op sink used when no gateway is wired (CLI / unit tests)."""

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]:
        return []

    def emit_context_compaction(self, **kwargs: Any) -> None:
        return None

    def pop_urgent_inbound(self, session_key: str) -> UrgentInbound | None:
        return None


_SINK: EventsSink = NullEventsSink()


def set_events_sink(sink: EventsSink | None) -> None:
    """Install the gateway-side implementation. ``None`` resets to no-op."""
    global _SINK
    _SINK = sink if sink is not None else NullEventsSink()


def get_events_sink() -> EventsSink:
    """Return the currently registered sink (never ``None``; defaults to no-op)."""
    return _SINK


# ── Convenience shims used by core modules ─────────────────────────────────


def invoke_hook(name: str, **kwargs: Any) -> list[Any]:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        return _SINK.invoke_hook(name, **kwargs)
    except Exception as exc:  # noqa: BLE001 — best-effort, never break the caller
        logger.debug("events_sink.invoke_hook skipped: %s", exc)
        return []


def emit_context_compaction(
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
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        _SINK.emit_context_compaction(
            phase=phase,
            thread_id=thread_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=messages_before,
            messages_after=messages_after,
            source=source,
            remote=remote,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("events_sink.emit_context_compaction skipped: %s", exc)


def pop_urgent_inbound(session_key: str) -> UrgentInbound | None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        return _SINK.pop_urgent_inbound(session_key)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("events_sink.pop_urgent_inbound skipped: %s", exc)
        return None


__all__ = [
    "EventsSink",
    "NullEventsSink",
    "UrgentInbound",
    "emit_context_compaction",
    "get_events_sink",
    "invoke_hook",
    "pop_urgent_inbound",
    "set_events_sink",
]
