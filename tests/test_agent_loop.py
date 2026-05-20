"""L2 module tests for butler.core.agent_loop."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from butler.core.agent_loop import (
    AgentLoop,
    LoopCallbacks,
    LoopConfig,
    LoopStatus,
)
from butler.transport.types import ToolCall, Usage, build_tool_call


def _usage(prompt: int = 10, completion: int = 5) -> Usage:
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def _text_response(content: str = "done", *, tokens: int = 15) -> object:
    from butler.transport.types import NormalizedResponse

    return NormalizedResponse(
        content=content,
        usage=_usage(tokens - 5, 5) if tokens else _usage(),
    )


def _tool_response(
    name: str,
    args: dict | None = None,
    *,
    content: str | None = None,
    tool_id: str | None = "call_1",
) -> object:
    from butler.transport.types import NormalizedResponse

    tc = build_tool_call(tool_id, name, args or {})
    return NormalizedResponse(
        content=content,
        tool_calls=[tc],
        usage=_usage(),
    )


@pytest.mark.module_test
class TestAgentLoopConstruction:
    def test_default_config_values(self, mock_llm_client):
        loop = AgentLoop(mock_llm_client)
        assert loop.config.max_iterations == 30
        assert loop.config.max_retries == 3
        assert loop.config.retry_delay == 1.0
        assert loop.config.retry_max_delay == 30.0
        assert loop.config.retry_jitter_ratio == 0.25
        assert loop.config.max_context_tokens == 128000
        assert loop.config.stream is True

    def test_custom_loop_config_all_fields(self, mock_llm_client):
        cfg = LoopConfig(
            max_iterations=5,
            max_retries=2,
            retry_delay=0.5,
            max_context_tokens=1000,
            stream=False,
        )
        loop = AgentLoop(mock_llm_client, config=cfg)
        assert loop.config.max_iterations == 5
        assert loop.config.max_retries == 2
        assert loop.config.retry_delay == 0.5
        assert loop.config.max_context_tokens == 1000
        assert loop.config.stream is False

    def test_no_system_prompt_no_system_message(self, mock_llm_client):
        loop = AgentLoop(mock_llm_client, system_prompt="")
        loop.run("hi")
        roles = [m["role"] for m in loop.messages]
        assert "system" not in roles

    def test_no_tools_empty_tools_list(self, mock_llm_client):
        loop = AgentLoop(mock_llm_client, tools=None)
        assert loop.tools == []


@pytest.mark.module_test
class TestAgentLoopRun:
    def test_pure_text_reply_completed(self, mock_llm_client, mock_llm_response):
        mock_llm_client.complete.return_value = mock_llm_response(content="hello world")
        loop = AgentLoop(mock_llm_client, config=LoopConfig(stream=False))
        result = loop.run("say hi")
        assert result.status == LoopStatus.COMPLETED
        assert result.final_response == "hello world"
        assert result.iterations == 1
        assert result.tool_calls_made == 0

    def test_single_tool_call_then_text(self, mock_llm_client):
        mock_llm_client.complete.side_effect = [
            _tool_response("echo", {"x": 1}),
            _text_response("tool done"),
        ]
        dispatched = []

        def dispatcher(name, args):
            dispatched.append((name, args))
            return "ok"

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=dispatcher,
            config=LoopConfig(stream=False),
        )
        result = loop.run("run tool")
        assert result.status == LoopStatus.COMPLETED
        assert result.final_response == "tool done"
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        assert dispatched == [("echo", {"x": 1})]

    def test_multiple_tool_calls_one_response(self, mock_llm_client):
        from butler.transport.types import NormalizedResponse

        tc1 = build_tool_call("c1", "tool_a", {})
        tc2 = build_tool_call("c2", "tool_b", {})
        mock_llm_client.complete.side_effect = [
            NormalizedResponse(tool_calls=[tc1, tc2], usage=_usage()),
            _text_response("both done"),
        ]
        calls = []

        def dispatcher(name, args):
            calls.append(name)
            return f"result-{name}"

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=dispatcher,
            config=LoopConfig(stream=False),
        )
        result = loop.run("multi")
        assert result.status == LoopStatus.COMPLETED
        assert result.iterations == 2
        assert result.tool_calls_made == 2
        assert set(calls) == {"tool_a", "tool_b"}

    def test_chain_of_three_tool_rounds(self, mock_llm_client):
        mock_llm_client.complete.side_effect = [
            _tool_response("t1", {}),
            _tool_response("t2", {}),
            _tool_response("t3", {}),
            _text_response("finished"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "ok",
            config=LoopConfig(stream=False),
        )
        result = loop.run("chain")
        assert result.status == LoopStatus.COMPLETED
        assert result.iterations == 4
        assert result.tool_calls_made == 3

    def test_max_iterations_exhausted_tool_limit(self, mock_llm_client):
        mock_llm_client.complete.return_value = _tool_response("loop", {})
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "ok",
            config=LoopConfig(max_iterations=2, stream=False),
        )
        result = loop.run("keep going")
        assert result.status == LoopStatus.TOOL_LIMIT
        assert result.iterations == 2

    def test_llm_exception_retry_exhausted_error(self, mock_llm_client):
        mock_llm_client.complete.side_effect = RuntimeError("api down")
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_retries=3, retry_delay=0, stream=False),
        )
        with patch("butler.core.agent_loop.time.sleep"):
            result = loop.run("fail")
        assert result.status == LoopStatus.ERROR
        assert mock_llm_client.complete.call_count == 3

    def test_llm_fails_once_then_succeeds(self, mock_llm_client, mock_llm_response):
        mock_llm_client.complete.side_effect = [
            RuntimeError("transient"),
            mock_llm_response(content="recovered"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_retries=3, retry_delay=0, stream=False),
        )
        with patch("butler.core.agent_loop.time.sleep"):
            result = loop.run("retry me")
        assert result.status == LoopStatus.COMPLETED
        assert result.final_response == "recovered"

    def test_retry_sleep_uses_exponential_backoff(self, mock_llm_client):
        mock_llm_client.complete.side_effect = RuntimeError("api down")
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(
                max_retries=3,
                retry_delay=0.5,
                retry_max_delay=10,
                retry_jitter_ratio=0,
                stream=False,
            ),
        )

        with patch("butler.core.agent_loop.time.sleep") as sleep:
            result = loop.run("fail")

        assert result.status == LoopStatus.ERROR
        assert [call.args[0] for call in sleep.call_args_list] == [0.5, 1.0]

    def test_content_and_tool_calls_tool_calls_priority(self, mock_llm_client):
        from butler.transport.types import NormalizedResponse

        tc = build_tool_call("id1", "my_tool", {})
        mock_llm_client.complete.side_effect = [
            NormalizedResponse(
                content="should not be final yet",
                tool_calls=[tc],
                usage=_usage(),
            ),
            _text_response("after tool"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "done",
            config=LoopConfig(stream=False),
        )
        result = loop.run("mixed")
        assert result.status == LoopStatus.COMPLETED
        assert result.final_response == "after tool"
        assert result.iterations == 2
        assert result.tool_calls_made == 1

    def test_token_accumulation_across_iterations(self, mock_llm_client):
        from butler.transport.types import NormalizedResponse

        mock_llm_client.complete.side_effect = [
            NormalizedResponse(
                tool_calls=[build_tool_call("a", "t", {})],
                usage=Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
            ),
            NormalizedResponse(
                content="done",
                usage=Usage(prompt_tokens=50, completion_tokens=10, total_tokens=60),
            ),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "x",
            config=LoopConfig(stream=False),
        )
        result = loop.run("tokens")
        assert result.total_tokens == 180

    def test_dispatcher_exception_is_enveloped_and_audited(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            _tool_response("explode", {"x": 1}),
            _text_response("done"),
        ]

        def dispatcher(_name, _args):
            raise RuntimeError("boom")

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=dispatcher,
            config=LoopConfig(stream=False),
        )
        result = loop.run("run tool")

        assert result.status == LoopStatus.COMPLETED
        tool_msg = next(msg for msg in loop.messages if msg["role"] == "tool")
        data = json.loads(tool_msg["content"])
        assert data["ok"] is False
        assert data["tool"] == "explode"
        assert data["code"] == "TOOL_DISPATCH_ERROR"
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "explode"
        assert event["code"] == "TOOL_DISPATCH_ERROR"

    def test_custom_dispatcher_error_json_is_enveloped_and_audited(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            _tool_response("custom_tool", {"x": 1}),
            _text_response("done"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: json.dumps({"error": "custom failed"}),
            config=LoopConfig(stream=False),
        )

        loop.run("run custom")

        tool_msg = next(msg for msg in loop.messages if msg["role"] == "tool")
        data = json.loads(tool_msg["content"])
        assert data["ok"] is False
        assert data["tool"] == "custom_tool"
        assert data["code"] == "TOOL_ERROR"
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "custom_tool"
        assert event["code"] == "TOOL_ERROR"

    def test_guardrail_warn_keeps_tool_result_json_envelope(self, mock_llm_client):
        from butler.tool_guardrails import GuardrailConfig, ToolCallGuardrailController

        mock_llm_client.complete.side_effect = [
            _tool_response("read_file", {"path": "same.py"}),
            _tool_response("read_file", {"path": "same.py"}),
            _text_response("done"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: json.dumps({"error": "not found"}),
            config=LoopConfig(stream=False, max_iterations=5),
        )
        loop._guardrails = ToolCallGuardrailController(
            GuardrailConfig(
                exact_failure_warn_after=2,
                exact_failure_block_after=99,
                same_tool_failure_warn_after=99,
                same_tool_failure_halt_after=99,
            )
        )

        loop.run("repeat failing read for warn")
        warn_msgs = [
            json.loads(msg["content"])
            for msg in loop.messages
            if msg["role"] == "tool"
            and json.loads(msg["content"]).get("guardrail", {}).get("action") == "warn"
        ]
        assert len(warn_msgs) >= 1
        assert warn_msgs[0]["guardrail"]["code"] == "repeated_exact_failure_warning"
        assert warn_msgs[0]["tool"] == "read_file"

    def test_guardrail_block_is_enveloped_and_audited(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            *[_tool_response("read_file", {"path": "missing.py"}) for _ in range(6)],
            _text_response("done"),
        ]

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: json.dumps({"error": "missing"}),
            config=LoopConfig(stream=False, max_iterations=7),
        )
        result = loop.run("repeat failing read")

        assert result.status == LoopStatus.COMPLETED
        events = get_tool_audit_events()
        assert any(event["code"] == "TOOL_GUARDRAIL_BLOCKED" for event in events)
        blocked_msg = [
            json.loads(msg["content"])
            for msg in loop.messages
            if msg["role"] == "tool" and "guardrail" in msg["content"]
        ][-1]
        assert blocked_msg["ok"] is False
        assert blocked_msg["tool"] == "read_file"
        assert blocked_msg["code"] == "TOOL_GUARDRAIL_BLOCKED"

    def test_parallel_tools_with_guardrails_accumulate_failures_thread_safely(
        self, mock_llm_client
    ):
        from butler.transport.types import NormalizedResponse
        from butler.tool_guardrails import GuardrailConfig, ToolCallGuardrailController

        tool_calls = [
            build_tool_call(f"c{i}", "search_files", {"query": f"q{i}"})
            for i in range(8)
        ]
        mock_llm_client.complete.side_effect = [
            NormalizedResponse(tool_calls=tool_calls, usage=_usage()),
            _text_response("done"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: json.dumps({"error": "parallel fail"}),
            config=LoopConfig(stream=False, enable_parallel_tools=True),
        )
        loop._guardrails = ToolCallGuardrailController(
            GuardrailConfig(
                same_tool_failure_halt_after=8,
                same_tool_failure_warn_after=99,
                exact_failure_warn_after=99,
                exact_failure_block_after=99,
            )
        )

        loop.run("parallel guardrail failures")
        assert loop._guardrails.halt_decision is not None
        assert loop._guardrails.halt_decision.action == "halt"
        assert loop._guardrails.halt_decision.tool_name == "search_files"
        tool_msgs = [msg for msg in loop.messages if msg["role"] == "tool"]
        assert len(tool_msgs) == 8

    def test_guardrail_halt_is_enveloped_and_audited(self, mock_llm_client):
        from butler.tool_guardrails import GuardrailConfig, ToolCallGuardrailController
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            _tool_response("read_file", {"path": "missing.py"}),
            _tool_response("read_file", {"path": "missing.py"}),
            _tool_response("read_file", {"path": "missing.py"}),
            _text_response("done"),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: json.dumps({"error": "missing"}),
            config=LoopConfig(stream=False, max_iterations=5),
        )
        loop._guardrails = ToolCallGuardrailController(
            GuardrailConfig(
                same_tool_failure_halt_after=3,
                same_tool_failure_warn_after=99,
                exact_failure_warn_after=99,
                exact_failure_block_after=99,
            )
        )

        loop.run("repeat failing read until halt")

        halt_events = [
            event for event in get_tool_audit_events() if event["code"] == "TOOL_GUARDRAIL_HALT"
        ]
        assert len(halt_events) == 1
        halt_msg = [
            json.loads(msg["content"])
            for msg in loop.messages
            if msg["role"] == "tool" and '"action": "halt"' in msg["content"]
        ][-1]
        assert halt_msg["ok"] is False
        assert halt_msg["tool"] == "read_file"
        assert halt_msg["code"] == "TOOL_GUARDRAIL_HALT"
        assert halt_msg["guardrail"]["action"] == "halt"
        assert "Tool loop hard stop" not in json.dumps(halt_msg)

    def test_sequential_multi_tool_batch_interrupt_fills_remaining_tool_messages_and_audit(
        self, mock_llm_client
    ):
        from butler.transport.types import NormalizedResponse
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        tc1 = build_tool_call("c1", "tool_a", {})
        tc2 = build_tool_call("c2", "tool_b", {})
        tc3 = build_tool_call("c3", "tool_c", {})
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: "should not run",
            config=LoopConfig(stream=False, enable_parallel_tools=False),
        )
        llm_calls = {"count": 0}

        def complete(**_kwargs):
            llm_calls["count"] += 1
            if llm_calls["count"] == 1:
                loop._interrupt_check = lambda: True
                return NormalizedResponse(tool_calls=[tc1, tc2, tc3], usage=_usage())
            return _text_response("done")

        mock_llm_client.complete.side_effect = complete

        loop.run("multi interrupt before dispatch")
        tool_msgs = [msg for msg in loop.messages if msg["role"] == "tool"]
        assert len(tool_msgs) == 3
        assert {json.loads(msg["content"])["code"] for msg in tool_msgs} == {"TOOL_INTERRUPTED"}
        assert {msg["tool_call_id"] for msg in tool_msgs} == {"c1", "c2", "c3"}
        events = get_tool_audit_events()
        assert len(events) == 3
        assert {event["tool"] for event in events} == {"tool_a", "tool_b", "tool_c"}

    def test_sequential_multi_tool_batch_interrupt_after_first_completes(
        self, mock_llm_client
    ):
        from butler.transport.types import NormalizedResponse
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        tc1 = build_tool_call("c1", "tool_a", {})
        tc2 = build_tool_call("c2", "tool_b", {})
        tc3 = build_tool_call("c3", "tool_c", {})
        dispatched: list[str] = []

        def dispatcher(name, _args):
            dispatched.append(name)
            return json.dumps({"ok": True})

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=dispatcher,
            config=LoopConfig(stream=False, enable_parallel_tools=False),
        )
        llm_calls = {"count": 0}

        def complete(**_kwargs):
            llm_calls["count"] += 1
            if llm_calls["count"] == 1:
                loop._interrupt_check = lambda: len(dispatched) >= 1
                return NormalizedResponse(tool_calls=[tc1, tc2, tc3], usage=_usage())
            loop._interrupt_check = lambda: False
            return _text_response("done")

        mock_llm_client.complete.side_effect = complete

        loop.run("multi interrupt after first")
        tool_msgs = [msg for msg in loop.messages if msg["role"] == "tool"]
        assert len(tool_msgs) == 3
        assert dispatched == ["tool_a"]
        first = json.loads(tool_msgs[0]["content"])
        assert first.get("ok") is True
        for msg in tool_msgs[1:]:
            assert json.loads(msg["content"])["code"] == "TOOL_INTERRUPTED"
        interrupted_events = [
            event for event in get_tool_audit_events() if event["code"] == "TOOL_INTERRUPTED"
        ]
        assert len(interrupted_events) == 2
        assert {event["tool"] for event in interrupted_events} == {"tool_b", "tool_c"}

    def test_sequential_interrupt_is_enveloped_and_audited(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda _n, _a: "should not run",
            config=LoopConfig(stream=False, enable_parallel_tools=False),
        )
        original_check = loop._interrupt_check
        called = {"count": 0}

        def complete(**_kwargs):
            called["count"] += 1
            if called["count"] == 1:
                loop._interrupt_check = lambda: True
                return _tool_response("read_file", {"path": "a.py"})
            return _text_response("done")

        mock_llm_client.complete.side_effect = complete
        loop._interrupt_check = original_check

        loop.run("interrupt tool")
        tool_msg = next(msg for msg in loop.messages if msg["role"] == "tool")
        data = json.loads(tool_msg["content"])
        assert data["ok"] is False
        assert data["tool"] == "read_file"
        assert data["code"] == "TOOL_INTERRUPTED"
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "read_file"
        assert event["code"] == "TOOL_INTERRUPTED"


@pytest.mark.module_test
class TestAgentLoopCallbacks:
    def test_on_llm_start_fires_with_message_count(self, mock_llm_client, mock_llm_response):
        mock_llm_client.complete.return_value = mock_llm_response()
        seen = []

        callbacks = LoopCallbacks(on_llm_start=lambda msgs: seen.append(len(msgs)))
        loop = AgentLoop(
            mock_llm_client,
            system_prompt="sys",
            callbacks=callbacks,
            config=LoopConfig(stream=False),
        )
        loop.run("hello")
        assert len(seen) == 1
        assert seen[0] >= 2

    def test_on_llm_complete_fires_with_response(self, mock_llm_client, mock_llm_response):
        resp = mock_llm_response(content="cb-test")
        mock_llm_client.complete.return_value = resp
        completed = []

        callbacks = LoopCallbacks(on_llm_complete=lambda r: completed.append(r))
        loop = AgentLoop(
            mock_llm_client,
            callbacks=callbacks,
            config=LoopConfig(stream=False),
        )
        loop.run("hi")
        assert len(completed) == 1
        assert completed[0].content == "cb-test"

    def test_on_tool_start_and_complete(self, mock_llm_client):
        mock_llm_client.complete.side_effect = [
            _tool_response("grep", {"pattern": "x"}),
            _text_response(),
        ]
        starts, completes = [], []

        callbacks = LoopCallbacks(
            on_tool_start=lambda name, args: starts.append((name, args)),
            on_tool_complete=lambda name, result: completes.append((name, result)),
        )
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "found",
            callbacks=callbacks,
            config=LoopConfig(stream=False),
        )
        loop.run("search")
        assert starts == [("grep", {"pattern": "x"})]
        assert completes == [("grep", "found")]

    def test_on_error_when_llm_fails(self, mock_llm_client):
        mock_llm_client.complete.side_effect = ValueError("boom")
        errors = []
        callbacks = LoopCallbacks(on_error=lambda exc, attempt: errors.append((type(exc), attempt)))
        loop = AgentLoop(
            mock_llm_client,
            callbacks=callbacks,
            config=LoopConfig(max_retries=2, retry_delay=0, stream=False),
        )
        with patch("butler.core.agent_loop.time.sleep"):
            loop.run("err")
        assert len(errors) == 2
        assert errors[0] == (ValueError, 1)
        assert errors[1] == (ValueError, 2)

    def test_should_continue_false_stops_early(self, mock_llm_client):
        mock_llm_client.complete.return_value = _tool_response(
            "stop_tool", {}, content="partial answer"
        )
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "ok",
            callbacks=LoopCallbacks(should_continue=lambda it, resp: False),
            config=LoopConfig(stream=False),
        )
        result = loop.run("stop early")
        assert result.status == LoopStatus.COMPLETED
        assert result.final_response == "partial answer"
        assert result.iterations == 1


@pytest.mark.module_test
class TestAgentLoopContext:
    def test_multiple_run_accumulates_messages(self, mock_llm_client, mock_llm_response):
        mock_llm_client.complete.return_value = mock_llm_response()
        loop = AgentLoop(mock_llm_client, system_prompt="sys", config=LoopConfig(stream=False))
        loop.run("first")
        loop.run("second")
        user_msgs = [m["content"] for m in loop.messages if m["role"] == "user"]
        assert user_msgs == ["first", "second"]

    def test_reset_clears_messages(self, mock_llm_client, mock_llm_response):
        mock_llm_client.complete.return_value = mock_llm_response()
        loop = AgentLoop(mock_llm_client, system_prompt="sys", config=LoopConfig(stream=False))
        loop.run("hello")
        loop.reset()
        assert loop.messages == []

    def test_compress_context_short_messages_unchanged(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=100000, stream=False),
        )
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        assert loop._compress_context(msgs) == msgs

    def test_compress_context_long_drops_middle(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=5, stream=False),
        )
        msgs = [{"role": "system", "content": "system prompt"}]
        for i in range(20):
            msgs.append({"role": "user", "content": "x" * 200})
        compressed = loop._compress_context(msgs)
        assert any(m.get("role") == "system" for m in compressed)
        from butler.core.context_compressor import SUMMARY_PREFIX
        assert len(compressed) < len(msgs) or any(
            SUMMARY_PREFIX[:20] in str(m.get("content", "")) for m in compressed
        )

    def test_hygiene_compress_skips_below_threshold(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=1000, stream=False),
        )
        loop.messages = [{"role": "user", "content": "short"} for _ in range(20)]

        with patch.object(loop, "_compress_context", wraps=loop._compress_context) as compress:
            did = loop.hygiene_compress_if_needed()

        assert did is False
        compress.assert_not_called()

    def test_hygiene_diagnostics_do_not_keep_stale_fields(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=1000, stream=False),
        )
        loop.diagnostics = {
            "hygiene_compressed": True,
            "hygiene_estimated_tokens": 900,
            "hygiene_messages_after": 1,
        }
        loop.messages = [{"role": "user", "content": "short"}]

        did = loop.hygiene_compress_if_needed()

        assert did is False
        assert loop.diagnostics["hygiene_compressed"] is False
        assert "hygiene_estimated_tokens" not in loop.diagnostics
        assert "hygiene_messages_after" not in loop.diagnostics

    def test_hygiene_compress_uses_85_percent_threshold(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=100, stream=False),
        )
        loop.messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]
        compressed = [{"role": "user", "content": "summary"}]

        with patch.object(loop, "_compress_context", return_value=compressed) as compress:
            did = loop.hygiene_compress_if_needed()

        assert did is True
        assert loop.messages == compressed
        compress.assert_called_once()
        assert compress.call_args.kwargs["threshold_ratio"] == 0.85
        assert loop.diagnostics["hygiene_compressed"] is True
        assert loop.diagnostics["hygiene_messages_before"] == 20
        assert loop.diagnostics["hygiene_messages_after"] == 1

    def test_hygiene_compress_hard_message_limit(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=100000, stream=False),
        )
        loop.messages = [{"role": "user", "content": f"short {i}"} for i in range(20)]

        with patch("butler.core.context_compressor.auxiliary_complete", return_value="summary"):
            did = loop.hygiene_compress_if_needed(hard_message_limit=5)

        assert did is True
        assert len(loop.messages) < 20

    def test_hygiene_estimate_counts_tool_calls(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=100, stream=False),
        )
        loop.messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{i}",
                        "type": "function",
                        "function": {"name": "big", "arguments": "x" * 1000},
                    }
                ],
            }
            for i in range(20)
        ]

        with patch("butler.core.context_compressor.auxiliary_complete", return_value="summary"):
            did = loop.hygiene_compress_if_needed()

        assert did is True
        assert len(loop.messages) < 20

    def test_hygiene_compresses_short_high_token_history(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            config=LoopConfig(max_context_tokens=100, stream=False),
        )
        loop.messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{i}",
                        "type": "function",
                        "function": {"name": "big", "arguments": "x" * 1000},
                    }
                ],
            }
            for i in range(6)
        ]

        with patch("butler.core.context_compressor.auxiliary_complete", return_value="summary"):
            did = loop.hygiene_compress_if_needed()

        assert did is True
        assert len(loop.messages) < 6

    def test_hygiene_compresses_gateway_system_plus_three_large_tool_calls(self, mock_llm_client):
        loop = AgentLoop(
            mock_llm_client,
            system_prompt="sys",
            config=LoopConfig(max_context_tokens=100, stream=False),
        )
        loop.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "please call tool"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "big", "arguments": "x" * 1000},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {"name": "big", "arguments": "y" * 1000},
                    }
                ],
            },
        ]

        before_tokens = loop._estimate_tokens(loop.messages)

        with patch("butler.core.context_compressor.auxiliary_complete", return_value="summary"):
            did = loop.hygiene_compress_if_needed()

        assert did is True
        assert loop._estimate_tokens(loop.messages) < before_tokens

    def test_estimate_tokens_english(self, mock_llm_client):
        loop = AgentLoop(mock_llm_client)
        msgs = [{"role": "user", "content": "hello world"}]
        assert loop._estimate_tokens(msgs) >= len("hello world") // 4

    def test_estimate_tokens_chinese(self, mock_llm_client):
        loop = AgentLoop(mock_llm_client)
        text = "你好世界测试"
        msgs = [{"role": "user", "content": text}]
        assert loop._estimate_tokens(msgs) >= len(text) // 4


@pytest.mark.module_test
class TestAgentLoopToolDispatch:
    def test_no_dispatcher_returns_error_string(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            _tool_response("missing", {}),
            _text_response(),
        ]
        loop = AgentLoop(mock_llm_client, config=LoopConfig(stream=False))
        loop.run("no dispatcher")
        tool_msgs = [m for m in loop.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert "No tool dispatcher" in tool_msgs[0]["content"]
        data = json.loads(tool_msgs[0]["content"])
        assert data["ok"] is False
        assert data["tool"] == "missing"
        assert data["code"] == "TOOL_DISPATCH_ERROR"
        assert get_tool_audit_events()[-1]["code"] == "TOOL_DISPATCH_ERROR"

    def test_dispatcher_exception_captured_as_tool_result(self, mock_llm_client):
        from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events

        reset_tool_audit_events()
        mock_llm_client.complete.side_effect = [
            _tool_response("bad", {}),
            _text_response(),
        ]

        def boom(name, args):
            raise RuntimeError("tool exploded")

        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=boom,
            config=LoopConfig(stream=False),
        )
        loop.run("boom")
        tool_msgs = [m for m in loop.messages if m["role"] == "tool"]
        assert "Tool execution failed" in tool_msgs[0]["content"]
        data = json.loads(tool_msgs[0]["content"])
        assert data["ok"] is False
        assert data["tool"] == "bad"
        assert data["code"] == "TOOL_DISPATCH_ERROR"
        assert get_tool_audit_events()[-1]["code"] == "TOOL_DISPATCH_ERROR"

    def test_tool_call_missing_id_generates_uuid(self, mock_llm_client):
        from butler.transport.types import NormalizedResponse

        tc = ToolCall(id=None, name="anon", arguments="{}")
        mock_llm_client.complete.side_effect = [
            NormalizedResponse(tool_calls=[tc], usage=_usage()),
            _text_response(),
        ]
        loop = AgentLoop(
            mock_llm_client,
            tool_dispatcher=lambda n, a: "ok",
            config=LoopConfig(stream=False),
        )
        loop.run("no id")
        assistant_msgs = [m for m in loop.messages if m.get("tool_calls")]
        assert assistant_msgs
        call_id = assistant_msgs[0]["tool_calls"][0]["id"]
        assert call_id.startswith("call_")
