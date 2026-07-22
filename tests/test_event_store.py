"""Unit tests for EventStore."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from butler.core.event_store import EventStore, StoredEvent, create_default_event_store


class TestEventStore:
    @pytest.fixture
    def event_store(self, tmp_path: Path):
        db_path = tmp_path / "test_events.db"
        return EventStore(db_path)

    @pytest.fixture
    def sample_event(self):
        return StoredEvent(
            event_id="evt-001",
            event_type="TEST_EVENT",
            payload={"key": "value", "number": 42},
            session_key="test-session",
            timestamp=1234567890.123,
        )

    def test_store_and_query(self, event_store: EventStore, sample_event: StoredEvent):
        event_store.store(sample_event)
        events = event_store.query_by_session("test-session")
        assert len(events) == 1
        assert events[0].event_id == "evt-001"
        assert events[0].payload == {"key": "value", "number": 42}

    def test_store_batch(self, event_store: EventStore):
        events = [
            StoredEvent(
                event_id=f"evt-{i:03d}",
                event_type="BATCH_EVENT",
                payload={"index": i},
                session_key="batch-session",
                timestamp=1234567890.0 + i,
            )
            for i in range(5)
        ]
        event_store.store_batch(events)
        result = event_store.query_by_session("batch-session")
        assert len(result) == 5

    def test_query_by_type(self, event_store: EventStore):
        event_store.store(
            StoredEvent(
                event_id="evt-type-1",
                event_type="TYPE_A",
                payload={},
                session_key="s1",
                timestamp=1234567890.0,
            )
        )
        event_store.store(
            StoredEvent(
                event_id="evt-type-2",
                event_type="TYPE_B",
                payload={},
                session_key="s1",
                timestamp=1234567890.1,
            )
        )
        result = event_store.query_by_type("TYPE_A")
        assert len(result) == 1
        assert result[0].event_type == "TYPE_A"

    def test_query_recent(self, event_store: EventStore):
        for i in range(10):
            event_store.store(
                StoredEvent(
                    event_id=f"evt-{i:03d}",
                    event_type="RECENT_EVENT",
                    payload={"i": i},
                    session_key="recent-session",
                    timestamp=1234567890.0 + i,
                )
            )
        result = event_store.query_recent(limit=3)
        assert len(result) == 3
        assert result[0].payload["i"] == 9

    def test_replay(self, event_store: EventStore):
        events = []
        for i in range(3):
            evt = StoredEvent(
                event_id=f"evt-{i:03d}",
                event_type="REPLAY_EVENT",
                payload={"step": i},
                session_key="replay-session",
                timestamp=1234567890.0 + i,
            )
            event_store.store(evt)
            events.append(evt)

        replayed = list(event_store.replay(session_key="replay-session"))
        assert len(replayed) == 3
        assert replayed[0].payload["step"] == 0
        assert replayed[1].payload["step"] == 1
        assert replayed[2].payload["step"] == 2

    def test_delete_old(self, event_store: EventStore):
        old_time = 1000000000.0
        recent_time = 2000000000.0

        event_store.store(
            StoredEvent(
                event_id="evt-old",
                event_type="DELETE_TEST",
                payload={},
                session_key="delete-session",
                timestamp=old_time,
            )
        )
        event_store.store(
            StoredEvent(
                event_id="evt-recent",
                event_type="DELETE_TEST",
                payload={},
                session_key="delete-session",
                timestamp=recent_time,
            )
        )

        deleted = event_store.delete_old(older_than_days=1)
        assert deleted == 1
        remaining = event_store.query_by_session("delete-session")
        assert len(remaining) == 1
        assert remaining[0].event_id == "evt-recent"

    def test_count(self, event_store: EventStore):
        for i in range(5):
            event_store.store(
                StoredEvent(
                    event_id=f"evt-count-{i}",
                    event_type="COUNT_EVENT",
                    payload={},
                    session_key="count-session",
                    timestamp=1234567890.0 + i,
                )
            )
        assert event_store.count() == 5

    def test_count_by_type(self, event_store: EventStore):
        for i in range(3):
            event_store.store(
                StoredEvent(
                    event_id=f"evt-type-a-{i}",
                    event_type="TYPE_A",
                    payload={},
                    session_key="count-type-session",
                    timestamp=1234567890.0 + i,
                )
            )
        for i in range(2):
            event_store.store(
                StoredEvent(
                    event_id=f"evt-type-b-{i}",
                    event_type="TYPE_B",
                    payload={},
                    session_key="count-type-session",
                    timestamp=1234567890.0 + i,
                )
            )
        counts = event_store.count_by_type()
        assert counts.get("TYPE_A") == 3
        assert counts.get("TYPE_B") == 2

    def test_close(self, event_store: EventStore):
        event_store.store(
            StoredEvent(
                event_id="evt-close",
                event_type="CLOSE_TEST",
                payload={},
                session_key="close-session",
                timestamp=1234567890.0,
            )
        )
        event_store.close()
        assert event_store._conn is None

    def test_create_default_event_store(self):
        store = create_default_event_store()
        assert store is not None
        assert "events" in str(store._db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])