"""Event replay optimization for event sourcing.

Provides:
- ReplayStrategy: Different strategies for replaying events
- ReplayOptimizer: Optimize event replay with snapshot support
- Snapshot: Point-in-time state snapshots
- EventTimeTravel: Navigate event history

These utilities improve event sourcing performance by:
1. Supporting snapshots to avoid replaying from the beginning
2. Providing incremental replay strategies
3. Enabling time-travel debugging
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Generic, TypeVar

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_types import DomainEvent

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Snapshot(Generic[T]):
    """Point-in-time snapshot of aggregate state.

    Used to optimize event replay by starting from a snapshot
    instead of replaying all events from the beginning.

    Attributes:
        state: The aggregate state at the snapshot point.
        version: Event version at snapshot time.
        timestamp: When the snapshot was taken.
        event_count: Number of events replayed to reach this state.
    """

    state: T
    version: int
    timestamp: datetime
    event_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "event_count": self.event_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Snapshot[T]":
        return cls(
            state=data["state"],
            version=data["version"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_count=data["event_count"],
            metadata=data.get("metadata", {}),
        )


class ReplayStrategy:
    """Strategy for replaying events.

    Provides different replay modes:
    - FULL: Replay all events from the beginning
    - INCREMENTAL: Start from a snapshot and replay new events
    - SNAPSHOT_ONLY: Use snapshot only, no replay
    """

    FULL = "full"
    INCREMENTAL = "incremental"
    SNAPSHOT_ONLY = "snapshot_only"


class ReplayOptimizer(Generic[T]):
    """Optimize event replay with snapshot support.

    Reduces replay cost by periodically saving snapshots and
    using them as starting points for state reconstruction.

    Example:
        optimizer = ReplayOptimizer(
            initial_state=initial,
            apply_event=apply_fn,
            snapshot_interval=100,
        )
        state = optimizer.replay(events)
    """

    def __init__(
        self,
        initial_state: T,
        apply_event: Callable[[T, DomainEvent], T],
        snapshot_interval: int = 100,
        max_snapshots: int = 5,
    ) -> None:
        self._initial_state = initial_state
        self._apply_event = apply_event
        self._snapshot_interval = snapshot_interval
        self._max_snapshots = max_snapshots
        self._snapshots: list[Snapshot[T]] = []

    def replay(
        self,
        events: Iterable[DomainEvent],
        strategy: str = ReplayStrategy.INCREMENTAL,
    ) -> T:
        """Replay events with the specified strategy.

        Args:
            events: Events to replay.
            strategy: Replay strategy to use.

        Returns:
            The reconstructed state.
        """
        events_list = sorted(events, key=lambda e: e.timestamp)

        if strategy == ReplayStrategy.SNAPSHOT_ONLY:
            if self._snapshots:
                return self._snapshots[-1].state
            return self._initial_state

        # Find the best starting point
        start_state = self._initial_state
        start_idx = 0

        if strategy == ReplayStrategy.INCREMENTAL and self._snapshots:
            best_snapshot = self._find_best_snapshot(len(events_list))
            if best_snapshot is not None:
                start_state = best_snapshot.state
                start_idx = best_snapshot.event_count
                logger.debug(
                    "Starting from snapshot at event %d", start_idx
                )

        # Replay remaining events
        state = start_state
        for i, event in enumerate(events_list[start_idx:], start=start_idx):
            state = self._apply_event(state, event)

            # Take periodic snapshots
            if (i + 1) % self._snapshot_interval == 0:
                self._take_snapshot(state, i + 1, event.timestamp)

        # Take final snapshot
        if events_list:
            self._take_snapshot(state, len(events_list), events_list[-1].timestamp)

        return state

    def _find_best_snapshot(
        self, total_events: int
    ) -> Snapshot[T] | None:
        """Find the best snapshot to start from."""
        best = None
        for snapshot in self._snapshots:
            if snapshot.event_count <= total_events:
                if best is None or snapshot.event_count > best.event_count:
                    best = snapshot
        return best

    def _take_snapshot(
        self, state: T, event_count: int, timestamp: datetime
    ) -> None:
        """Take a snapshot at the current state."""
        snapshot = Snapshot(
            state=state,
            version=len(self._snapshots),
            timestamp=timestamp,
            event_count=event_count,
        )
        self._snapshots.append(snapshot)

        # Keep only the latest N snapshots
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def clear_snapshots(self) -> None:
        self._snapshots.clear()


class EventTimeTravel(Generic[T]):
    """Navigate event history for debugging and inspection.

    Allows stepping forward and backward through event history,
    useful for debugging and auditing.

    Example:
        tt = EventTimeTravel(events, initial_state, apply_fn)
        state = tt.seek_to(50)  # State at event 50
        state = tt.backward(10)  # Go back 10 events
        state = tt.forward(5)   # Go forward 5 events
    """

    def __init__(
        self,
        events: list[DomainEvent],
        initial_state: T,
        apply_event: Callable[[T, DomainEvent], T],
    ) -> None:
        self._events = sorted(events, key=lambda e: e.timestamp)
        self._initial_state = initial_state
        self._apply_event = apply_event
        self._current_idx = 0
        self._state_history: list[T] = [initial_state]

    @property
    def current_state(self) -> T:
        """Get the current state."""
        return self._state_history[self._current_idx]

    @property
    def current_index(self) -> int:
        """Get the current event index."""
        return self._current_idx

    @property
    def total_events(self) -> int:
        """Get the total number of events."""
        return len(self._events)

    def seek_to(self, index: int) -> T:
        """Seek to a specific event index.

        Args:
            index: Target event index (0-based).

        Returns:
            The state at that index.
        """
        if index < 0 or index > len(self._events):
            raise IndexError(
                f"Index {index} out of range [0, {len(self._events)}]"
            )

        # Expand history if needed
        while len(self._state_history) <= index:
            next_idx = len(self._state_history)
            if next_idx <= len(self._events):
                new_state = self._apply_event(
                    self._state_history[-1],
                    self._events[next_idx - 1],
                )
                self._state_history.append(new_state)

        self._current_idx = index
        return self._state_history[self._current_idx]

    def forward(self, steps: int = 1) -> T:
        """Move forward N events."""
        return self.seek_to(self._current_idx + steps)

    def backward(self, steps: int = 1) -> T:
        """Move backward N events."""
        return self.seek_to(max(0, self._current_idx - steps))

    def reset(self) -> T:
        """Reset to initial state."""
        self._current_idx = 0
        return self._state_history[0]

    def get_event(self, index: int) -> DomainEvent:
        """Get the event at a specific index."""
        return self._events[index]

    def get_event_range(
        self, start: int, end: int
    ) -> list[DomainEvent]:
        """Get events in a range."""
        return self._events[start:end]


class EventQueryOptimizer:
    """Optimize event queries with indexing and caching.

    Provides fast lookups for common query patterns:
    - Events by session
    - Events by type
    - Events in time range
    """

    def __init__(self, events: list[DomainEvent]) -> None:
        self._events = events
        self._by_session: dict[str, list[int]] = {}
        self._by_type: dict[str, list[int]] = {}
        self._timestamps: list[datetime] = []
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build lookup indexes."""
        for i, event in enumerate(self._events):
            self._by_session.setdefault(event.session_key, []).append(i)
            self._by_type.setdefault(event.event_type, []).append(i)
            self._timestamps.append(event.timestamp)

    def get_by_session(self, session_key: str) -> list[DomainEvent]:
        """Get all events for a session."""
        indices = self._by_session.get(session_key, [])
        return [self._events[i] for i in indices]

    def get_by_type(self, event_type: str) -> list[DomainEvent]:
        """Get all events of a specific type."""
        indices = self._by_type.get(event_type, [])
        return [self._events[i] for i in indices]

    def get_by_time_range(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[DomainEvent]:
        """Get events within a time range."""
        results: list[DomainEvent] = []
        for event in self._events:
            if start is not None and event.timestamp < start:
                continue
            if end is not None and event.timestamp > end:
                continue
            results.append(event)
        return results

    def count_by_type(self) -> dict[str, int]:
        """Count events by type."""
        return {k: len(v) for k, v in self._by_type.items()}

    def count_by_session(self) -> dict[str, int]:
        """Count events by session."""
        return {k: len(v) for k, v in self._by_session.items()}


__all__ = [
    "Snapshot",
    "ReplayStrategy",
    "ReplayOptimizer",
    "EventTimeTravel",
    "EventQueryOptimizer",
]
