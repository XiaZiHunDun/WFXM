"""PR-X3: canonical message IR + tool_wire."""

from __future__ import annotations

import pytest

from butler.core.message_ir import (
    CanonicalMessage,
    ContentBlock,
    BlockKind,
    convert_inbound,
    inbound_text_from_gateway,
    ir_to_openai_user,
    message_ir_enabled,
    openai_message_to_ir,
    validate_openai_sequence,
    wechat_inbound,
)
from butler.transport.tool_wire import (
    normalize_tool_calls_for_provider,
    tool_wire_enabled,
    wire_tools_for_provider,
)
from butler.transport.types import ToolCall


def test_wechat_inbound_primary_text():
    msg = wechat_inbound("你好", platform="wechat", external_id="u1")
    assert msg.primary_text() == "你好"
    assert msg.channel == "wechat"


def test_openai_message_to_ir_tool():
    ir = openai_message_to_ir({
        "role": "tool",
        "content": "ok",
        "tool_call_id": "call_1",
        "name": "read_file",
    })
    assert ir.role == "tool"
    assert any(b.kind == BlockKind.TOOL_RESULT for b in ir.blocks)


def test_validate_openai_sequence_orphan_tool():
    errs = validate_openai_sequence([
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "x", "content": "r"},
    ])
    assert errs


def test_inbound_text_from_gateway_passthrough(monkeypatch):
    monkeypatch.setenv("BUTLER_MESSAGE_IR", "1")
    assert message_ir_enabled()
    out = inbound_text_from_gateway(
        "  ping  ",
        platform="wechat",
        external_id="1",
        session_key="wx:1",
    )
    assert out.strip() == "ping"


def test_ir_to_openai_user():
    msg = CanonicalMessage(
        role="user",
        blocks=[ContentBlock(BlockKind.TEXT, text="hello")],
    )
    oai = ir_to_openai_user(msg)
    assert oai["role"] == "user"
    assert oai["content"] == "hello"


def test_normalize_tool_calls_anthropic_id():
    assert tool_wire_enabled()
    out = normalize_tool_calls_for_provider(
        "anthropic",
        [ToolCall(id=None, name="read_file", arguments="")],
    )
    assert out[0].id
    assert out[0].arguments == "{}"


def test_wire_tools_for_provider_openai():
    tools = [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "read",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    wired = wire_tools_for_provider("openai", tools, api_mode="openai")
    assert wired
