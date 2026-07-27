"""Unit tests for the events_cli module."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from butler.cli.events_cli import (
    register_events_parser,
    _cmd_events_metrics,
    _cmd_events_audit,
    _cmd_events_sessions,
    _cmd_events_reset,
)


class TestEventsCli:
    """Tests for events CLI commands."""

    def test_register_events_parser(self):
        """Test that events parser is registered correctly."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        register_events_parser(sub)

        # Test that help works (--help triggers SystemExit)
        with pytest.raises(SystemExit):
            parser.parse_args(["events", "--help"])

    def test_register_events_subcommands(self):
        """Test that all subcommands are registered."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        register_events_parser(sub)

        # Check all subcommands exist
        events_parser = sub.choices["events"]
        sub_subparsers = events_parser._subparsers._actions[1]
        subcommands = list(sub_subparsers.choices.keys())

        assert "metrics" in subcommands
        assert "audit" in subcommands
        assert "sessions" in subcommands
        assert "reset" in subcommands

    @patch("butler.core.events.event_consumer.get_event_metrics_collector")
    def test_cmd_events_metrics(self, mock_get_collector):
        """Test metrics command."""
        mock_collector = MagicMock()
        mock_collector.get_metrics.return_value = {
            "uptime_seconds": 10.5,
            "total_events": 5,
            "total_sessions": 2,
            "llm_api_call_count": 3,
            "tool_call_count": 2,
            "memory_sync_count": 1,
            "error_count": 0,
            "event_counts": {"LLMApiCall": 3, "ToolCallCompleted": 2},
            "session_counts": {"session1": 3, "session2": 2},
        }
        mock_get_collector.return_value = mock_collector

        ns = argparse.Namespace(json=False)
        result = _cmd_events_metrics(ns)
        assert result == 0

    @patch("butler.core.events.event_consumer.get_event_metrics_collector")
    def test_cmd_events_metrics_json(self, mock_get_collector):
        """Test metrics command with JSON output."""
        mock_collector = MagicMock()
        mock_collector.get_metrics.return_value = {
            "uptime_seconds": 10.5,
            "total_events": 5,
        }
        mock_get_collector.return_value = mock_collector

        ns = argparse.Namespace(json=True)
        result = _cmd_events_metrics(ns)
        assert result == 0

    @patch("butler.core.events.event_consumer.get_event_audit_logger")
    def test_cmd_events_audit(self, mock_get_logger):
        """Test audit command."""
        mock_logger = MagicMock()
        mock_logger.get_history.return_value = [
            {
                "event_id": "test-id-1",
                "event_type": "LLMApiCall",
                "session_key": "session1",
                "timestamp": "2026-07-24T00:00:00Z",
                "data": {"provider": "test"},
            }
        ]
        mock_get_logger.return_value = mock_logger

        ns = argparse.Namespace(session="", type="", json=False, limit=50)
        result = _cmd_events_audit(ns)
        assert result == 0

    @patch("butler.core.events.event_consumer.get_event_audit_logger")
    def test_cmd_events_audit_by_session(self, mock_get_logger):
        """Test audit command with session filter."""
        mock_logger = MagicMock()
        mock_logger.search_by_session.return_value = []
        mock_get_logger.return_value = mock_logger

        ns = argparse.Namespace(session="session1", type="", json=False, limit=50)
        result = _cmd_events_audit(ns)
        assert result == 0
        mock_logger.search_by_session.assert_called_once_with("session1")

    @patch("butler.core.events.event_consumer.get_event_audit_logger")
    def test_cmd_events_audit_by_type(self, mock_get_logger):
        """Test audit command with type filter."""
        mock_logger = MagicMock()
        mock_logger.search_by_type.return_value = []
        mock_get_logger.return_value = mock_logger

        ns = argparse.Namespace(session="", type="LLMApiCall", json=False, limit=50)
        result = _cmd_events_audit(ns)
        assert result == 0
        mock_logger.search_by_type.assert_called_once_with("LLMApiCall")

    @patch("butler.core.events.event_consumer.get_session_activity_tracker")
    def test_cmd_events_sessions(self, mock_get_tracker):
        """Test sessions command."""
        mock_tracker = MagicMock()
        mock_tracker.get_active_sessions.return_value = {
            "session1": {
                "event_count": 5,
                "llm_calls": 3,
                "tool_calls": 2,
                "errors": 0,
                "last_activity": "2026-07-24T00:00:00Z",
            }
        }
        mock_get_tracker.return_value = mock_tracker

        ns = argparse.Namespace(json=False, minutes=60)
        result = _cmd_events_sessions(ns)
        assert result == 0

    @patch("butler.core.events.event_consumer.get_session_activity_tracker")
    def test_cmd_events_sessions_json(self, mock_get_tracker):
        """Test sessions command with JSON output."""
        mock_tracker = MagicMock()
        mock_tracker.get_active_sessions.return_value = {}
        mock_get_tracker.return_value = mock_tracker

        ns = argparse.Namespace(json=True, minutes=60)
        result = _cmd_events_sessions(ns)
        assert result == 0

    @patch("butler.core.events.event_consumer.get_event_metrics_collector")
    @patch("butler.core.events.event_consumer.get_event_audit_logger")
    @patch("butler.core.events.event_consumer.get_session_activity_tracker")
    def test_cmd_events_reset(
        self,
        mock_get_tracker,
        mock_get_logger,
        mock_get_collector,
    ):
        """Test reset command."""
        mock_collector = MagicMock()
        mock_logger = MagicMock()
        mock_tracker = MagicMock()

        mock_get_collector.return_value = mock_collector
        mock_get_logger.return_value = mock_logger
        mock_get_tracker.return_value = mock_tracker

        ns = argparse.Namespace()
        result = _cmd_events_reset(ns)
        assert result == 0

        mock_collector.reset.assert_called_once()
        mock_logger.reset.assert_called_once()
        mock_tracker.reset.assert_called_once()