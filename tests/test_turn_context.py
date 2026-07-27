"""Unit tests for the turn_context module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.core.turn_context import (
    TurnContext,
    build_turn_context,
    compose_user_api_content,
    substitute_api_content,
    drop_stale_api_content,
    extract_api_content_sidecar,
    _build_memory_context_block,
)


class TestBuildMemoryContextBlock:
    """Tests for _build_memory_context_block."""

    def test_empty_context(self):
        assert _build_memory_context_block("") == ""
        assert _build_memory_context_block("   ") == ""

    def test_valid_context(self):
        result = _build_memory_context_block("test memory content")
        assert "<memory-context>" in result
        assert "test memory content" in result
        assert "</memory-context>" in result


class TestComposeUserApiContent:
    """Tests for compose_user_api_content."""

    def test_non_string_content(self):
        result = compose_user_api_content({"type": "image"}, "", "")
        assert result is None

    def test_empty_injections(self):
        result = compose_user_api_content("hello", "", "")
        assert result is None

    def test_with_memory_context(self):
        result = compose_user_api_content("hello", "memory context", "")
        assert result == "hello\n\n" + _build_memory_context_block("memory context")

    def test_with_plugin_context(self):
        result = compose_user_api_content("hello", "", "plugin context")
        assert result == "hello\n\nplugin context"

    def test_with_both_contexts(self):
        result = compose_user_api_content("hello", "memory", "plugin")
        assert "memory" in result
        assert "plugin" in result
        assert "hello" in result


class TestSubstituteApiContent:
    """Tests for substitute_api_content."""

    def test_no_sidecar(self):
        msg = {"role": "user", "content": "hello"}
        result = substitute_api_content(msg)
        assert result is None
        assert msg["content"] == "hello"

    def test_with_sidecar_user(self):
        msg = {"role": "user", "content": "hello", "api_content": "hello + injected"}
        result = substitute_api_content(msg)
        assert result == "hello + injected"
        assert msg["content"] == "hello + injected"
        assert "api_content" not in msg

    def test_with_sidecar_assistant(self):
        msg = {"role": "assistant", "content": "reply", "api_content": "reply + injected"}
        result = substitute_api_content(msg)
        assert result == "reply + injected"
        assert msg["content"] == "reply + injected"

    def test_with_sidecar_system(self):
        # System messages don't get substituted
        msg = {"role": "system", "content": "system", "api_content": "system + injected"}
        result = substitute_api_content(msg)
        assert result == "system + injected"
        assert msg["content"] == "system"  # Not substituted for system


class TestDropStaleApiContent:
    """Tests for drop_stale_api_content."""

    def test_drop_sidecar(self):
        msg = {"role": "user", "content": "hello", "api_content": "injected"}
        drop_stale_api_content(msg)
        assert "api_content" not in msg

    def test_no_sidecar(self):
        msg = {"role": "user", "content": "hello"}
        drop_stale_api_content(msg)
        assert msg == {"role": "user", "content": "hello"}


class TestExtractApiContentSidecar:
    """Tests for extract_api_content_sidecar."""

    def test_extract_string(self):
        msg = {"role": "user", "content": "hello", "api_content": "injected"}
        result = extract_api_content_sidecar(msg)
        assert result == "injected"

    def test_extract_non_string(self):
        msg = {"role": "user", "content": "hello", "api_content": 123}
        result = extract_api_content_sidecar(msg)
        assert result is None

    def test_no_sidecar(self):
        msg = {"role": "user", "content": "hello"}
        result = extract_api_content_sidecar(msg)
        assert result is None


class TestTurnContext:
    """Tests for TurnContext dataclass."""

    def test_turn_context_creation(self):
        context = TurnContext(
            user_message="hello",
            original_user_message="hello",
            messages=[{"role": "user", "content": "hello"}],
            conversation_history=[{"role": "user", "content": "hello"}],
            active_system_prompt="system",
            effective_task_id="task1",
            turn_id="turn1",
            current_turn_user_idx=0,
        )
        assert context.user_message == "hello"
        assert context.effective_task_id == "task1"
        assert context.should_review_memory is False
        assert context.plugin_user_context == ""


class TestBuildTurnContext:
    """Tests for build_turn_context."""

    def test_build_basic_context(self):
        context = build_turn_context(
            user_message="hello",
            system_message="system",
            conversation_history=[],
            task_id="task1",
            session_id="session1",
        )
        assert context.user_message == "hello"
        assert context.effective_task_id == "task1"
        assert context.active_system_prompt == "system"
        assert len(context.messages) == 1
        assert context.messages[0]["content"] == "hello"

    def test_build_without_task_id(self):
        context = build_turn_context(
            user_message="hello",
            system_message="system",
            conversation_history=[],
            task_id=None,
        )
        assert context.effective_task_id is not None
        assert len(context.effective_task_id) > 0

    def test_build_with_memory_nudge(self):
        mock_memory_store = MagicMock()
        context = build_turn_context(
            user_message="hello",
            system_message="system",
            conversation_history=[],
            task_id="task1",
            memory_nudge_interval=3,
            valid_tool_names={"memory"},
            memory_store=mock_memory_store,
            turns_since_memory=3,
        )
        assert context.should_review_memory is True

    def test_build_with_memory_manager(self):
        mock_memory_manager = MagicMock()
        mock_memory_manager.prefetch.return_value = "prefetched context"
        context = build_turn_context(
            user_message="hello",
            system_message="system",
            conversation_history=[],
            task_id="task1",
            session_id="session1",
            memory_manager=mock_memory_manager,
        )
        mock_memory_manager.on_turn_start.assert_called_once()
        mock_memory_manager.prefetch.assert_called_once_with("hello", session_id="session1")
        assert context.ext_prefetch_cache == "prefetched context"

    def test_build_with_conversation_history(self):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        context = build_turn_context(
            user_message="how are you",
            system_message="system",
            conversation_history=history,
            task_id="task1",
        )
        assert len(context.messages) == 3
        assert context.messages[0]["content"] == "hi"
        assert context.messages[2]["content"] == "how are you"

    def test_build_with_api_content_sidecar(self):
        mock_memory_manager = MagicMock()
        mock_memory_manager.prefetch.return_value = "memory context"
        context = build_turn_context(
            user_message="hello",
            system_message="system",
            conversation_history=[],
            task_id="task1",
            session_id="session1",
            memory_manager=mock_memory_manager,
        )
        assert context.messages[0].get("api_content") is not None
        assert "memory context" in context.messages[0]["api_content"]