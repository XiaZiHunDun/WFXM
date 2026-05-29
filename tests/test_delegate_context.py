"""Tests for butler.core.delegate_context."""

from butler.core.delegate_context import (
    get_parent_callbacks,
    get_parent_messages,
    get_parent_system_prompt,
    set_parent_callbacks,
    set_parent_messages,
    set_parent_system_prompt,
)


class TestDelegateContext:
    def test_parent_callbacks_default_none(self):
        set_parent_callbacks(None)
        assert get_parent_callbacks() is None

    def test_parent_system_prompt_roundtrip(self):
        set_parent_system_prompt("hello")
        assert get_parent_system_prompt() == "hello"
        set_parent_system_prompt("")
        assert get_parent_system_prompt() == ""

    def test_parent_messages_roundtrip(self):
        msgs = [{"role": "user", "content": "hi"}]
        set_parent_messages(msgs)
        result = get_parent_messages()
        assert result == msgs
        assert result is not msgs  # defensive copy

    def test_parent_messages_empty(self):
        set_parent_messages([])
        assert get_parent_messages() == []

    def test_parent_messages_none(self):
        set_parent_messages(None)
        assert get_parent_messages() == []
