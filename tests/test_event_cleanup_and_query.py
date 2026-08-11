"""Tests for event cleanup and query optimization."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from butler.core.events import (
    EventArchiver,
    EventCleanupService,
    EventIndex,
    EventIndexEntry,
    EventQuery,
    EventQueryFilter,
    EventRetentionPolicy,
    FileEventStore,
    create_session_started,
    create_tool_called,
    create_tool_completed,
)


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def populated_store(temp_dir: Path) -> FileEventStore:
    """Create a file event store with test data."""
    store = FileEventStore(base_dir=temp_dir)

    session_id = "test-session-001"
    events = [
        create_session_started(session_id, project_path="/test"),
        create_tool_called(session_id, "read_file", "call-001"),
        create_tool_completed(session_id, "read_file", "call-001", duration_ms=50),
        create_tool_called(session_id, "write_file", "call-002"),
        create_tool_completed(session_id, "write_file", "call-002", duration_ms=30),
    ]
    store.append_batch(events)

    # Create old session (simulate old data)
    old_session = "old-session-001"
    old_events = [
        create_session_started(old_session),
        create_tool_called(old_session, "old_tool", "old-call-001"),
    ]
    store.append_batch(old_events)

    return store


class TestEventRetentionPolicy:
    """Test event retention policy configuration."""

    def test_default_values(self) -> None:
        """Test default policy values."""
        policy = EventRetentionPolicy()
        assert policy.max_age_days == 30
        assert policy.archive_after_days == 90
        assert policy.max_events_per_session == 10000
        assert policy.auto_cleanup is False

    def test_from_env(self) -> None:
        """Test creating policy from environment variables."""
        os.environ["BUTLER_EVENT_MAX_AGE_DAYS"] = "60"
        os.environ["BUTLER_EVENT_ARCHIVE_DAYS"] = "120"
        os.environ["BUTLER_EVENT_MAX_PER_SESSION"] = "5000"

        policy = EventRetentionPolicy.from_env()

        assert policy.max_age_days == 60
        assert policy.archive_after_days == 120
        assert policy.max_events_per_session == 5000

        # Cleanup
        del os.environ["BUTLER_EVENT_MAX_AGE_DAYS"]
        del os.environ["BUTLER_EVENT_ARCHIVE_DAYS"]
        del os.environ["BUTLER_EVENT_MAX_PER_SESSION"]

    def test_custom_values(self) -> None:
        """Test creating policy with custom values."""
        policy = EventRetentionPolicy(
            max_age_days=14,
            archive_after_days=30,
            max_events_per_session=1000,
            auto_cleanup=True,
        )

        assert policy.max_age_days == 14
        assert policy.archive_after_days == 30
        assert policy.auto_cleanup is True


class TestEventArchiver:
    """Test event archival functionality."""

    def test_archive_session(self, temp_dir: Path) -> None:
        """Test archiving a session's events."""
        import tempfile as tf
        import shutil

        archive_dir = Path(tf.mkdtemp())
        try:
            store = FileEventStore(base_dir=temp_dir)
            session_id = "test-archive-001"

            events = [
                create_session_started(session_id),
                create_tool_called(session_id, "tool1", "call-001"),
                create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
            ]
            store.append_batch(events)

            # Archive
            archiver = EventArchiver(base_dir=temp_dir, archive_dir=archive_dir)
            count = archiver.archive_session(session_id)

            assert count == 3

            # Verify active file is removed
            active_file = temp_dir / f"{session_id.replace(':', '_')}.jsonl"
            assert not active_file.exists()

            # Verify archive exists
            archives = archiver.list_archives()
            assert len(archives) == 1
            assert archives[0]["event_count"] == 3
        finally:
            shutil.rmtree(archive_dir, ignore_errors=True)

    def test_restore_session(self, temp_dir: Path) -> None:
        """Test restoring a session from archive."""
        import tempfile as tf
        import shutil

        archive_dir = Path(tf.mkdtemp())
        try:
            store = FileEventStore(base_dir=temp_dir)
            session_id = "test-restore-001"

            events = [
                create_session_started(session_id),
                create_tool_called(session_id, "tool1", "call-001"),
            ]
            store.append_batch(events)

            # Archive
            archiver = EventArchiver(base_dir=temp_dir, archive_dir=archive_dir)
            archiver.archive_session(session_id)

            # Restore
            restored = archiver.restore_session(session_id)
            assert restored == 2

            # Verify events are back
            result = store.get_events_for_session(session_id)
            assert result.is_ok()
            assert len(result.unwrap()) == 2
        finally:
            shutil.rmtree(archive_dir, ignore_errors=True)

    def test_list_archives(self, temp_dir: Path) -> None:
        """Test listing archives."""
        import tempfile as tf

        # Create unique archive directory
        archive_dir = Path(tf.mkdtemp())
        try:
            store = FileEventStore(base_dir=temp_dir)

            # Create and archive multiple sessions
            for i in range(3):
                session_id = f"archive-session-{i}"
                store.append(create_session_started(session_id))
                store.append(create_tool_called(session_id, f"tool{i}", f"call-{i}"))

            archiver = EventArchiver(base_dir=temp_dir, archive_dir=archive_dir)
            for i in range(3):
                archiver.archive_session(f"archive-session-{i}")

            archives = archiver.list_archives()
            assert len(archives) == 3
        finally:
            import shutil
            shutil.rmtree(archive_dir, ignore_errors=True)

    def test_get_archive_size(self, temp_dir: Path) -> None:
        """Test getting total archive size."""
        import tempfile as tf

        archive_dir = Path(tf.mkdtemp())
        try:
            store = FileEventStore(base_dir=temp_dir)
            session_id = "size-test"
            store.append(create_session_started(session_id))

            archiver = EventArchiver(base_dir=temp_dir, archive_dir=archive_dir)
            archiver.archive_session(session_id)

            size = archiver.get_archive_size()
            assert size > 0
        finally:
            import shutil
            shutil.rmtree(archive_dir, ignore_errors=True)


class TestEventCleanupService:
    """Test the cleanup service."""

    def test_cleanup_expired_sessions(self, temp_dir: Path) -> None:
        """Test cleaning up expired sessions."""
        store = FileEventStore(base_dir=temp_dir)

        # Create a session
        session_id = "cleanup-test"
        store.append(create_session_started(session_id))

        # Modify the file to make it "old"
        session_file = temp_dir / f"{session_id}.jsonl"
        old_time = (datetime.now() - timedelta(days=100)).timestamp()
        os.utime(session_file, (old_time, old_time))

        # Run cleanup
        service = EventCleanupService(
            base_dir=temp_dir,
            policy=EventRetentionPolicy(
                max_age_days=30,
                archive_after_days=60,
            ),
        )

        result = service.cleanup_expired_sessions(force=True)

        assert result["status"] == "completed"
        assert result["sessions_processed"] >= 1

    def test_check_session_size(self, temp_dir: Path) -> None:
        """Test checking session size."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "size-check"

        # Add many events
        for i in range(100):
            store.append(create_tool_called(session_id, f"tool{i}", f"call-{i}"))

        service = EventCleanupService(
            base_dir=temp_dir,
            policy=EventRetentionPolicy(max_events_per_session=50),
        )

        check = service.check_session_size(session_id)

        assert check["session"] == session_id
        assert check["event_count"] == 100
        assert check["needs_cleanup"] is True
        assert check["max_events"] == 50

    def test_cleanup_oversized_session(self, temp_dir: Path) -> None:
        """Test cleaning up an oversized session."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "oversized"

        # Add many events
        for i in range(200):
            store.append(create_tool_called(session_id, f"tool{i}", f"call-{i}"))

        service = EventCleanupService(
            base_dir=temp_dir,
            policy=EventRetentionPolicy(max_events_per_session=50),
        )

        result = service.cleanup_oversized_session(session_id)

        assert result["status"] == "completed"
        assert result["removed_events"] == 150
        assert result["kept_events"] == 50

    def test_get_storage_stats(self, temp_dir: Path) -> None:
        """Test getting storage statistics."""
        store = FileEventStore(base_dir=temp_dir)

        for i in range(5):
            session_id = f"stats-session-{i}"
            store.append(create_session_started(session_id))

        service = EventCleanupService(base_dir=temp_dir)
        stats = service.get_storage_stats()

        assert stats["active_sessions_count"] == 5
        assert stats["active_events_size_bytes"] > 0
        assert stats["policy"]["max_age_days"] == 30


class TestEventIndex:
    """Test the event indexing system."""

    def test_add_and_lookup_by_id(self) -> None:
        """Test adding entries and looking up by ID."""
        index = EventIndex()
        entry = EventIndexEntry(
            event_id="evt-001",
            session_key="session-001",
            event_type="TOOL_CALLED.1",
            timestamp=datetime.now(timezone.utc),
            file_offset=0,
            file_path="/test/file.jsonl",
        )

        index.add(entry)

        result = index.lookup_by_id("evt-001")
        assert result is not None
        assert result.event_id == "evt-001"
        assert result.event_type == "TOOL_CALLED.1"

    def test_lookup_by_session(self) -> None:
        """Test looking up entries by session."""
        index = EventIndex()

        for i in range(5):
            index.add(EventIndexEntry(
                event_id=f"evt-{i}",
                session_key="session-001",
                event_type="TOOL_CALLED.1",
                timestamp=datetime.now(timezone.utc),
                file_offset=i * 100,
                file_path="/test/file.jsonl",
            ))

        entries = index.lookup_by_session("session-001")
        assert len(entries) == 5

        empty = index.lookup_by_session("nonexistent")
        assert len(empty) == 0

    def test_lookup_by_type(self) -> None:
        """Test looking up entries by type."""
        index = EventIndex()

        index.add(EventIndexEntry(
            event_id="evt-1",
            session_key="session-001",
            event_type="TOOL_CALLED.1",
            timestamp=datetime.now(timezone.utc),
            file_offset=0,
            file_path="/test/file.jsonl",
        ))
        index.add(EventIndexEntry(
            event_id="evt-2",
            session_key="session-001",
            event_type="TOOL_COMPLETED.1",
            timestamp=datetime.now(timezone.utc),
            file_offset=100,
            file_path="/test/file.jsonl",
        ))

        called = index.lookup_by_type("TOOL_CALLED.1")
        assert len(called) == 1
        assert called[0].event_id == "evt-1"

        completed = index.lookup_by_type("TOOL_COMPLETED.1")
        assert len(completed) == 1

    def test_build_from_file(self, temp_dir: Path) -> None:
        """Test building index from a JSONL file."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-index"

        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
        ]
        store.append_batch(events)

        # Find the JSONL file
        jsonl_file = temp_dir / f"{session_id}.jsonl"
        assert jsonl_file.exists()

        # Build index
        index = EventIndex()
        count = index.build_from_file(jsonl_file)

        assert count == 3
        assert index.count == 3

        # Lookup by ID
        first_entry = index.lookup_by_id(events[0].event_id)
        assert first_entry is not None
        assert first_entry.event_type == "SESSION_STARTED.1"

    def test_build_from_directory(self, temp_dir: Path) -> None:
        """Test building index from all files in a directory."""
        store = FileEventStore(base_dir=temp_dir)

        # Create multiple sessions
        for i in range(3):
            session_id = f"dir-session-{i}"
            events = [
                create_session_started(session_id),
                create_tool_called(session_id, f"tool{i}", f"call-{i}"),
            ]
            store.append_batch(events)

        # Build index from directory
        index = EventIndex()
        count = index.build_from_directory(temp_dir)

        assert count == 6  # 2 events × 3 sessions


class TestEventQuery:
    """Test the event query API."""

    def test_execute_with_session_filter(self, temp_dir: Path) -> None:
        """Test querying with session filter."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "query-session"

        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
        ]
        store.append_batch(events)

        # Build index
        index = EventIndex()
        index.build_from_directory(temp_dir)

        # Query
        query = EventQuery(index)
        filter = EventQueryFilter(session_key=session_id)
        results = query.execute(temp_dir, filter)

        assert len(results) == 3
        assert results[0]["event_type"] == "SESSION_STARTED.1"

    def test_execute_with_type_filter(self, temp_dir: Path) -> None:
        """Test querying with event type filter."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "type-session"

        events = [
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
            create_tool_called(session_id, "tool2", "call-002"),
        ]
        store.append_batch(events)

        index = EventIndex()
        index.build_from_directory(temp_dir)

        query = EventQuery(index)
        filter = EventQueryFilter(
            session_key=session_id,
            event_type="TOOL_CALLED.1",
        )
        results = query.execute(temp_dir, filter)

        assert len(results) == 2
        for r in results:
            assert r["event_type"] == "TOOL_CALLED.1"

    def test_count(self, temp_dir: Path) -> None:
        """Test counting events."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "count-session"

        for i in range(10):
            store.append(create_tool_called(session_id, f"tool{i}", f"call-{i}"))

        index = EventIndex()
        index.build_from_directory(temp_dir)

        query = EventQuery(index)
        filter = EventQueryFilter(session_key=session_id)
        count = query.count(temp_dir, filter)

        assert count == 10

    def test_aggregate_by_type(self, temp_dir: Path) -> None:
        """Test aggregating events by type."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "agg-session"

        events = [
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
            create_tool_called(session_id, "tool2", "call-002"),
            create_tool_completed(session_id, "tool2", "call-002", duration_ms=30),
            create_tool_called(session_id, "tool3", "call-003"),
        ]
        store.append_batch(events)

        index = EventIndex()
        index.build_from_directory(temp_dir)

        query = EventQuery(index)
        filter = EventQueryFilter(session_key=session_id)
        aggregation = query.aggregate_by_type(filter)

        assert aggregation["TOOL_CALLED.1"] == 3
        assert aggregation["TOOL_COMPLETED.1"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
