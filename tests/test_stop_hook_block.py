"""Stop hook block decision."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.hooks.runner import StopHookResult, run_stop_hooks


@pytest.mark.unit
def test_stop_hook_exit_2_blocks():
    rule = type("R", (), {"event": "Stop", "matcher": "*", "command": "echo block"})()

    with patch("butler.hooks.runner._rules_for_event", return_value=[rule]):
        with patch("butler.hooks.runner._run_hook", return_value=(2, "", "blocked by hook")):
            result = run_stop_hooks(status="completed")
    assert isinstance(result, StopHookResult)
    assert result.blocked is True
    assert result.decision == "block"


@pytest.mark.unit
def test_stop_hook_json_block_decision():
    stdout = (
        '{"hookSpecificOutput":{"hookEventName":"Stop",'
        '"decision":"block","systemMessage":"未跑 pytest，禁止结束"}}'
    )
    rule = type("R", (), {"event": "Stop", "matcher": "*", "command": "echo"})()

    with patch("butler.hooks.runner._rules_for_event", return_value=[rule]):
        with patch("butler.hooks.runner._run_hook", return_value=(0, stdout, "")):
            result = run_stop_hooks(status="completed")
    assert result.blocked is True
    assert "pytest" in result.block_message
