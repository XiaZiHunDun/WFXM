"""Lightweight async event bus for decoupling Butler components.

Events:
- agent.started / agent.completed / agent.failed
- tool.called / tool.failed
- memory.updated / memory.pending_approval
- task.progress / task.approval_needed
- provider.failed / provider.recovered

Usage:
    from butler.core.event_bus import event_bus

    # Subscribe
    @event_bus.on("agent.completed")
    async def handle_completion(data):
        print(f"Agent done: {data}")

    # Publish
    await event_bus.emit("agent.completed", {"task_id": "abc", "success": True})
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBus:
    """Lightweight async pub/sub event bus."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._once_handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: list[tuple[str, dict]] = []
        self._max_history = 100

    def on(self, event: str, handler: EventHandler | None = None):
        """Subscribe to an event. Can be used as decorator."""
        if handler is not None:
            self._handlers[event].append(handler)
            return handler

        def decorator(fn: EventHandler) -> EventHandler:
            self._handlers[event].append(fn)
            return fn
        return decorator

    def once(self, event: str, handler: EventHandler) -> None:
        """Subscribe to an event, auto-unsubscribe after first call."""
        self._once_handlers[event].append(handler)

    def off(self, event: str, handler: EventHandler) -> None:
        """Unsubscribe from an event."""
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
        if handler in self._once_handlers[event]:
            self._once_handlers[event].remove(handler)

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event to all subscribers."""
        data = data or {}

        self._history.append((event, data))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        handlers = list(self._handlers.get(event, []))
        once_handlers = list(self._once_handlers.get(event, []))
        self._once_handlers[event].clear()

        all_handlers = handlers + once_handlers

        # Also notify wildcard subscribers
        all_handlers.extend(self._handlers.get("*", []))

        for handler in all_handlers:
            try:
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Event handler error for '{event}': {e}")

    def emit_sync(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Fire-and-forget emit from sync code (creates background task)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event, data))
        except RuntimeError:
            # No event loop running — log and skip
            logger.debug(f"Event '{event}' dropped (no event loop): {data}")

    def get_history(self, event: str | None = None, limit: int = 20) -> list[tuple[str, dict]]:
        """Get recent event history."""
        if event:
            filtered = [(e, d) for e, d in self._history if e == event]
            return filtered[-limit:]
        return self._history[-limit:]

    def clear(self) -> None:
        """Remove all handlers and history."""
        self._handlers.clear()
        self._once_handlers.clear()
        self._history.clear()

    def handler_count(self, event: str | None = None) -> int:
        """Count registered handlers."""
        if event:
            return len(self._handlers.get(event, [])) + len(self._once_handlers.get(event, []))
        return sum(len(v) for v in self._handlers.values()) + sum(len(v) for v in self._once_handlers.values())


# Module-level singleton
event_bus = EventBus()
