"""Unit tests for the tool_executor module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from butler.core.tool_executor import (
    ToolProgressCallbacks,
    execute_tool_calls_concurrent,
    execute_tool_calls_sequential,
    apply_tool_request_middleware,
    _parse_tool_arguments,
    _resolve_concurrent_tool_timeout,
)


class TestParseToolArguments:
    """Tests for _parse_tool_arguments."""

    def test_parse_valid_json(self):
        args, error = _parse_tool_arguments('{"key": "value"}')
        assert args == {"key": "value"}
        assert error is None

    def test_parse_invalid_json(self):
        args, error = _parse_tool_arguments('{"key": "value"')
        assert args == {}
        assert error is not None
        assert "Invalid tool arguments" in error

    def test_parse_non_json_string(self):
        args, error = _parse_tool_arguments("not json")
        assert args == {}
        assert error is not None

    def test_parse_dict(self):
        # _parse_tool_arguments expects string input, dict input is treated as invalid
        args, error = _parse_tool_arguments({"key": "value"})
        assert args == {}
        assert error is not None


class TestResolveConcurrentToolTimeout:
    """Tests for _resolve_concurrent_tool_timeout."""

    @patch("os.getenv")
    def test_default_timeout(self, mock_getenv):
        mock_getenv.return_value = ""
        assert _resolve_concurrent_tool_timeout() == 420.0

    @patch("os.getenv")
    def test_custom_timeout(self, mock_getenv):
        mock_getenv.return_value = "120"
        assert _resolve_concurrent_tool_timeout() == 120.0

    @patch("os.getenv")
    def test_invalid_timeout(self, mock_getenv):
        mock_getenv.return_value = "invalid"
        assert _resolve_concurrent_tool_timeout() == 420.0

    @patch("os.getenv")
    def test_zero_timeout(self, mock_getenv):
        mock_getenv.return_value = "0"
        assert _resolve_concurrent_tool_timeout() is None


class TestToolProgressCallbacks:
    """Tests for ToolProgressCallbacks."""

    def test_callbacks_creation(self):
        callbacks = ToolProgressCallbacks()
        assert callbacks.on_start is None
        assert callbacks.on_complete is None

    def test_callbacks_with_handlers(self):
        start_handler = MagicMock()
        complete_handler = MagicMock()
        callbacks = ToolProgressCallbacks(on_start=start_handler, on_complete=complete_handler)
        callbacks.on_start("test", {}, "id123")
        start_handler.assert_called_once_with("test", {}, "id123")
        callbacks.on_complete("test", {}, "result", 0.5, False)
        complete_handler.assert_called_once_with("test", {}, "result", 0.5, False)


class TestApplyToolRequestMiddleware:
    """Tests for apply_tool_request_middleware."""

    def test_middleware_applied(self):
        # Test that middleware doesn't break when tool_middleware module is not available
        args, trace = apply_tool_request_middleware("test_tool", {"key": "value"})
        assert args == {"key": "value"}
        assert trace == []

    def test_middleware_with_session_id(self):
        args, trace = apply_tool_request_middleware(
            "test_tool", {"key": "value"}, session_id="test_session"
        )
        assert args == {"key": "value"}
        assert trace == []


class TestExecuteToolCallsSequential:
    """Tests for execute_tool_calls_sequential."""

    def test_empty_tool_calls(self):
        results = execute_tool_calls_sequential([], lambda n, a, i: "result")
        assert results == []

    def test_single_tool_call(self):
        dispatch_fn = MagicMock(return_value='{"result": "success"}')
        tool_calls = [{"name": "test_tool", "arguments": '{"arg": "value"}'}]
        results = execute_tool_calls_sequential(tool_calls, dispatch_fn)
        assert len(results) == 1
        assert results[0][0] == tool_calls[0]
        assert results[0][1] == '{"result": "success"}'
        dispatch_fn.assert_called_once_with("test_tool", {"arg": "value"}, "")

    def test_interrupt_during_execution(self):
        interrupted = [False]

        def interrupt_check():
            return interrupted[0]

        dispatch_fn = MagicMock(side_effect=lambda n, a, i: ("result"))
        tool_calls = [
            {"name": "tool1", "arguments": '{}'},
            {"name": "tool2", "arguments": '{}'},
        ]
        interrupted[0] = True
        results = execute_tool_calls_sequential(tool_calls, dispatch_fn, interrupt_check=interrupt_check)
        assert len(results) == 1
        assert "cancelled" in results[0][1]

    def test_progress_callbacks(self):
        start_handler = MagicMock()
        complete_handler = MagicMock()
        callbacks = ToolProgressCallbacks(on_start=start_handler, on_complete=complete_handler)
        dispatch_fn = MagicMock(return_value='{"result": "success"}')
        tool_calls = [{"name": "test_tool", "arguments": '{}'}]
        execute_tool_calls_sequential(tool_calls, dispatch_fn, progress_callbacks=callbacks)
        start_handler.assert_called_once()
        complete_handler.assert_called_once()


class TestExecuteToolCallsConcurrent:
    """Tests for execute_tool_calls_concurrent."""

    def test_empty_tool_calls(self):
        results = execute_tool_calls_concurrent([], lambda n, a, i: "result")
        assert results == []

    def test_single_tool_call(self):
        dispatch_fn = MagicMock(return_value='{"result": "success"}')
        tool_calls = [{"name": "test_tool", "arguments": '{"arg": "value"}'}]
        results = execute_tool_calls_concurrent(tool_calls, dispatch_fn)
        assert len(results) == 1
        assert results[0][0] == tool_calls[0]
        assert results[0][1] == '{"result": "success"}'

    def test_multiple_tool_calls(self):
        dispatch_fn = MagicMock(side_effect=lambda n, a, i: f'{{"result": "{n}"}}')
        tool_calls = [
            {"name": "tool1", "arguments": '{}'},
            {"name": "tool2", "arguments": '{}'},
        ]
        results = execute_tool_calls_concurrent(tool_calls, dispatch_fn, max_workers=2)
        assert len(results) == 2
        assert results[0][0]["name"] == "tool1"
        assert results[1][0]["name"] == "tool2"

    def test_interrupt_before_start(self):
        interrupted = [True]

        def interrupt_check():
            return interrupted[0]

        dispatch_fn = MagicMock()
        tool_calls = [{"name": "tool1", "arguments": '{}'}]
        results = execute_tool_calls_concurrent(tool_calls, dispatch_fn, interrupt_check=interrupt_check)
        assert len(results) == 1
        assert "cancelled" in results[0][1]
        dispatch_fn.assert_not_called()

    def test_malformed_arguments(self):
        dispatch_fn = MagicMock()
        tool_calls = [{"name": "tool1", "arguments": "not json"}]
        results = execute_tool_calls_concurrent(tool_calls, dispatch_fn)
        assert len(results) == 1
        assert "Invalid tool arguments" in results[0][1]
        dispatch_fn.assert_not_called()