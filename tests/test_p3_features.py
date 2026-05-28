"""P3: doom_loop ask, transcript revert, delegate interrupt, worktree."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.core.transcript_revert import truncate_transcript
from butler.permissions.approvals import grant_once, is_approved, save_pending
from butler.permissions.doom_loop import check_doom_loop_ask, doom_loop_approval_request
from butler.project.worktree import effective_workspace, read_worktree_spec
from butler.runtime.delegate_registry import (
    interrupt_delegates_for_session,
    register_delegate_loop,
    unregister_delegate_loop,
)
from butler.tool_guardrails import (
    GuardrailDecision,
    ToolCallGuardrailController,
    doom_loop_mode,
)


@pytest.mark.unit
def test_doom_loop_mode_default_block(monkeypatch):
    monkeypatch.delenv("BUTLER_DOOM_LOOP_MODE", raising=False)
    assert doom_loop_mode() == "block"


@pytest.mark.unit
def test_doom_loop_ask_requires_approval(monkeypatch):
    monkeypatch.setenv("BUTLER_DOOM_LOOP_MODE", "ask")
    monkeypatch.setenv("BUTLER_DOOM_LOOP_THRESHOLD", "2")
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: "wx:doom",
    )
    ctrl = ToolCallGuardrailController()
    args = {"path": "/same"}
    ctrl.before_call("read_file", args)
    decision = ctrl.before_call("read_file", args)
    assert decision.action == "ask"
    block = check_doom_loop_ask(decision, "read_file", args)
    assert block is not None
    req = doom_loop_approval_request("read_file", args)
    save_pending("wx:doom", req)
    grant_once("wx:doom")
    assert is_approved("wx:doom", req)
    assert check_doom_loop_ask(decision, "read_file", args) is None


@pytest.mark.unit
def test_truncate_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    sk = "wx:revert"
    from butler.core.session_transcript import transcript_path

    path = transcript_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "user", "i": i}) for i in range(30)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = truncate_transcript(sk, keep_last_lines=5)
    assert out["ok"]
    assert out["dropped_lines"] == 25
    kept = path.read_text(encoding="utf-8").splitlines()
    assert kept[0].find("transcript_revert") >= 0 or "transcript_revert" in kept[0]
    assert len(kept) == 6


@pytest.mark.unit
def test_delegate_interrupt_propagates():
    parent = "wx:parent"
    child_loop = MagicMock()
    register_delegate_loop(parent, child_loop)
    n = interrupt_delegates_for_session(parent)
    assert n == 1
    child_loop.interrupt.assert_called_once()
    unregister_delegate_loop(parent, child_loop)


@pytest.mark.unit
def test_effective_workspace_worktree(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_PROJECT_WORKTREE", "1")
    proj = tmp_path / "proj"
    wt = tmp_path / "wt"
    proj.mkdir()
    wt.mkdir()
    (proj / "project.yaml").write_text(
        f"worktree: {wt}\nname: demo\n",
        encoding="utf-8",
    )
    assert read_worktree_spec(proj) == str(wt)
    assert effective_workspace(proj) == wt.resolve()
