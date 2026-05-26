"""Tool schema sanitizer compatibility tests."""

import copy

from butler.transport.chat_completions import ChatCompletionsTransport
from butler.transport.anthropic_transport import AnthropicTransport
from butler.transport.types import NormalizedResponse
from butler.core.agent_loop import AgentLoop, LoopConfig, LoopStatus
from butler.transport.schema_sanitizer import sanitize_tool_schemas, strip_pattern_and_format


def _tool(name: str, parameters) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": parameters}}


def test_object_without_properties_gets_empty_properties():
    out = sanitize_tool_schemas([_tool("t", {"type": "object"})])

    assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}


def test_nested_bare_string_schema_gets_dict_schema():
    out = sanitize_tool_schemas([
        _tool("t", {
            "type": "object",
            "properties": {
                "payload": "object",
                "name": "string",
            },
        })
    ])

    props = out[0]["function"]["parameters"]["properties"]
    assert props["payload"] == {"type": "object", "properties": {}}
    assert props["name"] == {"type": "string"}


def test_nullable_type_array_collapses_to_single_type():
    out = sanitize_tool_schemas([
        _tool("t", {
            "type": "object",
            "properties": {"maybe": {"type": ["string", "null"]}},
        })
    ])

    prop = out[0]["function"]["parameters"]["properties"]["maybe"]
    assert prop["type"] == "string"
    assert prop["nullable"] is True


def test_nullable_anyof_collapses_to_non_null_branch():
    out = sanitize_tool_schemas([
        _tool("t", {
            "type": "object",
            "properties": {
                "maybe": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "optional value",
                }
            },
        })
    ])

    prop = out[0]["function"]["parameters"]["properties"]["maybe"]
    assert prop["type"] == "string"
    assert prop["nullable"] is True
    assert prop["description"] == "optional value"
    assert "anyOf" not in prop


def test_required_prunes_missing_properties():
    out = sanitize_tool_schemas([
        _tool("t", {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path", "missing"],
        })
    ])

    assert out[0]["function"]["parameters"]["required"] == ["path"]


def test_top_level_combinators_removed_but_nested_preserved():
    out = sanitize_tool_schemas([
        _tool("t", {
            "type": "object",
            "properties": {
                "mode": {
                    "oneOf": [{"type": "string"}, {"type": "integer"}],
                },
            },
            "oneOf": [{"required": ["mode"]}],
            "enum": ["bad"],
        })
    ])

    params = out[0]["function"]["parameters"]
    assert "oneOf" not in params
    assert "enum" not in params
    assert "oneOf" in params["properties"]["mode"]


def test_sanitizer_deep_copies_input():
    params = {"type": "object", "properties": {"payload": "object"}}
    original = [_tool("t", params)]

    out = sanitize_tool_schemas(original)

    assert original[0]["function"]["parameters"]["properties"]["payload"] == "object"
    assert out[0]["function"]["parameters"]["properties"]["payload"] == {
        "type": "object",
        "properties": {},
    }


def test_chat_transport_build_kwargs_sanitizes_tools():
    schema = {"type": "object", "properties": {"payload": "object"}}
    tools = [_tool("t", schema)]

    kwargs = ChatCompletionsTransport().build_kwargs(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
    )

    payload = kwargs["tools"][0]["function"]["parameters"]["properties"]["payload"]
    assert payload == {"type": "object", "properties": {}}
    assert tools[0]["function"]["parameters"]["properties"]["payload"] == "object"


def test_anthropic_transport_drops_nullable_hint():
    tools = [
        _tool("t", {
            "type": "object",
            "properties": {
                "maybe": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
        })
    ]

    kwargs = AnthropicTransport().build_kwargs(
        model="claude",
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
    )

    prop = kwargs["tools"][0]["input_schema"]["properties"]["maybe"]
    assert prop["type"] == "string"
    assert "nullable" not in prop


def test_strip_pattern_and_format_removes_schema_keywords_only():
    tools = [
        _tool("search", {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "literal property name"},
                "date": {"type": "string", "pattern": "\\d{4}-\\d{2}-\\d{2}"},
                "ts": {"type": "string", "format": "date-time"},
            },
            "required": ["pattern"],
        })
    ]

    _, stripped = strip_pattern_and_format(tools)

    props = tools[0]["function"]["parameters"]["properties"]
    assert stripped == 2
    assert "pattern" in props
    assert "pattern" not in props["date"]
    assert "format" not in props["ts"]


def test_agent_loop_retries_llamacpp_schema_error_with_stripped_schema(monkeypatch):
    class GrammarError(Exception):
        status_code = 400

    class FakeClient:
        provider_name = "local"
        model = "llama"

        def __init__(self):
            self.calls = []

        def complete(self, *, messages, tools, **kwargs):
            self.calls.append(copy.deepcopy(tools))
            date_schema = tools[0]["function"]["parameters"]["properties"]["date"]
            if "pattern" in date_schema:
                raise GrammarError("Unable to generate parser: json schema conversion failed")
            return NormalizedResponse(content="ok")

    monkeypatch.setenv("BUTLER_SCHEMA_OPTIMIZE", "0")
    client = FakeClient()
    loop = AgentLoop(
        client,
        tools=[
            _tool("t", {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "pattern": "\\d{4}-\\d{2}-\\d{2}"},
                },
            })
        ],
        config=LoopConfig(stream=False, max_retries=2),
    )

    result = loop.run("hi")

    assert result.status == LoopStatus.COMPLETED
    assert len(client.calls) == 2
    assert "pattern" in client.calls[0][0]["function"]["parameters"]["properties"]["date"]
    assert "pattern" not in client.calls[1][0]["function"]["parameters"]["properties"]["date"]
    assert result.diagnostics["schema_recovered"] is True
    assert result.diagnostics["schema_keywords_stripped"] == 1


def test_agent_loop_retries_schema_error_with_sanitized_schema_when_nothing_stripped(monkeypatch):
    class GrammarError(Exception):
        status_code = 400

    class FakeClient:
        provider_name = "local"
        model = "llama"

        def __init__(self):
            self.calls = []

        def complete(self, *, messages, tools, **kwargs):
            self.calls.append(copy.deepcopy(tools))
            maybe_schema = tools[0]["function"]["parameters"]["properties"]["maybe"]
            if "anyOf" in maybe_schema:
                raise GrammarError("Unable to generate parser: json schema conversion failed")
            return NormalizedResponse(content="ok")

    monkeypatch.setenv("BUTLER_SCHEMA_OPTIMIZE", "0")
    client = FakeClient()
    loop = AgentLoop(
        client,
        tools=[
            _tool("t", {
                "type": "object",
                "properties": {
                    "maybe": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
            })
        ],
        config=LoopConfig(stream=False, max_retries=2, retry_delay=0),
    )

    result = loop.run("hi")

    assert result.status == LoopStatus.COMPLETED
    assert len(client.calls) == 2
    assert "anyOf" in client.calls[0][0]["function"]["parameters"]["properties"]["maybe"]
    assert client.calls[1][0]["function"]["parameters"]["properties"]["maybe"]["type"] == "string"
