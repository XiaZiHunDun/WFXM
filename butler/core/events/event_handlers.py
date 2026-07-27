"""Event handlers for event sourcing and projections.

Provides:
- EventSourcingHandler: Replay events to reconstruct aggregate state
- Projector: Incrementally build read models from event streams
- EventBatch: Atomic batch for event publishing
- Scope: Resource lifecycle management
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Generic, TypeVar

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_bus import EventBus
from butler.core.events.event_store_protocol import EventStore
from butler.core.events.event_types import DomainEvent

T = TypeVar("T")


class EventSourcingHandler(Generic[T]):
    """Event sourcing handler for state reconstruction.

    Uses event replay to rebuild aggregate state from historical events.

    Example:
        def apply_event(state, event):
            match event.event_type:
                case "SESSION_START":
                    return SessionState(...)
                case "TOOL_ACTION":
                    return state.with_tool_action(...)
                case _:
                    return state

        handler = EventSourcingHandler(initial_state, apply_event)
        state = handler.replay(events)
    """

    def __init__(
        self,
        initial_state: T,
        apply_event: Callable[[T, DomainEvent], T],
    ) -> None:
        self._initial_state = initial_state
        self._apply_event = apply_event

    def replay(self, events: Iterable[DomainEvent]) -> T:
        """Replay events to reconstruct state."""
        state = self._initial_state
        for event in sorted(events, key=lambda e: e.timestamp):
            state = self._apply_event(state, event)
        return state

    def replay_from_store(self, store: EventStore, session_key: str) -> Result[T, Exception]:
        """Replay events from a store for a session."""
        result = store.get_events_for_session(session_key)
        if result.is_err():
            return result
        return Ok(self.replay(result.unwrap()))


class Projector(Generic[T]):
    """Event projector for building read models from event streams.

    Based on opencode's projector pattern. Subscribes to events from an EventBus
    and incrementally builds a read model. Unlike EventSourcingHandler (which
    replays all events from scratch), a Projector updates incrementally as
    events arrive.

    Example:
        def on_session_start(state, event):
            return state | {"active_sessions": state["active_sessions"] + 1}

        def on_tool_action(state, event):
            return state | {"tool_calls": state["tool_calls"] + 1}

        projector = Projector(
            initial_state={"active_sessions": 0, "tool_calls": 0},
            handlers={
                "SESSION_START": on_session_start,
                "TOOL_ACTION": on_tool_action,
            },
        )
        projector.attach(event_bus)
        # Now automatically updates as events arrive
        current_state = projector.state
    """

    def __init__(
        self,
        initial_state: T,
        handlers: dict[str, Callable[[T, DomainEvent], T]],
    ) -> None:
        self._state = initial_state
        self._handlers = handlers
        self._unsubscribe: Callable[[], None] | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> T:
        """Get the current projected state."""
        with self._lock:
            return self._state

    def handle(self, event: DomainEvent) -> None:
        """Handle a single event and update state."""
        handler = self._handlers.get(event.event_type)
        if handler is None:
            return
        with self._lock:
            self._state = handler(self._state, event)

    def attach(self, bus: EventBus) -> None:
        """Attach to an event bus, subscribing to all handler event types."""
        if self._unsubscribe is not None:
            self._unsubscribe()

        unsubs: list[Callable[[], None]] = []
        for event_type in self._handlers:
            unsub = bus.subscribe(event_type, self.handle)
            unsubs.append(unsub)

        def detach_all() -> None:
            for unsub in unsubs:
                unsub()

        self._unsubscribe = detach_all

    def detach(self) -> None:
        """Detach from the event bus."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def rebuild_from_store(self, store: EventStore, session_key: str) -> Result[T, Exception]:
        """Rebuild the projection from an event store."""
        result = store.get_events_for_session(session_key)
        if result.is_err():
            return result
        events = result.unwrap()
        with self._lock:
            self._state = self._state.__class__() if hasattr(self._state, "__class__") else self._state
        for event in sorted(events, key=lambda e: e.timestamp):
            self.handle(event)
        return Ok(self._state)


class EventBatch:
    """Atomic batch for event publishing.

    Based on opencode's State.batch pattern. Collects events and publishes
    them atomically — either all succeed or none are published.

    Example:
        with EventBatch(event_bus, event_store) as batch:
            batch.append(session_start_event)
            batch.append(tool_action_event)
            # All events published atomically on exit
    """

    def __init__(
        self,
        bus: EventBus | None = None,
        store: EventStore | None = None,
    ) -> None:
        self._bus = bus
        self._store = store
        self._events: list[DomainEvent] = []
        self._committed = False

    def append(self, event: DomainEvent) -> Result[None, RuntimeError]:
        """Add an event to the batch."""
        if self._committed:
            return Err(RuntimeError("Cannot append to a committed batch"))
        self._events.append(event)
        return Ok(None)

    def commit(self) -> Result[list[Any], Exception]:
        """Atomically publish all events.

        If a store is attached, events are persisted first.
        If any step fails, no events are published.
        """
        if self._committed:
            return Err(RuntimeError("Batch already committed"))
        self._committed = True

        if not self._events:
            return Ok([])

        # Persist to store first (if attached)
        if self._store is not None:
            result = self._store.append_batch(self._events)
            if result.is_err():
                return result

        # Publish to bus (if attached)
        if self._bus is not None:
            result = self._bus.publish_many(self._events)
            if result.is_err():
                return result
            return Ok(result.unwrap())

        return Ok([])

    def rollback(self) -> None:
        """Discard all pending events."""
        self._events.clear()
        self._committed = True

    def __enter__(self) -> "EventBatch":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.commit()

    @property
    def pending_count(self) -> int:
        """Number of pending events."""
        return len(self._events)


class Scope:
    """Resource scope for lifecycle management.

    Based on opencode's Scope pattern. Manages cleanup of resources
    (subscriptions, file handles, connections) with automatic disposal.

    Example:
        scope = Scope()

        unsub = event_bus.subscribe("SESSION_START", handler)
        scope.add_finalizer(unsub)

        # ... later, clean up all resources
        scope.close()
    """

    def __init__(self) -> None:
        self._finalizers: list[Callable[[], None]] = []
        self._closed = False
        self._lock = threading.RLock()

    def add_finalizer(self, finalizer: Callable[[], None]) -> None:
        """Add a cleanup function to be called on close."""
        with self._lock:
            if self._closed:
                finalizer()
                return
            self._finalizers.append(finalizer)

    def manage(self, disposable: Any) -> Any:
        """Manage a disposable resource (with close() or detach() method)."""
        finalizer = None
        if hasattr(disposable, "close"):
            finalizer = disposable.close
        elif hasattr(disposable, "detach"):
            finalizer = disposable.detach
        elif callable(disposable):
            finalizer = disposable

        if finalizer is not None:
            self.add_finalizer(finalizer)
        return disposable

    def fork(self) -> "Scope":
        """Create a child scope. Closing the parent also closes children."""
        child = Scope()

        def close_child() -> None:
            child.close()

        self.add_finalizer(close_child)
        return child

    def close(self) -> None:
        """Close the scope and run all finalizers in reverse order."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            finalizers = list(reversed(self._finalizers))
            self._finalizers.clear()

        for finalizer in finalizers:
            try:
                finalizer()
            except Exception:
                pass  # Suppress errors during cleanup

    @property
    def is_closed(self) -> bool:
        """Whether this scope has been closed."""
        return self._closed

    def __enter__(self) -> "Scope":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


__all__ = [
    "EventSourcingHandler",
    "Projector",
    "EventBatch",
    "Scope",
]
