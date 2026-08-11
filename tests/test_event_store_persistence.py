"""Integration tests for persistent event storage."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from butler.core.events import (
    FileEventStore,
    HybridEventStore,
    SessionStateProjector,
    create_session_started,
    create_tool_called,
    create_tool_completed,
    create_tool_failed,
)


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for event storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestFileEventStore:
    """Test the file-based event store."""

    def test_append_and_retrieve(self, temp_dir: Path) -> None:
        """Test basic append and retrieve operations."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-001"

        event = create_session_started(session_id, project_path="/test")
        result = store.append(event)
        assert result.is_ok()

        events_result = store.get_events_for_session(session_id)
        assert events_result.is_ok()
        events = events_result.unwrap()
        assert len(events) == 1
        assert events[0].event_type == "SESSION_STARTED.1"

    def test_append_batch(self, temp_dir: Path) -> None:
        """Test batch append operations."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-002"

        events = [
            create_tool_called(session_id, "read_file", "call-001"),
            create_tool_completed(session_id, "read_file", "call-001", duration_ms=50),
            create_tool_called(session_id, "web_search", "call-002"),
            create_tool_failed(
                session_id, "web_search", "call-002", "timeout", duration_ms=100
            ),
        ]

        result = store.append_batch(events)
        assert result.is_ok()

        events_result = store.get_events_for_session(session_id)
        assert events_result.is_ok()
        retrieved = events_result.unwrap()
        assert len(retrieved) == 4

    def test_get_events_by_type(self, temp_dir: Path) -> None:
        """Test filtering events by type."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-003"

        events = [
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
            create_tool_called(session_id, "tool2", "call-002"),
        ]
        store.append_batch(events)

        called_result = store.get_events_by_type(session_id, "TOOL_CALLED.1")
        assert called_result.is_ok()
        called_events = called_result.unwrap()
        assert len(called_events) == 2

    def test_persistence_across_instances(self, temp_dir: Path) -> None:
        """Test that events persist across different store instances."""
        store1 = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-004"

        event = create_session_started(session_id)
        store1.append(event)

        # Create new instance pointing to same directory
        store2 = FileEventStore(base_dir=temp_dir)
        events_result = store2.get_events_for_session(session_id)
        assert events_result.is_ok()
        events = events_result.unwrap()
        assert len(events) == 1
        assert events[0].event_id == event.event_id

    def test_clear_session(self, temp_dir: Path) -> None:
        """Test clearing a session's events."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-005"

        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "tool1", "call-001"),
        ]
        store.append_batch(events)

        # Verify events exist
        events_result = store.get_events_for_session(session_id)
        assert len(events_result.unwrap()) == 2

        # Clear session
        clear_result = store.clear_session(session_id)
        assert clear_result.is_ok()

        # Verify events are cleared
        events_result = store.get_events_for_session(session_id)
        assert len(events_result.unwrap()) == 0

    def test_get_session_file_path(self, temp_dir: Path) -> None:
        """Test getting the session file path."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test:session:006"

        event = create_session_started(session_id)
        store.append(event)

        file_path = store.get_session_file_path(session_id)
        assert file_path.exists()
        assert file_path.suffix == ".jsonl"

        # Verify file content
        content = file_path.read_text()
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["event_type"] == "SESSION_STARTED.1"

    def test_get_all_sessions(self, temp_dir: Path) -> None:
        """Test getting all session keys."""
        store = FileEventStore(base_dir=temp_dir)

        # Create events for multiple sessions
        for i in range(3):
            session_id = f"test-session-{i}"
            event = create_session_started(session_id)
            store.append(event)

        sessions_result = store.get_all_sessions()
        assert sessions_result.is_ok()
        sessions = sessions_result.unwrap()
        assert len(sessions) == 3

    def test_count_events(self, temp_dir: Path) -> None:
        """Test counting events across all sessions."""
        store = FileEventStore(base_dir=temp_dir)

        events = []
        for i in range(3):
            session_id = f"test-session-{i}"
            events.extend([
                create_tool_called(session_id, f"tool{i}", f"call-{i}"),
                create_tool_completed(session_id, f"tool{i}", f"call-{i}", duration_ms=50),
            ])

        store.append_batch(events)

        count_result = store.count_events()
        assert count_result.is_ok()
        assert count_result.unwrap() == 6

    def test_state_reconstruction_from_file(self, temp_dir: Path) -> None:
        """Test reconstructing session state from file-stored events."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-session-reconstruct"

        # Store events
        events = [
            create_session_started(session_id, project_path="/test/project"),
            create_tool_called(session_id, "read_file", "call-001", turn_number=1),
            create_tool_completed(
                session_id, "read_file", "call-001", duration_ms=50
            ),
            create_tool_called(session_id, "web_search", "call-002", turn_number=1),
            create_tool_failed(
                session_id,
                "web_search",
                "call-002",
                "Connection timeout",
                duration_ms=100,
            ),
        ]
        store.append_batch(events)

        # Retrieve and reconstruct
        stored_events = store.get_events_for_session(session_id).unwrap()
        projector = SessionStateProjector()
        state = projector.replay_events(stored_events, session_id)

        assert state.session_id == session_id
        assert len(state.tool_calls) == 2
        assert len(state.errors) == 1


class TestHybridEventStore:
    """Test the hybrid event store with memory cache and file persistence."""

    def test_write_then_read(self, temp_dir: Path) -> None:
        """Test basic write and read operations."""
        store = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))
        session_id = "test-hybrid-001"

        event = create_session_started(session_id)
        result = store.append(event)
        assert result.is_ok()

        # Read from cache (fast path)
        events_result = store.get_events_for_session(session_id)
        assert events_result.is_ok()
        events = events_result.unwrap()
        assert len(events) == 1

    def test_recovery_from_file(self, temp_dir: Path) -> None:
        """Test recovering events from file on new instance."""
        # First instance writes events
        store1 = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))
        session_id = "test-hybrid-002"

        events = [
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
        ]
        store1.append_batch(events)

        # Create new instance - should recover from file
        store2 = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))
        events_result = store2.get_events_for_session(session_id)
        assert events_result.is_ok()
        recovered = events_result.unwrap()
        assert len(recovered) == 2

    def test_batch_operations(self, temp_dir: Path) -> None:
        """Test batch append operations."""
        store = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))
        session_id = "test-hybrid-003"

        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=30),
        ]

        result = store.append_batch(events)
        assert result.is_ok()

        count_result = store.count_events()
        assert count_result.is_ok()
        assert count_result.unwrap() == 3

    def test_clear_operations(self, temp_dir: Path) -> None:
        """Test clearing session events."""
        store = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))
        session_id = "test-hybrid-004"

        events = [create_session_started(session_id)]
        store.append_batch(events)

        # Verify exists
        count = store.count_events().unwrap()
        assert count == 1

        # Clear
        store.clear_session(session_id)

        # Verify cleared
        events_result = store.get_events_for_session(session_id)
        assert len(events_result.unwrap()) == 0

    def test_multiple_sessions(self, temp_dir: Path) -> None:
        """Test handling multiple sessions."""
        store = HybridEventStore(file_store=FileEventStore(base_dir=temp_dir))

        for i in range(5):
            session_id = f"test-session-{i}"
            event = create_session_started(session_id)
            store.append(event)

        # Check all sessions
        sessions = store.get_all_sessions().unwrap()
        assert len(sessions) == 5

        count = store.count_events().unwrap()
        assert count == 5

    def test_sync_from_file(self, temp_dir: Path) -> None:
        """Test syncing events from file to cache."""
        # Create file store and write events
        file_store = FileEventStore(base_dir=temp_dir)
        session_id = "test-sync-001"

        events = [
            create_tool_called(session_id, "tool1", "call-001"),
            create_tool_completed(session_id, "tool1", "call-001", duration_ms=50),
        ]
        file_store.append_batch(events)

        # Create hybrid store with same directory
        store = HybridEventStore(file_store=file_store, auto_recover=False)

        # Initially empty
        assert store.count_events().unwrap() == 0

        # Sync from file
        synced = store.sync_from_file(session_id)
        assert synced.is_ok()
        assert synced.unwrap() == 2

        # Now available in cache
        assert store.count_events().unwrap() == 2


class TestFileStorageIntegration:
    """Integration tests for file-based event storage."""

    def test_full_event_lifecycle(self, temp_dir: Path) -> None:
        """Test a full event lifecycle: create, store, retrieve, replay."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-lifecycle"

        # Create session events
        start_event = create_session_started(session_id, project_path="/project")
        store.append(start_event)

        tool_events = []
        for i in range(5):
            call_id = f"call-{i}"
            tool_events.append(create_tool_called(session_id, f"tool{i}", call_id))
            tool_events.append(
                create_tool_completed(
                    session_id, f"tool{i}", call_id, duration_ms=50 * (i + 1)
                )
            )

        store.append_batch(tool_events)

        # Retrieve and verify
        all_events = store.get_events_for_session(session_id).unwrap()
        assert len(all_events) == 11  # 1 start + 5 called + 5 completed

        # Reconstruct state
        projector = SessionStateProjector()
        state = projector.replay_events(all_events, session_id)

        assert state.session_id == session_id
        assert len(state.tool_calls) == 5
        assert state.project_path == "/project"

    def test_event_audit_trail(self, temp_dir: Path) -> None:
        """Test using file events as an audit trail."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-audit"

        # Simulate a session with mixed events
        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "read_file", "call-001"),
            create_tool_completed(session_id, "read_file", "call-001", duration_ms=45),
            create_tool_called(session_id, "write_file", "call-002"),
            create_tool_failed(
                session_id, "write_file", "call-002", "Permission denied", duration_ms=10
            ),
        ]
        store.append_batch(events)

        # Retrieve tool failures
        failures = store.get_events_by_type(session_id, "TOOL_FAILED.1").unwrap()
        assert len(failures) == 1
        assert "Permission denied" in failures[0].error_message

        # Get all events for audit
        all_events = store.get_events_for_session(session_id).unwrap()
        audit_log = [(e.event_type, e.timestamp) for e in all_events]

        assert len(audit_log) == 5
        assert audit_log[0][0] == "SESSION_STARTED.1"
        assert audit_log[-1][0] == "TOOL_FAILED.1"

    def test_multiple_session_isolation(self, temp_dir: Path) -> None:
        """Test that sessions are properly isolated."""
        store = FileEventStore(base_dir=temp_dir)

        # Session A
        session_a = "session-a"
        store.append(create_session_started(session_a))
        store.append(create_tool_called(session_a, "tool_a", "call-a1"))

        # Session B
        session_b = "session-b"
        store.append(create_session_started(session_b))
        store.append(create_tool_called(session_b, "tool_b", "call-b1"))
        store.append(create_tool_completed(session_b, "tool_b", "call-b1", duration_ms=20))

        # Verify isolation
        events_a = store.get_events_for_session(session_a).unwrap()
        assert len(events_a) == 2
        assert all(e.session_key == session_a for e in events_a)

        events_b = store.get_events_for_session(session_b).unwrap()
        assert len(events_b) == 3
        assert all(e.session_key == session_b for e in events_b)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
