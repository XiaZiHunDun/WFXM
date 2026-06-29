"""AP-11: HITL gate should not invoke AgentLoop while workflow step pending."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest_plugins = ["tests.gateway.test_gateway_handler"]

from butler.human_gate import check_workflow_step_approval, clear_session_gates


@pytest.mark.unit
def test_workflow_step_pending_blocks_until_approved():
    sk = "wechat:hitl-zero-llm"
    clear_session_gates(sk)
    assert check_workflow_step_approval(sk, "novel-factory", "danger_step") is False
    assert check_workflow_step_approval(sk, "novel-factory", "danger_step") is False
    clear_session_gates(sk)


@pytest.mark.integration
def test_handler_slash_command_does_not_run_loop(handler):
    """Slash commands are deterministic — AgentLoop.run must not be called."""
    mock_loop = MagicMock()
    with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
        out = handler._handle_command("/projects")
    assert out is not None
    mock_loop.run.assert_not_called()
