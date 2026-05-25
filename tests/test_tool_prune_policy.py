"""Tiered micro-prune by tool name."""

from __future__ import annotations

from butler.core.context_compressor import prune_tool_outputs
from butler.core.tool_prune_policy import (
    CLEARED_TOOL_RESULT_MESSAGE,
    classify_tool,
    prune_tool_message_content,
)


def test_classify_tools():
    assert classify_tool("read_file") == "clearable"
    assert classify_tool("grep") == "clearable"
    assert classify_tool("patch") == "preserve"
    assert classify_tool("delegate_task") == "preserve"
    assert classify_tool("unknown_tool") == "default"


def test_stale_clearable_cleared():
    big = "x" * 5000
    out = prune_tool_message_content(big, tool_name="grep", is_stale=True)
    assert out == CLEARED_TOOL_RESULT_MESSAGE


def test_recent_clearable_pruned_not_cleared():
    big = "y" * 5000
    out = prune_tool_message_content(big, tool_name="grep", is_stale=False)
    assert "[Tool output pruned" in out
    assert out != CLEARED_TOOL_RESULT_MESSAGE


def test_preserve_keeps_longer_summary():
    big = "z" * 3000
    out = prune_tool_message_content(big, tool_name="write_file", is_stale=True)
    assert "[Tool output pruned" in out
    assert len(out) > len(CLEARED_TOOL_RESULT_MESSAGE) + 100


def test_prune_messages_uses_tool_name_index(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_PRUNE_KEEP_RECENT", "1")
    messages: list[dict] = []
    for i in range(3):
        tid = f"c{i}"
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tid,
                    "type": "function",
                    "function": {"name": "grep", "arguments": "{}"},
                },
            ],
        })
        messages.append({"role": "tool", "tool_call_id": tid, "content": "a" * 5000})
    messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "c_last", "type": "function", "function": {"name": "patch", "arguments": "{}"}},
        ],
    })
    messages.append({"role": "tool", "tool_call_id": "c_last", "content": "b" * 5000})
    out = prune_tool_outputs(messages)
    assert out[1]["content"] == CLEARED_TOOL_RESULT_MESSAGE
    assert out[3]["content"] == CLEARED_TOOL_RESULT_MESSAGE
    assert "[Tool output pruned" in out[-1]["content"]
