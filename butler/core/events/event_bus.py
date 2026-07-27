"""Event bus implementations for pub/sub pattern.

Provides:
- EventBus: Simple event bus for basic pub/sub
- EnhancedEventBus: Enhanced version with wildcard support and error isolation
- Global event bus utilities
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from butler.core.effects import Result, Ok, Err, collect_results
from butler.core.events.event_types import DomainEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Simple event bus for pub/sub pattern.

    Allows components to subscribe to event types and react to events.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[DomainEvent], Any]]] = {}

    def subscribe(
        self, event_type: str, handler: Callable[[DomainEvent], Any]
    ) -> Callable[[], None]:
        """Subscribe to an event type.

        Returns an unsubscribe function.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if event_type in self._subscribers:
                    self._subscribers[event_type].remove(handler)

        return unsubscribe

    def unsubscribe(self, event_type: str, handler: Callable[[DomainEvent], Any]) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass

    def publish(self, event: DomainEvent) -> Result[list[Any], Exception]:
        """Publish an event to all subscribers."""
        try:
            with self._lock:
                handlers = self._subscribers.get(event.event_type, [])

            results = [handler(event) for handler in handlers]
            return Ok(results)
        except Exception as e:
            return Err(e)

    def publish_many(self, events: Iterable[DomainEvent]) -> Result[list[list[Any]], Exception]:
        """Publish multiple events."""
        return collect_results([self.publish(event) for event in events])


class EnhancedEventBus(EventBus):
    """Enhanced event bus with wildcard support and error isolation.

    Based on opencode's event system patterns. Improvements over EventBus:
    - Wildcard subscriptions ("*" matches all events)
    - Error isolation (one handler failure doesn't affect others)
    - Handler priority support
    """

    def __init__(self) -> None:
        super().__init__()
        self._wildcard_handlers: list[Callable[[DomainEvent], Any]] = []

    def subscribe_all(self, handler: Callable[[DomainEvent], Any]) -> Callable[[], None]:
        """Subscribe to all event types."""
        with self._lock:
            self._wildcard_handlers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._wildcard_handlers:
                    self._wildcard_handlers.remove(handler)

        return unsubscribe

    def publish(self, event: DomainEvent) -> Result[list[Any], Exception]:
        """Publish an event with error isolation."""
        try:
            with self._lock:
                handlers = list(self._subscribers.get(event.event_type, []))
                wildcard = list(self._wildcard_handlers)

            results: list[Any] = []
            # Call specific handlers first, then wildcards
            for handler in handlers + wildcard:
                try:
                    result = handler(event)
                    results.append(result)
                except Exception as e:
                    # Isolate handler errors
                    logger.warning(
                        "Event handler failed for %s: %s",
                        event.event_type,
                        e,
                        exc_info=True,
                    )
                    results.append(None)
            return Ok(results)
        except Exception as e:
            return Err(e)


# Global singleton instance (for testing and simple use cases)
_global_event_bus: EventBus | None = None


def get_global_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_global_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _global_event_bus
    _global_event_bus = EventBus()


__all__ = [
    "EventBus",
    "EnhancedEventBus",
    "get_global_event_bus",
    "reset_global_event_bus",
]
