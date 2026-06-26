"""Tests for dev delegate bootstrap (ENG-2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from butler.dev_engine.delegate_init import init_dev_engine_state_for_delegate
from butler.tools.delegate_phases import DelegateRunState


def test_init_dev_engine_skips_non_dev_role():
    state = DelegateRunState(role="content", task="write doc")
    with patch("butler.dev_engine.dev_tools.dev_engine_enabled") as mock_en:
        init_dev_engine_state_for_delegate(state)
    mock_en.assert_not_called()


def test_init_dev_engine_skips_when_disabled():
    state = DelegateRunState(role="dev", task="fix tests")
    with patch("butler.dev_engine.dev_tools.dev_engine_enabled", return_value=False):
        with patch("butler.dev_engine.dev_loop.create_dev_state") as mock_create:
            init_dev_engine_state_for_delegate(state)
    mock_create.assert_not_called()


def test_init_dev_engine_registers_active_state():
    state = DelegateRunState(
        role="dev",
        task="fix tests",
        child_session_key="child-sk",
        session_key="parent-sk",
    )
    ds = SimpleNamespace()
    agent = MagicMock()
    agent._plugins = SimpleNamespace(
        plugins=[],
        _before_llm_hooks=[],
        _after_tools_hooks=[],
    )
    state.agent = agent
    active: dict = {}
    with patch("butler.dev_engine.dev_tools.dev_engine_enabled", return_value=True), patch(
        "butler.dev_engine.dev_loop.create_dev_state",
        return_value=ds,
    ), patch(
        "butler.dev_engine.delegate_init._activate_coding_knowledge",
    ), patch(
        "butler.dev_engine.dev_tools._active_states",
        active,
    ), patch(
        "butler.dev_engine.loop_plugin.create_dev_engine_plugin",
        return_value=SimpleNamespace(
            before_model=lambda: None,
            after_tools=lambda: None,
        ),
    ):
        init_dev_engine_state_for_delegate(state)
    assert active.get("child-sk") is ds
