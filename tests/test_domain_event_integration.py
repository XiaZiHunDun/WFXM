"""Tests for approval and message event emitters."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from butler.core.events import (
    EventBus,
    EventIndex,
    EventQuery,
    EventQueryFilter,
    FileEventStore,
    SessionStateProjector,
    create_session_started,
    create_tool_called,
    create_tool_completed,
    create_tool_failed,
    get_global_event_bus,
    reset_global_event_bus,
)
from butler.core.events.approval_event_emitter import (
    emit_approval_denied_event,
    emit_approval_granted_event,
    emit_approval_requested_event,
    emit_approval_revoked_event,
)
from butler.core.events.message_event_emitter import (
    emit_error_occurred_event,
    emit_message_received_event,
    emit_message_sent_event,
)
from butler.core.events.event_types import DomainEvent


@pytest.fixture
def event_bus() -> EventBus:
    """Reset and return a fresh global event bus."""
    reset_global_event_bus()
    return get_global_event_bus()


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestApprovalEventEmitter:
    """Test approval-related event emission."""

    def test_emit_approval_requested_event(self, event_bus: EventBus) -> None:
        """Test emitting an approval requested event."""
        session_id = "test-approval-001"
        events_received: list[DomainEvent] = []

        def on_requested(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_REQUESTED.1", on_requested)

        emit_approval_requested_event(
            session_id=session_id,
            tool_name="write_file",
            reason="Need to write config file",
            permission_type="rule",
            fingerprint="abc123def456",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_REQUESTED.1"
        assert event.session_key == session_id
        assert event.data["tool_name"] == "write_file"
        assert event.data["reason"] == "Need to write config file"
        assert event.data["fingerprint"] == "abc123def456"

    def test_emit_approval_granted_event_once(self, event_bus: EventBus) -> None:
        """Test emitting an approval granted event (once)."""
        session_id = "test-approval-002"
        events_received: list[DomainEvent] = []

        def on_granted(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_GRANTED.1", on_granted)

        emit_approval_granted_event(
            session_id=session_id,
            tool_name="read_file",
            granted_by="owner",
            duration_type="once",
            permission="file_read",
            pattern="/test/*.py",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_GRANTED.1"
        assert event.data["duration_type"] == "once"
        assert event.data["permission"] == "file_read"

    def test_emit_approval_granted_event_always(self, event_bus: EventBus) -> None:
        """Test emitting an approval granted event (always)."""
        session_id = "test-approval-003"
        events_received: list[DomainEvent] = []

        def on_granted(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_GRANTED.1", on_granted)

        emit_approval_granted_event(
            session_id=session_id,
            tool_name="web_search",
            granted_by="owner",
            duration_type="always",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.data["duration_type"] == "always"

    def test_emit_approval_denied_event(self, event_bus: EventBus) -> None:
        """Test emitting an approval denied event."""
        session_id = "test-approval-004"
        events_received: list[DomainEvent] = []

        def on_denied(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_DENIED.1", on_denied)

        emit_approval_denied_event(
            session_id=session_id,
            tool_name="execute_command",
            denied_by="owner",
            reason="Dangerous command blocked",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_DENIED.1"
        assert event.data["reason"] == "Dangerous command blocked"

    def test_emit_approval_revoked_event(self, event_bus: EventBus) -> None:
        """Test emitting an approval revoked event."""
        session_id = "test-approval-005"
        events_received: list[DomainEvent] = []

        def on_denied(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_DENIED.1", on_denied)

        emit_approval_revoked_event(
            session_id=session_id,
            tool_name="write_file",
            permission="file_write",
            revoked_by="owner",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert "Revoked" in event.data["reason"]


class TestMessageEventEmitter:
    """Test message-related event emission."""

    def test_emit_message_received_event(self, event_bus: EventBus) -> None:
        """Test emitting a message received event."""
        session_id = "test-message-001"
        events_received: list[DomainEvent] = []

        def on_received(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("MESSAGE_RECEIVED.1", on_received)

        emit_message_received_event(
            session_id=session_id,
            content_preview="Hello, how are you?",
            message_type="text",
            channel="wechat",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "MESSAGE_RECEIVED.1"
        assert event.data["channel"] == "wechat"
        assert event.data["message_type"] == "text"

    def test_emit_message_sent_event(self, event_bus: EventBus) -> None:
        """Test emitting a message sent event."""
        session_id = "test-message-002"
        events_received: list[DomainEvent] = []

        def on_sent(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("MESSAGE_SENT.1", on_sent)

        emit_message_sent_event(
            session_id=session_id,
            content_preview="I'm fine, thanks!",
            message_type="text",
            duration_ms=150,
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "MESSAGE_SENT.1"
        assert event.data["duration_ms"] == 150

    def test_emit_error_occurred_event(self, event_bus: EventBus) -> None:
        """Test emitting an error occurred event."""
        session_id = "test-message-003"
        events_received: list[DomainEvent] = []

        def on_error(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("ERROR_OCCURRED.1", on_error)

        emit_error_occurred_event(
            session_id=session_id,
            error_type="tool_timeout",
            error_message="Tool execution timed out after 30s",
            source="tool_executor",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == "ERROR_OCCURRED.1"
        assert event.data["error_type"] == "tool_timeout"
        assert event.data["source"] == "tool_executor"


class TestEventEmitterIntegration:
    """Test integration of emitters with event store and projector."""

    def test_approval_events_integrate_with_store(self, temp_dir: Path) -> None:
        """Test that approval events can be stored and replayed."""
        from butler.core.events.approval_event_emitter import (
            emit_approval_granted_event,
        )
        from butler.core.events.event_types import generate_event_id

        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-integration-001"

        # Manually create and store events (simulating what emitters do)
        from butler.core.events.session_events import ApprovalGranted

        event = ApprovalGranted(
            event_id=generate_event_id(),
            event_type="APPROVAL_GRANTED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data={
                "tool_name": "read_file",
                "granted_by": "owner",
                "duration_type": "once",
            },
            session_id=session_id,
            tool_name="read_file",
            granted_by="owner",
            duration_type="once",
        )

        result = store.append(event)
        assert result.is_ok()

        # Reconstruct state
        events_result = store.get_events_for_session(session_id)
        assert events_result.is_ok()
        events = events_result.unwrap()

        projector = SessionStateProjector()
        state = projector.replay_events(events, session_id)

        assert len(state.granted_approvals) == 1
        assert state.granted_approvals[0]["tool_name"] == "read_file"
        assert state.granted_approvals[0]["duration_type"] == "once"

    def test_error_event_integrate_with_store(self, temp_dir: Path) -> None:
        """Test that error events can be stored and queried."""
        from butler.core.events.event_types import generate_event_id
        from butler.core.events.event_types import DomainEvent

        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-integration-002"

        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ERROR_OCCURRED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data={
                "error_type": "tool_failed",
                "error_message": "Connection refused",
                "source": "network",
            },
        )

        result = store.append(event)
        assert result.is_ok()

        # Query by type
        errors = store.get_events_by_type(session_id, "ERROR_OCCURRED.1")
        assert errors.is_ok()
        assert len(errors.unwrap()) == 1

    def test_message_events_integrate_with_index(self, temp_dir: Path) -> None:
        """Test that message events can be indexed and queried."""
        store = FileEventStore(base_dir=temp_dir)
        session_id = "test-integration-003"

        # Create session events
        events = [
            create_session_started(session_id),
            create_tool_called(session_id, "read_file", "call-001"),
            create_tool_completed(session_id, "read_file", "call-001", duration_ms=50),
            create_tool_failed(
                session_id, "write_file", "call-002", "Permission denied", duration_ms=10
            ),
        ]
        store.append_batch(events)

        # Build index
        index = EventIndex()
        count = index.build_from_directory(temp_dir)
        assert count == 4

        # Query
        query = EventQuery(index)
        filter = EventQueryFilter(session_key=session_id)
        results = query.execute(temp_dir, filter)

        assert len(results) == 4
        assert results[0]["event_type"] == "SESSION_STARTED.1"

        # Aggregate
        aggregation = query.aggregate_by_type(filter)
        assert aggregation["TOOL_CALLED.1"] == 1
        assert aggregation["TOOL_COMPLETED.1"] == 1
        assert aggregation["TOOL_FAILED.1"] == 1
        assert aggregation["SESSION_STARTED.1"] == 1


class TestApprovalFlowIntegration:
    """Test integration with the actual approval flow."""

    def test_save_pending_emits_event(self, temp_dir: Path) -> None:
        """Test that save_pending emits an ApprovalRequested event."""
        reset_global_event_bus()
        event_bus = get_global_event_bus()

        events_received: list[DomainEvent] = []

        def on_requested(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_REQUESTED.1", on_requested)

        from butler.permissions.approvals import ApprovalRequest, save_pending

        request = ApprovalRequest(
            permission="file_write",
            tool="write_file",
            pattern="/test/*.log",
            reason="Need to write test results",
        )

        # Set environment for approvals path
        import os
        os.environ["BUTLER_HOME"] = str(temp_dir)

        session_key = "test-flow-001"
        fp = save_pending(session_key, request)

        assert fp != ""
        assert len(events_received) >= 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_REQUESTED.1"

    def test_grant_once_emits_event(self, temp_dir: Path) -> None:
        """Test that grant_once emits an ApprovalGranted event."""
        reset_global_event_bus()
        event_bus = get_global_event_bus()

        events_received: list[DomainEvent] = []

        def on_granted(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_GRANTED.1", on_granted)

        from butler.permissions.approvals import ApprovalRequest, grant_once, save_pending

        import os
        os.environ["BUTLER_HOME"] = str(temp_dir)

        session_key = "test-flow-002"
        request = ApprovalRequest(
            permission="file_read",
            tool="read_file",
            pattern="/test/*.py",
        )
        fp = save_pending(session_key, request)
        assert fp != ""

        result = grant_once(session_key, fingerprint=fp)
        assert result is not None
        assert "已批准一次" in result

        # Give event time to be processed
        assert len(events_received) >= 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_GRANTED.1"

    def test_grant_always_emits_event(self, temp_dir: Path) -> None:
        """Test that grant_always emits an ApprovalGranted event."""
        reset_global_event_bus()
        event_bus = get_global_event_bus()

        events_received: list[DomainEvent] = []

        def on_granted(event: DomainEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("APPROVAL_GRANTED.1", on_granted)

        from butler.permissions.approvals import grant_always

        import os
        os.environ["BUTLER_HOME"] = str(temp_dir)

        session_key = "test-flow-003"
        result = grant_always(
            session_key,
            permission="external_directory",
            tool="list_dir",
            pattern="/project/*",
        )

        assert "已始终允许" in result
        assert len(events_received) >= 1
        event = events_received[0]
        assert event.event_type == "APPROVAL_GRANTED.1"
        assert event.data["duration_type"] == "always"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
