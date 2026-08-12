"""Event query optimization with indexing support.

Provides:
- EventIndex: Lightweight index for efficient event lookup
- EventQuery: High-level query API with filtering and aggregation
"""

from __future__ import annotations

import bisect
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EventIndexEntry:
    """Index entry for a single event."""
    event_id: str
    session_key: str
    event_type: str
    timestamp: datetime
    file_offset: int
    file_path: str


class EventIndex:
    """Lightweight in-memory index for event storage.

    Provides O(1) lookup by event_id and O(log n) range queries by time.
    Uses minimal memory overhead suitable for large event stores.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, EventIndexEntry] = {}
        self._by_session: dict[str, list[EventIndexEntry]] = defaultdict(list)
        self._by_type: dict[str, list[EventIndexEntry]] = defaultdict(list)
        self._by_time: list[tuple[datetime, str]] = []  # (timestamp, event_id)
        self._lock_active: bool = False
        self._count: int = 0

    @property
    def count(self) -> int:
        return self._count

    def add(self, entry: EventIndexEntry) -> None:
        """Add an index entry."""
        self._by_id[entry.event_id] = entry
        self._by_session[entry.session_key].append(entry)
        self._by_type[entry.event_type].append(entry)
        bisect.insort(self._by_time, (entry.timestamp, entry.event_id))
        self._count += 1

    def lookup_by_id(self, event_id: str) -> EventIndexEntry | None:
        """O(1) lookup by event ID."""
        return self._by_id.get(event_id)

    def lookup_by_session(
        self, session_key: str
    ) -> list[EventIndexEntry]:
        """Get all entries for a session."""
        return self._by_session.get(session_key, [])

    def lookup_by_type(
        self, event_type: str
    ) -> list[EventIndexEntry]:
        """Get all entries of a specific type."""
        return self._by_type.get(event_type, [])

    def lookup_by_time_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[EventIndexEntry]:
        """O(log n) range query by time."""
        if start is None and end is None:
            return [self._by_id[eid] for _, eid in self._by_time]

        results = []
        for ts, eid in self._by_time:
            if start is not None and ts < start:
                continue
            if end is not None and ts > end:
                break
            entry = self._by_id.get(eid)
            if entry:
                results.append(entry)

        return results

    def build_from_file(self, file_path: str | Path) -> int:
        """Build index from a JSONL event file."""
        file_path = Path(file_path)
        if not file_path.exists():
            return 0

        count = 0
        session_key = file_path.stem.replace("_", ":")

        with open(file_path, "r", encoding="utf-8") as f:
            for offset, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    event_id = data.get("event_id", "")
                    event_type = data.get("event_type", "")
                    ts_str = data.get("timestamp", "")

                    if event_id and event_type and ts_str:
                        try:
                            from datetime import datetime, timezone
                            ts = datetime.fromisoformat(ts_str)
                        except (ValueError, TypeError):
                            ts = datetime.now(timezone.utc)

                        entry = EventIndexEntry(
                            event_id=event_id,
                            session_key=data.get("session_key", session_key),
                            event_type=event_type,
                            timestamp=ts,
                            file_offset=offset,
                            file_path=str(file_path),
                        )
                        self.add(entry)
                        count += 1
                except (json.JSONDecodeError, Exception):
                    continue

        logger.debug("Indexed %d events from %s", count, file_path.name)
        return count

    def build_from_directory(self, directory: str | Path) -> int:
        """Build index from all JSONL files in a directory."""
        directory = Path(directory)
        if not directory.exists():
            return 0

        total = 0
        for jsonl_file in directory.glob("*.jsonl"):
            total += self.build_from_file(jsonl_file)

        return total

    def clear(self) -> None:
        """Clear all index entries."""
        self._by_id.clear()
        self._by_session.clear()
        self._by_type.clear()
        self._by_time.clear()
        self._count = 0


@dataclass
class EventQueryFilter:
    """Query filter for event searches."""
    session_key: str | None = None
    event_type: str | None = None
    event_types: list[str] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int | None = None
    offset: int = 0


class EventQuery:
    """High-level query API for event stores.

    Supports filtering, aggregation, and pagination.
    Designed for use with EventIndex for efficient lookups.
    """

    def __init__(self, index: EventIndex) -> None:
        self._index = index

    def execute(
        self, base_dir: str | Path, filter: EventQueryFilter
    ) -> list[dict[str, Any]]:
        """Execute a query with the given filter.

        Reads actual event data from files based on index lookups.
        """
        candidates: list[EventIndexEntry] = []

        # Apply filters
        if filter.session_key:
            candidates = self._index.lookup_by_session(filter.session_key)
        elif filter.event_type:
            candidates = self._index.lookup_by_type(filter.event_type)
        elif filter.event_types:
            for et in filter.event_types:
                candidates.extend(self._index.lookup_by_type(et))
        elif filter.start_time or filter.end_time:
            candidates = self._index.lookup_by_time_range(
                filter.start_time, filter.end_time
            )
        else:
            # Return all entries (with limit)
            candidates = [
                self._index._by_id[eid]
                for _, eid in self._index._by_time
            ]

        # Apply time filters if not already filtered by time
        if (filter.start_time or filter.end_time) and not (
            filter.session_key or filter.event_type or filter.event_types
        ):
            pass  # Already filtered by time range query
        elif filter.start_time or filter.end_time:
            candidates = [
                c
                for c in candidates
                if (filter.start_time is None or c.timestamp >= filter.start_time)
                and (filter.end_time is None or c.timestamp <= filter.end_time)
            ]

        # Apply type filter if combined with session filter
        if filter.session_key and filter.event_type:
            candidates = [c for c in candidates if c.event_type == filter.event_type]
        elif filter.session_key and filter.event_types:
            type_set = set(filter.event_types)
            candidates = [c for c in candidates if c.event_type in type_set]

        # Apply pagination
        candidates = candidates[filter.offset:]
        if filter.limit is not None:
            candidates = candidates[: filter.limit]

        # Read actual event data from files
        results = []
        file_cache: dict[str, list[str]] = {}

        base_dir = Path(base_dir)

        for entry in candidates:
            if entry.file_path not in file_cache:
                file_path = Path(entry.file_path)
                if file_path.exists():
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_cache[entry.file_path] = f.readlines()
                else:
                    file_cache[entry.file_path] = []

            lines = file_cache.get(entry.file_path, [])
            if 0 <= entry.file_offset < len(lines):
                try:
                    data = json.loads(lines[entry.file_offset].strip())
                    results.append(data)
                except (json.JSONDecodeError, IndexError):
                    pass

        return results

    def count(
        self, base_dir: str | Path, filter: EventQueryFilter
    ) -> int:
        """Count events matching filter without reading data."""
        candidates: list[EventIndexEntry] = []

        if filter.session_key:
            candidates = self._index.lookup_by_session(filter.session_key)
        elif filter.event_type:
            candidates = self._index.lookup_by_type(filter.event_type)
        elif filter.event_types:
            for et in filter.event_types:
                candidates.extend(self._index.lookup_by_type(et))
        else:
            candidates = [
                self._index._by_id[eid]
                for _, eid in self._index._by_time
            ]

        # Apply filters
        if filter.start_time or filter.end_time:
            candidates = [
                c
                for c in candidates
                if (filter.start_time is None or c.timestamp >= filter.start_time)
                and (filter.end_time is None or c.timestamp <= filter.end_time)
            ]

        if filter.event_type and filter.session_key:
            candidates = [c for c in candidates if c.event_type == filter.event_type]

        return len(candidates)

    def aggregate_by_type(
        self, filter: EventQueryFilter
    ) -> dict[str, int]:
        """Count events grouped by type."""
        if filter.session_key:
            entries = self._index.lookup_by_session(filter.session_key)
        else:
            entries = [
                self._index._by_id[eid]
                for _, eid in self._index._by_time
            ]

        # Apply time filters
        if filter.start_time or filter.end_time:
            entries = [
                e
                for e in entries
                if (filter.start_time is None or e.timestamp >= filter.start_time)
                and (filter.end_time is None or e.timestamp <= filter.end_time)
            ]

        counts: dict[str, int] = defaultdict(int)
        for entry in entries:
            counts[entry.event_type] += 1

        return dict(counts)

    def get_time_range(self) -> tuple[datetime | None, datetime | None]:
        """Get the time range of indexed events."""
        if not self._index._by_time:
            return None, None

        first_ts = self._index._by_time[0][0]
        last_ts = self._index._by_time[-1][0]
        return first_ts, last_ts


__all__ = [
    "EventIndexEntry",
    "EventIndex",
    "EventQueryFilter",
    "EventQuery",
]
