"""Tests for OMO tool-pair repair."""

from __future__ import annotations


from butler.core.tool_pair_repair import (
    PLACEHOLDER_CONTENT,
    repair_tool_pairs,
    tool_pair_repair_enabled,
)


def test_tool_pair_repair_inserts_synthetic_result(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_PAIR_REPAIR", "1")
    assert tool_pair_repair_enabled()
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"role": "user", "content": "next"},
    ]
    repaired, count = repair_tool_pairs(messages)
    assert count == 1
    assert repaired[1]["role"] == "tool"
    assert repaired[1]["tool_call_id"] == "call_1"
    assert PLACEHOLDER_CONTENT in repaired[1]["content"]


def test_tool_pair_repair_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_PAIR_REPAIR", "0")
    messages = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_1", "function": {"name": "x", "arguments": "{}"}}],
        },
    ]
    repaired, count = repair_tool_pairs(messages)
    assert count == 0
    assert len(repaired) == 1


def test_gateway_pre_turn_repair_unblocks_sequence(monkeypatch):
    from butler.gateway.locked_phases import LockedTurnState, _phase_validate_loop_messages

    monkeypatch.setenv("BUTLER_INBOUND_SEQUENCE_VALIDATE", "1")
    monkeypatch.setenv("BUTLER_TOOL_PAIR_REPAIR", "1")

    class _Loop:
        def __init__(self) -> None:
            self._messages = [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "user", "content": "Todoist里Inbox有哪些任务"},
            ]

        @property
        def messages(self) -> list[dict]:
            return list(self._messages)

        @messages.setter
        def messages(self, value: list[dict]) -> None:
            self._messages = list(value)

    state = LockedTurnState(text="x", session_key="s", platform="wechat", external_id=None)
    state.loop = _Loop()
    assert _phase_validate_loop_messages(state) is None
    assert state.health.get("tool_pair_repair_pre_turn") == 1
