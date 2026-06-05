"""L2 module tests for R2-10 [H] bad_fallback fix.

R2-10 issue: ``wire_tools_for_provider`` failure used to fall back to
``transport.convert_tools(tools)`` (generic schema). When the provider has
strict schema validation, the generic schema was rejected with a 400,
and the model could emit tool_calls that the provider would then reject.

The fix: on failure, use an empty tool list so the LLM proceeds without
tools; log the original error at ERROR level with exc_info; record the
exception on the instance for the caller to inspect.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from butler.transport.llm_client import LLMClient


_SENTINEL_CONVERT_TOOLS_CALLED = AssertionError(
    "transport.convert_tools should NOT be called as a fallback "
    "after wire_tools_for_provider failure (R2-10 fix)"
)


def _make_transport_with_tracking_convert_tools():
    """Return a mock transport whose convert_tools raises if called.

    ``normalize_response`` is configured to return a real
    ``NormalizedResponse`` so the call site under test can return one
    to its caller (the LLMClient methods always return
    ``NormalizedResponse``).
    """
    from butler.transport.types import NormalizedResponse

    transport = MagicMock()
    transport.convert_tools.side_effect = _SENTINEL_CONVERT_TOOLS_CALLED
    transport.normalize_response.return_value = NormalizedResponse(
        content="ok",
        finish_reason="stop",
    )
    return transport


def _patch_wire_tools_to_fail():
    """Patch wire_tools_for_provider to raise a sentinel error."""
    sentinel = RuntimeError("wire_tools_for_provider exploded (test)")

    def _explode(*args, **kwargs):
        raise sentinel

    return patch(
        "butler.transport.tool_wire.wire_tools_for_provider",
        side_effect=_explode,
    ), sentinel


def _patch_openai_response(mock_get_client, content="ok", tool_calls=None):
    """Configure the mocked OpenAI client to return a normal chat response.

    For non-streaming: returns a single dict that the OpenAI SDK would
    normally produce. For streaming: the returned value will be iterated
    by the stream loop, so callers should pass ``stream_chunks=True`` to
    get a proper iterable of MagicMock chunks.
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    message = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    mock_client.chat.completions.create.return_value = {
        "choices": [{"message": message, "finish_reason": "stop"}],
    }
    return mock_client


def _patch_openai_stream_response(mock_get_client, content="streamed"):
    """Configure the mocked OpenAI client to return iterable stream chunks."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content=content, tool_calls=None)
    chunk.choices[0].finish_reason = "stop"

    mock_client.chat.completions.create.return_value = iter([chunk])
    return mock_client


@pytest.mark.module_test
class TestCompleteFallback:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_complete_uses_empty_tools_when_wire_fails(self, mock_get_client):
        """On wire_tools_for_provider failure, complete() must call the API with no tools.

        The audit's R2-10 contract: "the model will be called WITHOUT tools (so
        the model knows it cannot emit tool calls for this turn)". The transport
        drops empty tool lists from the API kwargs, so the only safe assertion
        is that the API does not receive any tools at all (no dict list with
        our sentinel tool).
        """
        wire_patch, _ = _patch_wire_tools_to_fail()
        mock_client = _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        sentinel_tool = {
            "type": "function",
            "function": {"name": "sentinel_tool_should_not_appear"},
        }

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            result = client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[sentinel_tool],
            )

        assert result.content == "ok"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        # R2-10 contract: provider must NOT receive any tool defs on wire failure.
        # Either the key is absent (transport drops empty lists) or the value is [].
        tools_kwarg = call_kwargs.get("tools")
        assert not tools_kwarg, (
            f"Expected no tools in API call after wire failure, got {tools_kwarg!r}"
        )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_complete_logs_error_with_exc_info(self, mock_get_client, caplog):
        """Failure must be logged at ERROR level with exc_info attached."""
        wire_patch, _ = _patch_wire_tools_to_fail()
        _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ), caplog.at_level(logging.DEBUG):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        # Find the record(s) related to wire_tools_for_provider
        wire_records = [
            r for r in caplog.records
            if "wire_tools_for_provider" in r.getMessage()
        ]
        assert wire_records, "Expected a log record mentioning wire_tools_for_provider"
        for r in wire_records:
            assert r.levelno >= logging.ERROR, (
                f"Expected level >= ERROR (got {logging.getLevelName(r.levelno)}): "
                f"{r.getMessage()}"
            )
            assert r.exc_info is not None, (
                "Expected exc_info attached so the traceback is preserved"
            )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_no_warning_level_for_tool_wire_failure(self, mock_get_client, caplog):
        """No WARNING-level record for wire_tools_for_provider failure."""
        wire_patch, _ = _patch_wire_tools_to_fail()
        _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ), caplog.at_level(logging.DEBUG):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING
            and "wire_tools_for_provider" in r.getMessage()
        ]
        assert not warning_records, (
            f"Expected no WARNING for wire_tools_for_provider, got: "
            f"{[r.getMessage() for r in warning_records]}"
        )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_instance_records_last_tool_wire_error(self, mock_get_client):
        """After a failure, llm._last_tool_wire_error is set to the original exc."""
        wire_patch, sentinel = _patch_wire_tools_to_fail()
        _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            assert client._last_tool_wire_error is None
            client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        assert client._last_tool_wire_error is sentinel, (
            f"Expected _last_tool_wire_error to be the original exception, "
            f"got {client._last_tool_wire_error!r}"
        )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_complete_succeeds_without_tools_when_wire_fails(self, mock_get_client):
        """complete() must still return a NormalizedResponse after wire failure."""
        wire_patch, _ = _patch_wire_tools_to_fail()
        _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            result = client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        assert result.content == "ok"
        assert result.finish_reason == "stop"

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_complete_does_not_use_convert_tools(self, mock_get_client):
        """transport.convert_tools must NOT be called as a fallback (R2-10 fix)."""
        wire_patch, _ = _patch_wire_tools_to_fail()
        _patch_openai_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            client.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        # If convert_tools was called, its side_effect raises _SENTINEL_CONVERT_TOOLS_CALLED
        # and the call would have exploded before reaching us. Reaching this assertion
        # is itself the proof that convert_tools was NOT called.
        assert transport.convert_tools.call_count == 0, (
            f"transport.convert_tools was called {transport.convert_tools.call_count} "
            f"time(s); the R2-10 fix must not use it as a fallback"
        )


@pytest.mark.module_test
class TestStreamFallback:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_stream_uses_empty_tools_when_wire_fails(self, mock_get_client):
        """On wire_tools_for_provider failure, stream() must call the API with no tools.

        R2-10 contract: provider must NOT receive tool defs on wire failure
        (transport drops empty tool lists from kwargs).
        """
        wire_patch, _ = _patch_wire_tools_to_fail()
        mock_client = _patch_openai_stream_response(mock_get_client, content="streamed")
        transport = _make_transport_with_tracking_convert_tools()

        sentinel_tool = {
            "type": "function",
            "function": {"name": "sentinel_tool_should_not_appear"},
        }

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            result = client.stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[sentinel_tool],
            )

        assert result.content == "streamed"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        tools_kwarg = call_kwargs.get("tools")
        assert not tools_kwarg, (
            f"Expected no tools in API call after wire failure, got {tools_kwarg!r}"
        )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_stream_logs_error_with_exc_info(self, mock_get_client, caplog):
        """stream() failure must be logged at ERROR with exc_info attached."""
        wire_patch, _ = _patch_wire_tools_to_fail()
        _patch_openai_stream_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ), caplog.at_level(logging.DEBUG):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            client.stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        wire_records = [
            r for r in caplog.records
            if "wire_tools_for_provider" in r.getMessage()
        ]
        assert wire_records, "Expected a log record mentioning wire_tools_for_provider"
        for r in wire_records:
            assert r.levelno >= logging.ERROR, (
                f"Expected level >= ERROR (got {logging.getLevelName(r.levelno)}): "
                f"{r.getMessage()}"
            )
            assert r.exc_info is not None, (
                "Expected exc_info attached so the traceback is preserved"
            )

    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_stream_instance_records_last_tool_wire_error(self, mock_get_client):
        """After a stream() failure, _last_tool_wire_error is the original exc."""
        wire_patch, sentinel = _patch_wire_tools_to_fail()
        _patch_openai_stream_response(mock_get_client)
        transport = _make_transport_with_tracking_convert_tools()

        with wire_patch, patch(
            "butler.transport.get_transport", return_value=transport
        ):
            client = LLMClient(
                api_mode="chat_completions",
                model="gpt-4o",
                base_url="https://api.example.com/v1",
            )
            assert client._last_tool_wire_error is None
            client.stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}],
            )

        assert client._last_tool_wire_error is sentinel


@pytest.mark.module_test
class TestFallbackInitialState:
    def test_last_tool_wire_error_initially_none(self):
        client = LLMClient(api_mode="chat_completions", model="gpt-4o")
        assert client._last_tool_wire_error is None
