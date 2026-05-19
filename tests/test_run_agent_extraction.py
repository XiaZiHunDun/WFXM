"""Tests for Hermes run_agent.py second extraction."""

from __future__ import annotations

import pytest

from butler.core.message_sanitize import is_thinking_only_assistant, sanitize_api_messages
from butler.core.steer import apply_steer_to_tool_results, drain_steer, steer
from butler.core.tool_call_normalize import normalize_tool_calls, repair_tool_name
from butler.transport.content_sanitize import has_visible_content, strip_think_blocks
from butler.transport.types import ToolCall


@pytest.mark.unit
class TestContentSanitize:
    def test_strip_thinking_tags(self):
        raw = "hello <thinking>secret</thinking> world"
        assert "secret" not in strip_think_blocks(raw)
        assert "hello" in strip_think_blocks(raw)

    def test_has_visible_content_false_for_think_only(self):
        assert not has_visible_content("<thinking>only this</thinking>")


@pytest.mark.unit
class TestMessageSanitize:
    def test_stub_missing_tool_result(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            ]},
        ]
        out, repairs = sanitize_api_messages(msgs)
        assert repairs >= 1
        assert any(m.get("role") == "tool" and m.get("tool_call_id") == "c1" for m in out)

    def test_thinking_only_assistant(self):
        assert is_thinking_only_assistant({
            "role": "assistant",
            "content": "",
            "reasoning": "internal",
        })


@pytest.mark.unit
class TestToolNormalize:
    def test_repair_read_file(self):
        assert repair_tool_name("ReadFile") == "read_file"

    def test_dedupe_tool_calls(self):
        tcs = [
            ToolCall(id="1", name="read_file", arguments='{"path": "/a"}'),
            ToolCall(id="2", name="read_file", arguments='{"path": "/a"}'),
        ]
        out = normalize_tool_calls(tcs)
        assert len(out) == 1

    def test_cap_delegate(self):
        tcs = [
            ToolCall(
                id=str(i),
                name="delegate_task",
                arguments=f'{{"role": "dev", "task": "job{i}"}}',
            )
            for i in range(5)
        ]
        out = normalize_tool_calls(tcs)
        assert sum(1 for t in out if t.name == "delegate_task") == 2


@pytest.mark.unit
class TestSteer:
    def test_steer_applied_to_tool_result(self):
        steer("please focus on tests")
        msgs = [
            {"role": "assistant", "tool_calls": [{"id": "x", "function": {"name": "t"}}]},
            {"role": "tool", "tool_call_id": "x", "content": "ok"},
        ]
        assert apply_steer_to_tool_results(msgs, 1)
        assert "User guidance" in msgs[-1]["content"]
        assert drain_steer() is None
