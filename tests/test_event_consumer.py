"""Unit tests for the event_consumer module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from butler.core.events.event_consumer import (
    EventConsumer,
    EventMetricsCollector,
    EventAuditLogger,
    SessionActivityTracker,
    get_event_metrics_collector,
    get_event_audit_logger,
    get_session_activity_tracker,
    initialize_event_consumers,
    shutdown_event_consumers,
)
from butler.core.events.event_store import DomainEvent, generate_event_id, now_utc


class TestEventConsumer:
    """Tests for EventConsumer base class."""

    def test_subscribe_unsubscribe(self):
        mock_bus = MagicMock()
        consumer = EventConsumer()
        consumer.subscribe(mock_bus)
        mock_bus.subscribe.assert_called_once_with("*", consumer._handle_event)
        consumer.unsubscribe()
        mock_bus.unsubscribe.assert_called_once_with("*", consumer._handle_event)

    def test_subscribe_with_event_types(self):
        mock_bus = MagicMock()
        consumer = EventConsumer({"LLMApiCall", "ToolCallCompleted"})
        consumer.subscribe(mock_bus)
        assert mock_bus.subscribe.call_count == 2
        mock_bus.subscribe.assert_any_call("LLMApiCall", consumer._handle_event)
        mock_bus.subscribe.assert_any_call("ToolCallCompleted", consumer._handle_event)

    def test_handle_event_not_implemented(self):
        consumer = EventConsumer()
        event = DomainEvent(
            event_id="test-id",
            event_type="TestEvent",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        with pytest.raises(NotImplementedError):
            consumer._handle_event(event)


class TestEventMetricsCollector:
    """Tests for EventMetricsCollector."""

    def test_handle_llm_api_call_event(self):
        collector = EventMetricsCollector()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={"provider": "test", "model": "test-model", "prompt_tokens": 100},
        )
        collector._handle_event(event)
        metrics = collector.get_metrics()
        assert metrics["event_counts"]["LLMApiCall"] == 1
        assert metrics["llm_api_call_count"] == 1
        assert metrics["total_events"] == 1

    def test_handle_tool_call_completed_event(self):
        collector = EventMetricsCollector()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={"tool_name": "test_tool", "is_error": False},
        )
        collector._handle_event(event)
        metrics = collector.get_metrics()
        assert metrics["event_counts"]["ToolCallCompleted"] == 1
        assert metrics["tool_call_count"] == 1

    def test_handle_tool_call_error(self):
        collector = EventMetricsCollector()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={"tool_name": "test_tool", "is_error": True},
        )
        collector._handle_event(event)
        metrics = collector.get_metrics()
        assert metrics["error_count"] == 1

    def test_handle_memory_sync_completed(self):
        collector = EventMetricsCollector()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="MemorySyncCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={"success_count": 2, "error_count": 1},
        )
        collector._handle_event(event)
        metrics = collector.get_metrics()
        assert metrics["event_counts"]["MemorySyncCompleted"] == 1
        assert metrics["memory_sync_count"] == 1

    def test_handle_multiple_sessions(self):
        collector = EventMetricsCollector()
        event1 = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        event2 = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session2",
            timestamp=now_utc(),
            data={},
        )
        collector._handle_event(event1)
        collector._handle_event(event2)
        metrics = collector.get_metrics()
        assert metrics["total_sessions"] == 2

    def test_reset_metrics(self):
        collector = EventMetricsCollector()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        collector._handle_event(event)
        collector.reset()
        metrics = collector.get_metrics()
        assert metrics["total_events"] == 0
        assert metrics["total_sessions"] == 0


class TestEventAuditLogger:
    """Tests for EventAuditLogger."""

    def test_handle_event(self):
        logger = EventAuditLogger(max_history=10)
        event = DomainEvent(
            event_id="test-id-123",
            event_type="TestEvent",
            session_key="session1",
            timestamp=now_utc(),
            data={"key": "value"},
            version=1,
        )
        logger._handle_event(event)
        history = logger.get_history()
        assert len(history) == 1
        assert history[0]["event_id"] == "test-id-123"
        assert history[0]["event_type"] == "TestEvent"
        assert history[0]["session_key"] == "session1"

    def test_max_history(self):
        logger = EventAuditLogger(max_history=3)
        for i in range(5):
            event = DomainEvent(
                event_id=f"test-id-{i}",
                event_type="TestEvent",
                session_key="session1",
                timestamp=now_utc(),
                data={},
            )
            logger._handle_event(event)
        history = logger.get_history()
        assert len(history) == 3

    def test_search_by_session(self):
        logger = EventAuditLogger()
        event1 = DomainEvent(
            event_id="id1",
            event_type="TestEvent",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        event2 = DomainEvent(
            event_id="id2",
            event_type="TestEvent",
            session_key="session2",
            timestamp=now_utc(),
            data={},
        )
        logger._handle_event(event1)
        logger._handle_event(event2)
        results = logger.search_by_session("session1")
        assert len(results) == 1
        assert results[0]["event_id"] == "id1"

    def test_search_by_type(self):
        logger = EventAuditLogger()
        event1 = DomainEvent(
            event_id="id1",
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        event2 = DomainEvent(
            event_id="id2",
            event_type="ToolCallCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        logger._handle_event(event1)
        logger._handle_event(event2)
        results = logger.search_by_type("LLMApiCall")
        assert len(results) == 1
        assert results[0]["event_id"] == "id1"


class TestSessionActivityTracker:
    """Tests for SessionActivityTracker."""

    def test_handle_event_new_session(self):
        tracker = SessionActivityTracker()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        tracker._handle_event(event)
        activity = tracker.get_session_activity("session1")
        assert activity is not None
        assert activity["event_count"] == 1
        assert activity["llm_calls"] == 1

    def test_handle_event_existing_session(self):
        tracker = SessionActivityTracker()
        event1 = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        event2 = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={"is_error": False},
        )
        tracker._handle_event(event1)
        tracker._handle_event(event2)
        activity = tracker.get_session_activity("session1")
        assert activity["event_count"] == 2
        assert activity["llm_calls"] == 1
        assert activity["tool_calls"] == 1

    def test_handle_tool_call_error(self):
        tracker = SessionActivityTracker()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallCompleted",
            session_key="session1",
            timestamp=now_utc(),
            data={"is_error": True},
        )
        tracker._handle_event(event)
        activity = tracker.get_session_activity("session1")
        assert activity["errors"] == 1

    def test_get_all_sessions(self):
        tracker = SessionActivityTracker()
        event1 = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        event2 = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session2",
            timestamp=now_utc(),
            data={},
        )
        tracker._handle_event(event1)
        tracker._handle_event(event2)
        sessions = tracker.get_all_sessions()
        assert len(sessions) == 2

    def test_get_active_sessions(self):
        tracker = SessionActivityTracker()
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="session1",
            timestamp=now_utc(),
            data={},
        )
        tracker._handle_event(event)
        active = tracker.get_active_sessions(minutes=60)
        assert len(active) == 1

    def test_cleanup_stale_sessions(self):
        tracker = SessionActivityTracker()
        old_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key="stale_session",
            timestamp=old_time,
            data={},
        )
        tracker._handle_event(event)
        removed = tracker.cleanup_stale_sessions(hours=1)
        assert removed == 1
        sessions = tracker.get_all_sessions()
        assert len(sessions) == 0


class TestGlobalInstances:
    """Tests for global instance functions."""

    def test_get_event_metrics_collector(self):
        collector = get_event_metrics_collector()
        assert isinstance(collector, EventMetricsCollector)
        # Second call should return the same instance
        collector2 = get_event_metrics_collector()
        assert collector is collector2

    def test_get_event_audit_logger(self):
        logger = get_event_audit_logger()
        assert isinstance(logger, EventAuditLogger)
        logger2 = get_event_audit_logger()
        assert logger is logger2

    def test_get_session_activity_tracker(self):
        tracker = get_session_activity_tracker()
        assert isinstance(tracker, SessionActivityTracker)
        tracker2 = get_session_activity_tracker()
        assert tracker is tracker2

    def test_initialize_shutdown_consumers(self):
        initialize_event_consumers()
        shutdown_event_consumers()