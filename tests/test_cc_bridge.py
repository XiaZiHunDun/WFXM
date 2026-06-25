"""Tests for Claude Code CLI bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_cc_bridge_disabled_status():
    from butler.runtime.cc_bridge import format_cc_bridge_status

    with patch.dict("os.environ", {"BUTLER_CC_BRIDGE": "0"}, clear=False):
        text = format_cc_bridge_status()
    assert "未启用" in text


def test_submit_sync_failure_no_cli(tmp_path, monkeypatch):
    from butler.runtime.cc_bridge import submit_cc_bridge_job

    monkeypatch.setenv("BUTLER_CC_BRIDGE", "1")
    with patch("butler.runtime.cc_bridge.claude_cli_path", return_value=None):
        job = submit_cc_bridge_job(
            session_key="sk",
            task="hello",
            workspace=str(tmp_path),
            run_async=False,
        )
    assert job.status == "failed"
    assert "claude" in job.error.lower()


def test_run_sync_success(tmp_path, monkeypatch):
    from butler.runtime.cc_bridge import run_cc_bridge_sync, CcBridgeJob

    monkeypatch.setenv("BUTLER_CC_BRIDGE", "1")
    job = CcBridgeJob(
        job_id="j1",
        session_key="sk",
        task="say hi",
        workspace=str(tmp_path),
        project_name="p",
    )

    class _Proc:
        returncode = 0
        stdout = "done"
        stderr = ""

    with patch("butler.runtime.cc_bridge.claude_cli_path", return_value="/usr/bin/claude"):
        with patch("butler.runtime.cc_bridge._queue_path") as qp:
            qp.return_value = tmp_path / "q.jsonl"
            with patch("subprocess.run", return_value=_Proc()) as run:
                out = run_cc_bridge_sync(job)
    assert out.status == "completed"
    assert "done" in out.summary
    run.assert_called_once()
    argv = run.call_args[0][0]
    assert argv[:3] == ["/usr/bin/claude", "-p", "say hi"]


def test_list_recent_jobs_filters_session(tmp_path, monkeypatch):
    from butler.runtime.cc_bridge import CcBridgeJob, list_recent_jobs

    q = tmp_path / "cc_bridge_queue.jsonl"
    rows = [
        CcBridgeJob(job_id="a", session_key="sk1", task="t1", workspace="/w"),
        CcBridgeJob(job_id="b", session_key="sk2", task="t2", workspace="/w"),
    ]
    q.write_text(
        "\n".join(json.dumps(r.to_dict(), ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("butler.runtime.cc_bridge._queue_path", lambda: q)
    got = list_recent_jobs("sk1", limit=5)
    assert len(got) == 1
    assert got[0].job_id == "a"


def test_claude_in_terminal_allowlist_when_bridge_on(monkeypatch):
    from butler.tools.path_safety import _allowed_terminal_commands

    monkeypatch.setenv("BUTLER_CC_BRIDGE", "1")
    assert "claude" in _allowed_terminal_commands()
