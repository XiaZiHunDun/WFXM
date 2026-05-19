"""L1 unit tests for butler.transport.types."""

import json

import pytest

from butler.transport.types import (
    NormalizedResponse,
    ToolCall,
    Usage,
    build_tool_call,
    map_finish_reason,
)


@pytest.mark.unit
class TestToolCall:
    def test_creation(self):
        tc = ToolCall(id="call-1", name="read_file", arguments='{"path": "a.py"}')
        assert tc.id == "call-1"
        assert tc.name == "read_file"
        assert tc.arguments == '{"path": "a.py"}'

    def test_args_dict_valid_json(self):
        tc = ToolCall(id=None, name="run_shell", arguments='{"command": "pytest"}')
        assert tc.args_dict() == {"command": "pytest"}

    def test_args_dict_invalid_json_returns_empty(self):
        tc = ToolCall(id=None, name="run_shell", arguments="not-json{")
        assert tc.args_dict() == {}

    def test_function_property_returns_self(self):
        tc = ToolCall(id="x", name="edit_file", arguments="{}")
        assert tc.function is tc

    def test_type_property_returns_function(self):
        tc = ToolCall(id="x", name="edit_file", arguments="{}")
        assert tc.type == "function"


@pytest.mark.unit
class TestUsage:
    def test_creation_with_defaults(self):
        u = Usage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0
        assert u.cached_tokens == 0

    def test_total_tokens_explicit(self):
        u = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert u.prompt_tokens == 100
        assert u.completion_tokens == 50
        assert u.total_tokens == 150


@pytest.mark.unit
class TestNormalizedResponse:
    def test_basic_construction(self):
        resp = NormalizedResponse(content="hello", finish_reason="stop")
        assert resp.content == "hello"
        assert resp.finish_reason == "stop"
        assert resp.tool_calls is None

    def test_think_tag_extraction(self):
        raw = "Answer here.<think>step one</think> Done."
        resp = NormalizedResponse(content=raw)
        assert resp.reasoning == "step one"
        assert "redacted_thinking" not in (resp.content or "")
        assert "Answer here." in resp.content
        assert "Done." in resp.content

    def test_reasoning_merge_with_existing(self):
        raw = "<think>new thought</think>"
        resp = NormalizedResponse(content=raw, reasoning="prior")
        assert "prior" in resp.reasoning
        assert "new thought" in resp.reasoning

    def test_content_only_no_think(self):
        resp = NormalizedResponse(content="plain text")
        assert resp.content == "plain text"
        assert resp.reasoning is None

    def test_tool_only_no_content(self):
        tc = ToolCall(id="1", name="read_file", arguments="{}")
        resp = NormalizedResponse(content=None, tool_calls=[tc])
        assert resp.content is None
        assert len(resp.tool_calls) == 1

    def test_content_and_tools(self):
        tc = ToolCall(id="1", name="read_file", arguments="{}")
        resp = NormalizedResponse(content="see file", tool_calls=[tc])
        assert resp.content == "see file"
        assert resp.tool_calls[0].name == "read_file"

    def test_content_none_when_only_think_tags(self):
        resp = NormalizedResponse(content="<think>only thinking</think>")
        assert resp.content is None
        assert resp.reasoning == "only thinking"


@pytest.mark.unit
class TestBuildToolCall:
    def test_with_dict_args(self):
        tc = build_tool_call("id-1", "read_file", {"path": "main.py"})
        assert tc.name == "read_file"
        assert tc.args_dict() == {"path": "main.py"}

    def test_with_str_args(self):
        tc = build_tool_call("id-2", "run_shell", '{"command": "ls"}')
        assert tc.arguments == '{"command": "ls"}'
        assert tc.args_dict()["command"] == "ls"

    def test_with_none_args(self):
        tc = build_tool_call(None, "noop", None)
        assert tc.arguments == "{}"
        assert tc.args_dict() == {}


@pytest.mark.unit
class TestMapFinishReason:
    def test_none_returns_stop(self):
        assert map_finish_reason(None) == "stop"

    def test_known_mapping(self):
        mapping = {"tool_calls": "tool_calls", "length": "length"}
        assert map_finish_reason("tool_calls", mapping) == "tool_calls"

    def test_unknown_passthrough(self):
        assert map_finish_reason("custom_reason") == "custom_reason"
        assert map_finish_reason("weird", {"stop": "stop"}) == "weird"
