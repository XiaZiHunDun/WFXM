"""Tests for delegate_task failure cleanup."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from butler.tools.registry import _tool_delegate_task


def test_delegate_failure_completes_task_and_caches_report(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()

    orch = MagicMock()
    orch.project_manager.get_current.return_value = MagicMock(name="demo")
    agent = MagicMock()
    agent.run.side_effect = RuntimeError("boom")
    orch.create_project_agent_loop.return_value = agent

    with (
        patch("butler.tools.delegate_impl._orchestrator_for_tool", return_value=orch),
        patch("butler.execution_context.get_current_session_key", return_value="wechat:u1:demo"),
        patch(
            "butler.tools.project_tools.get_tool_definitions_for_project",
            return_value=[],
        ),
        patch("butler.session.lifecycle.attach_turn_memory_prefetch"),
        patch("butler.session.lifecycle.sync_turn_memory"),
    ):
        raw = _tool_delegate_task(role="dev", task="fix tests", context="")

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload.get("task_id")

    from butler.runtime.task_store import get_task

    row = get_task(payload["task_id"])
    assert row is not None
    assert row["status"] == "failed"

    from butler.report import get_last_report

    report = get_last_report("wechat:u1:demo")
    assert report is not None
    assert report.success is False
