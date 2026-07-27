"""Integration tests for tool execution event sourcing.

Tests the end-to-end flow of:
1. Tool execution emitting session events
2. Event bus subscribers receiving events
3. Session state reconstruction from events
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from butler.core.events import (
    EventBus,
    SessionState,
    SessionStateProjector,
    ToolCalled,
    ToolCompleted,
    ToolFailedEvent,
    get_global_event_bus,
    reset_global_event_bus,
)
from butler.core.tool_executor import (
    execute_tool_calls_sequential,
    execute_tool_calls_concurrent,
)
from butler.core.tool_event_emitter import (
    emit_tool_called_event,
    emit_tool_completed_event,
    emit_tool_failed_event,
)
from butler.core.tool_failure_bridge import (
    classify_tool_error,
    tool_result_to_effects,
    create_error_tool_failure,
)


class MockToolCall:
    """Mock tool call object for testing."""

    def __init__(self, name: str, arguments: dict[str, Any], call_id: str = ""):
        self.name = name
        self.arguments = json.dumps(arguments)
        self.id = call_id or f"call-{name}"


def mock_dispatch_fn(name: str, args: dict[str, Any], call_id: str) -> str:
    """Mock tool dispatch function for testing."""
    if name == "read_file":
        return json.dumps({"content": "File content here", "path": args.get("path", "")})
    elif name == "web_search":
        return json.dumps({"results": ["Result 1", "Result 2"], "query": args.get("query", "")})
    elif name == "failing_tool":
        return json.dumps({"error": "Tool failed", "error_kind": "retry"})
    elif name == "slow_tool":
        time.sleep(0.05)
        return json.dumps({"result": "Slow tool completed"})
    else:
        return json.dumps({"result": f"Unknown tool: {name}"})


@pytest.fixture
def event_bus():
    """Reset and provide a clean event bus."""
    reset_global_event_bus()
    bus = get_global_event_bus()
    return bus


class TestToolEventEmission:
    """Test that tool execution emits session events."""

    def test_sequential_execution_emits_events(self, event_bus: EventBus) -> None:
        """Test that sequential tool execution emits ToolCalled and ToolCompleted events."""
        session_id = "wx:test-session-001"
        events_received: list[Any] = []

        def on_tool_called(event: ToolCalled) -> None:
            events_received.append(("called", event))

        def on_tool_completed(event: ToolCompleted) -> None:
            events_received.append(("completed", event))

        def on_tool_failed(event: ToolFailedEvent) -> None:
            events_received.append(("failed", event))

        event_bus.subscribe("TOOL_CALLED.1", on_tool_called)
        event_bus.subscribe("TOOL_COMPLETED.1", on_tool_completed)
        event_bus.subscribe("TOOL_FAILED.1", on_tool_failed)

        tool_calls = [
            MockToolCall("read_file", {"path": "/test/file.txt"}, "call-001"),
            MockToolCall("web_search", {"query": "test"}, "call-002"),
        ]

        results = execute_tool_calls_sequential(
            tool_calls,
            mock_dispatch_fn,
            session_id=session_id,
        )

        assert len(results) == 2
        assert len(events_received) == 4  # 2 called + 2 completed

        called_events = [e for t, e in events_received if t == "called"]
        completed_events = [e for t, e in events_received if t == "completed"]

        assert len(called_events) == 2
        assert len(completed_events) == 2

        # Verify event content
        assert called_events[0].tool_name == "read_file"
        assert called_events[1].tool_name == "web_search"
        assert completed_events[0].tool_name == "read_file"
        assert completed_events[0].success is True

    def test_sequential_execution_emits_failure_event(self, event_bus: EventBus) -> None:
        """Test that sequential tool execution emits ToolFailedEvent on error."""
        session_id = "wx:test-session-002"
        events_received: list[Any] = []

        def on_tool_failed(event: ToolFailedEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("TOOL_FAILED.1", on_tool_failed)

        tool_calls = [
            MockToolCall("failing_tool", {"param": "value"}, "call-003"),
        ]

        results = execute_tool_calls_sequential(
            tool_calls,
            mock_dispatch_fn,
            session_id=session_id,
        )

        assert len(results) == 1
        assert len(events_received) == 1

        failed_event = events_received[0]
        assert failed_event.tool_name == "failing_tool"
        assert "Tool failed" in failed_event.error_message

    def test_concurrent_execution_emits_events(self, event_bus: EventBus) -> None:
        """Test that concurrent tool execution emits session events."""
        session_id = "wx:test-session-003"
        events_received: list[Any] = []

        def on_tool_called(event: ToolCalled) -> None:
            events_received.append(("called", event))

        def on_tool_completed(event: ToolCompleted) -> None:
            events_received.append(("completed", event))

        event_bus.subscribe("TOOL_CALLED.1", on_tool_called)
        event_bus.subscribe("TOOL_COMPLETED.1", on_tool_completed)

        tool_calls = [
            MockToolCall("read_file", {"path": "/test/file.txt"}, "call-004"),
            MockToolCall("slow_tool", {"param": "value"}, "call-005"),
        ]

        results = execute_tool_calls_concurrent(
            tool_calls,
            mock_dispatch_fn,
            session_id=session_id,
            max_workers=2,
        )

        assert len(results) == 2
        assert len(events_received) >= 4  # At least 2 called + 2 completed


class TestSessionStateReconstruction:
    """Test session state reconstruction from events."""

    def test_reconstruct_state_from_tool_events(self, event_bus: EventBus) -> None:
        """Test reconstructing session state from tool execution events."""
        session_id = "wx:test-session-004"
        all_events: list[Any] = []

        # Collect all events
        def collect_all(event: Any) -> None:
            all_events.append(event)

        # Subscribe to all tool events
        for event_type in ["TOOL_CALLED.1", "TOOL_COMPLETED.1", "TOOL_FAILED.1"]:
            event_bus.subscribe(event_type, collect_all)

        # Execute tools
        tool_calls = [
            MockToolCall("read_file", {"path": "/test/file.txt"}, "call-001"),
            MockToolCall("web_search", {"query": "test"}, "call-002"),
            MockToolCall("failing_tool", {"param": "value"}, "call-003"),
        ]

        execute_tool_calls_sequential(
            tool_calls,
            mock_dispatch_fn,
            session_id=session_id,
        )

        # Reconstruct state
        projector = SessionStateProjector()
        state = projector.replay_events(all_events, session_id)

        # Verify reconstructed state
        assert state.session_id == session_id
        assert len(state.tool_calls) == 3
        assert len(state.errors) == 1

        # Verify tool call statuses
        tool_call_map = {tc["tool_name"]: tc for tc in state.tool_calls}
        assert tool_call_map["read_file"]["status"] == "completed"
        assert tool_call_map["web_search"]["status"] == "completed"
        assert tool_call_map["failing_tool"]["status"] == "failed"


class TestToolFailureIntegration:
    """Test ToolFailure integration with error handling."""

    def test_classify_tool_error_success(self) -> None:
        """Test classifying successful tool results."""
        success_result = json.dumps({"content": "File content"})
        is_error, msg, kind = classify_tool_error(success_result)
        assert is_error is False
        assert msg == ""

    def test_classify_tool_error_failure(self) -> None:
        """Test classifying failed tool results."""
        error_result = json.dumps({"error": "File not found", "error_kind": "retry"})
        is_error, msg, kind = classify_tool_error(error_result)
        assert is_error is True
        assert msg == "File not found"
        assert kind == "retry"

    def test_tool_result_to_effects_success(self) -> None:
        """Test converting successful results to ToolSuccess."""
        result = tool_result_to_effects("read_file", "File content", duration_ms=50)
        assert hasattr(result, "tool_name")
        assert result.tool_name == "read_file"

    def test_tool_result_to_effects_failure(self) -> None:
        """Test converting failed results to ToolFailure."""
        error_result = json.dumps({"error": "Timeout", "error_kind": "retry"})
        result = tool_result_to_effects("web_search", error_result, duration_ms=100)
        assert hasattr(result, "tool_name")
        assert result.tool_name == "web_search"

    def test_create_error_tool_failure(self) -> None:
        """Test creating ToolFailure from exceptions."""
        try:
            raise ConnectionError("Network timeout")
        except ConnectionError as e:
            failure = create_error_tool_failure("web_search", e, duration_ms=200)
            assert failure.tool_name == "web_search"
            assert failure.is_retryable is True
            assert "Network timeout" in failure.message


class TestEventEmitters:
    """Test event emitter functions directly."""

    def test_emit_tool_called_event(self, event_bus: EventBus) -> None:
        """Test emitting a ToolCalled event directly."""
        events_received: list[Any] = []

        def on_event(event: ToolCalled) -> None:
            events_received.append(event)

        event_bus.subscribe("TOOL_CALLED.1", on_event)

        emit_tool_called_event(
            session_id="test-session",
            tool_name="test_tool",
            call_id="call-001",
            args={"param": "value"},
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.tool_name == "test_tool"
        assert event.aggregate_id == "test-session"

    def test_emit_tool_completed_event(self, event_bus: EventBus) -> None:
        """Test emitting a ToolCompleted event directly."""
        events_received: list[Any] = []

        def on_event(event: ToolCompleted) -> None:
            events_received.append(event)

        event_bus.subscribe("TOOL_COMPLETED.1", on_event)

        emit_tool_completed_event(
            session_id="test-session",
            tool_name="test_tool",
            call_id="call-001",
            result="Success result",
            duration_ms=50,
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.tool_name == "test_tool"
        assert event.success is True
        assert event.duration_ms == 50

    def test_emit_tool_failed_event(self, event_bus: EventBus) -> None:
        """Test emitting a ToolFailedEvent directly."""
        events_received: list[Any] = []

        def on_event(event: ToolFailedEvent) -> None:
            events_received.append(event)

        event_bus.subscribe("TOOL_FAILED.1", on_event)

        emit_tool_failed_event(
            session_id="test-session",
            tool_name="test_tool",
            call_id="call-001",
            error_message="Something went wrong",
            error_kind="retry",
            duration_ms=100,
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.tool_name == "test_tool"
        assert "Something went wrong" in event.error_message


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
