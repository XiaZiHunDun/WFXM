"""Tests for butler.ops.langfuse_tracer — opt-in LangFuse integration."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_tracer(monkeypatch):
    """Reset module state between tests."""
    import butler.ops.langfuse_tracer as mod
    mod._langfuse_client = None
    mod._initialised = False
    mod._thread_local_ctx.clear()
    monkeypatch.delenv("BUTLER_LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    yield
    mod._langfuse_client = None
    mod._initialised = False
    mod._thread_local_ctx.clear()


class TestLangfuseEnabled:
    def test_disabled_by_default(self):
        from butler.ops.langfuse_tracer import langfuse_enabled
        assert langfuse_enabled() is False

    def test_enabled_when_env_set(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        from butler.ops.langfuse_tracer import langfuse_enabled
        assert langfuse_enabled() is True

    def test_enabled_true_string(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "true")
        from butler.ops.langfuse_tracer import langfuse_enabled
        assert langfuse_enabled() is True


class TestGetClient:
    def test_returns_none_when_disabled(self):
        from butler.ops.langfuse_tracer import _get_client
        assert _get_client() is None

    def test_returns_none_when_import_fails(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod
        mod._initialised = False
        with patch.dict("sys.modules", {"langfuse": None}):
            mod._initialised = False
            result = mod._get_client()
        assert result is None

    def test_initialises_client_once(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        mock_langfuse_cls = MagicMock()
        mock_client = MagicMock()
        mock_langfuse_cls.return_value = mock_client

        mock_module = MagicMock()
        mock_module.Langfuse = mock_langfuse_cls

        import butler.ops.langfuse_tracer as mod
        mod._initialised = False
        with patch.dict("sys.modules", {"langfuse": mock_module}):
            result = mod._get_client()
        assert result is mock_client
        assert mod._initialised is True


class TestTracingContext:
    def test_noop_when_no_client(self):
        from butler.ops.langfuse_tracer import TracingContext
        ctx = TracingContext(session_key="test")
        assert ctx.active is False
        assert ctx.trace_id == ""
        ctx.on_llm_start([{"role": "user", "content": "hi"}])
        ctx.on_llm_complete(MagicMock(content="ok"))
        ctx.on_tool_start("test_tool", {"a": 1})
        ctx.on_tool_complete("test_tool", "result")
        ctx.finish()

    def test_active_with_mock_client(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-123"
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="wechat:u1")
        assert ctx.active is True
        assert ctx.trace_id == "trace-123"

    def test_llm_span_lifecycle(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_gen = MagicMock()
        mock_trace.generation.return_value = mock_gen
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="s1")
        messages = [{"role": "user", "content": "hello"}]
        ctx.on_llm_start(messages)
        mock_trace.generation.assert_called_once()

        response = MagicMock(spec=["content", "usage", "finish_reason", "tool_calls"])
        response.content = "answer"
        response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        response.finish_reason = "stop"
        response.tool_calls = None
        ctx.on_llm_complete(response)
        mock_gen.end.assert_called_once()

    def test_tool_span_lifecycle(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="s1")
        ctx.on_tool_start("read_file", {"path": "/a.txt"})
        mock_trace.span.assert_called_once()
        ctx.on_tool_complete("read_file", "file contents")
        mock_span.end.assert_called_once()


class TestPublicAPI:
    def test_langfuse_callbacks_empty_when_disabled(self):
        from butler.ops.langfuse_tracer import langfuse_callbacks
        assert langfuse_callbacks(session_key="s1") == {}

    def test_langfuse_callbacks_returns_dict_when_enabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "t-1"
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        cbs = mod.langfuse_callbacks(session_key="wechat:u1")
        assert "on_llm_start" in cbs
        assert "on_llm_complete" in cbs
        assert "on_tool_start" in cbs
        assert "on_tool_complete" in cbs

    def test_flush_and_shutdown_noop_when_disabled(self):
        from butler.ops.langfuse_tracer import flush_langfuse, shutdown_langfuse
        flush_langfuse()
        shutdown_langfuse()

    def test_end_trace_lifecycle(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "t-2"
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        mod.start_trace(session_key="s1")
        ctx = mod.get_current_trace(session_key="s1")
        assert ctx is not None
        assert ctx.active is True

        mock_result = MagicMock(
            status="completed", iterations=3, total_tokens=500,
            tool_calls_made=2, elapsed_seconds=1.5,
        )
        mod.end_trace(session_key="s1", result=mock_result)
        assert mod.get_current_trace(session_key="s1") is None
        mock_trace.update.assert_called_once()


class TestM2DeepTracing:
    """M2 deep tracing: memory prefetch, gateway inbound/outbound."""

    def test_memory_prefetch_span(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="s1")
        ctx.on_memory_prefetch("测试查询", hit=True, result_count=3, chars=200)
        mock_trace.span.assert_called_once()
        mock_span.end.assert_called_once()

    def test_memory_write_span(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="s1")
        ctx.on_memory_write("experience", success=True)
        mock_trace.span.assert_called_once()
        mock_span.end.assert_called_once()

    def test_gateway_inbound_outbound(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
        import butler.ops.langfuse_tracer as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace
        mod._langfuse_client = mock_client
        mod._initialised = True

        ctx = mod.TracingContext(session_key="s1")
        ctx.on_gateway_inbound("wechat:u1", "wechat", 42)
        ctx.on_gateway_outbound("wechat:u1", 300, 2.5)
        assert mock_trace.span.call_count == 2

    def test_noop_when_no_trace(self):
        from butler.ops.langfuse_tracer import TracingContext
        ctx = TracingContext(session_key="nope")
        ctx.on_memory_prefetch("q", hit=False)
        ctx.on_memory_write("exp", success=True)
        ctx.on_gateway_inbound("s", "p", 0)
        ctx.on_gateway_outbound("s", 0)


class TestChainCallbacks:
    def test_chain_calls_both(self):
        from butler.gateway.locked_phases import _chain_callbacks
        from butler.core.loop_types import LoopCallbacks

        calls = []
        base = LoopCallbacks(on_llm_start=lambda msgs: calls.append(("base", msgs)))
        extra = LoopCallbacks(on_llm_start=lambda msgs: calls.append(("extra", msgs)))
        chained = _chain_callbacks(base, extra)
        chained.on_llm_start([{"role": "user"}])
        assert len(calls) == 2
        assert calls[0][0] == "base"
        assert calls[1][0] == "extra"

    def test_chain_none_base(self):
        from butler.gateway.locked_phases import _chain_callbacks
        from butler.core.loop_types import LoopCallbacks

        extra = LoopCallbacks(on_llm_start=lambda msgs: None)
        result = _chain_callbacks(None, extra)
        assert result is extra

    def test_chain_none_extra(self):
        from butler.gateway.locked_phases import _chain_callbacks
        from butler.core.loop_types import LoopCallbacks

        base = LoopCallbacks(on_llm_start=lambda msgs: None)
        result = _chain_callbacks(base, None)
        assert result is base
