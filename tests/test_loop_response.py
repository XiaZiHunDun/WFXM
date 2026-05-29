"""Tests for butler.core.loop_response."""

from butler.core.loop_response import (
    empty_retry_message,
    needs_empty_content_retry,
    needs_truncation_continue,
    sanitize_response,
    truncation_continue_message,
)
from butler.transport.types import NormalizedResponse


class TestSanitizeResponse:
    def test_strips_think_blocks(self):
        resp = NormalizedResponse(content="<think>internal</think>answer")
        result = sanitize_response(resp)
        assert "<think>" not in (result.content or "")

    def test_empty_content_no_tools(self):
        resp = NormalizedResponse(content="", reasoning="some reasoning")
        assert needs_empty_content_retry(resp) is True

    def test_has_content_no_retry(self):
        resp = NormalizedResponse(content="visible text")
        assert needs_empty_content_retry(resp) is False

    def test_has_tool_calls_no_retry(self):
        resp = NormalizedResponse(
            content="", tool_calls=[{"id": "1", "function": {"name": "test"}}]
        )
        assert needs_empty_content_retry(resp) is False


class TestTruncationContinue:
    def test_length_finish_no_tools(self):
        resp = NormalizedResponse(content="partial", finish_reason="length")
        assert needs_truncation_continue(resp) is True

    def test_stop_finish(self):
        resp = NormalizedResponse(content="done", finish_reason="stop")
        assert needs_truncation_continue(resp) is False


class TestNudgeMessages:
    def test_empty_retry_message(self):
        assert len(empty_retry_message()) > 0

    def test_truncation_message(self):
        assert len(truncation_continue_message()) > 0
