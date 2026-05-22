"""Per-session steer queue (WeChat S1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.core.steer import (
    apply_steer_to_tool_results,
    clear_steer,
    drain_steer,
    is_run_active,
    mark_run_active,
    mark_run_inactive,
    steer,
)
from butler.execution_context import use_execution_context


@pytest.fixture(autouse=True)
def _reset_steer_state():
    clear_steer("s1")
    clear_steer("s2")
    clear_steer("default")
    clear_steer("cli")
    mark_run_inactive("s1")
    mark_run_inactive("s2")
    mark_run_inactive("default")
    mark_run_inactive("cli")
    yield
    clear_steer("s1")
    clear_steer("s2")
    clear_steer("default")
    clear_steer("cli")
    mark_run_inactive("s1")
    mark_run_inactive("s2")
    mark_run_inactive("default")
    mark_run_inactive("cli")


def test_steer_isolated_per_session_key():
    assert steer("alpha", session_key="s1")
    assert steer("beta", session_key="s2")
    assert drain_steer("s1") == "alpha"
    assert drain_steer("s2") == "beta"
    assert drain_steer("s1") is None


def test_clear_steer_only_one_session():
    steer("keep", session_key="s1")
    steer("drop", session_key="s2")
    clear_steer("s1")
    assert drain_steer("s1") is None
    assert drain_steer("s2") == "drop"


def test_run_active_depth_per_session():
    mark_run_active("alice")
    assert is_run_active("alice")
    assert not is_run_active("bob")
    mark_run_active("alice")
    mark_run_inactive("alice")
    assert is_run_active("alice")
    mark_run_inactive("alice")
    assert not is_run_active("alice")


def test_apply_steer_uses_execution_context_session():
    with use_execution_context(MagicMock(), session_key="ctx-s"):
        steer("from context", session_key=None)
        msgs = [
            {"role": "assistant", "tool_calls": [{"id": "x", "function": {"name": "t"}}]},
            {"role": "tool", "tool_call_id": "x", "content": "ok"},
        ]
        assert apply_steer_to_tool_results(msgs, 1)
        assert "from context" in msgs[-1]["content"]
        assert drain_steer("ctx-s") is None


def test_gateway_steer_requires_active_run():
    from butler.gateway.message_handler import ButlerMessageHandler

    h = ButlerMessageHandler(channel="test")
    with patch("butler.core.steer.is_run_active", return_value=False):
        text = h._handle_command("/steer 先看测试", session_key="wechat:u1")
    assert "没有进行中" in text

    with patch("butler.core.steer.is_run_active", return_value=True):
        with patch("butler.core.steer.steer", return_value=True) as steer_fn:
            text = h._handle_command("/指引 先看测试", session_key="wechat:u1")
    steer_fn.assert_called_once_with("先看测试", session_key="wechat:u1")
    assert "已加入指引" in text
