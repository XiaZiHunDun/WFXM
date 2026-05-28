"""OpenCode-inspired Butler features (zero-dep subset)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from butler.core.compaction_prompt import (
    OPENCODE_SUMMARY_TEMPLATE,
    build_compaction_user_prompt,
    use_opencode_compaction_template,
)
from butler.core.context_budget import usage_billable_tokens, record_usage_in_diagnostics
from butler.core.instruction_walkup import (
    drain_pending_instructions,
    record_read_path,
    reset_instruction_claims,
)
from butler.core.tool_output_prune import backward_prune_tool_outputs
from butler.delegate.subagent_permissions import (
    filter_tools_for_subagent,
    make_child_session_key,
)
from butler.permissions import evaluate_permission
from butler.tool_guardrails import ToolCallGuardrailController, doom_loop_threshold


def _tool_msg(content: str, call_id: str = "c1") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def test_compaction_prompt_includes_opencode_sections():
    assert use_opencode_compaction_template()
    prompt = build_compaction_user_prompt(transcript="[USER]: hi")
    assert "## Goal" in prompt
    assert "## Relevant Files" in prompt
    assert OPENCODE_SUMMARY_TEMPLATE[:20] in prompt


def test_backward_prune_clears_old_tool_outputs():
    big = "x" * 90000
    msgs = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "a", "tool_calls": [{"id": "c1", "function": {"name": "read_file"}}]},
        _tool_msg(big, "c1"),
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b", "tool_calls": [{"id": "c2", "function": {"name": "read_file"}}]},
        _tool_msg(big, "c2"),
    ]
    out = backward_prune_tool_outputs(msgs)
    assert out[2]["content"] != big or out[4]["content"] != big


def test_permission_last_match_wins(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir(parents=True)
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        """
rules:
  - tool: terminal
    action: deny
    reason: default deny
  - tool: terminal
    action: allow
    reason: exception allow
""",
        encoding="utf-8",
    )
    decision = evaluate_permission("terminal", {"command": "ls"}, workspace=ws)
    assert decision is not None
    assert decision.allowed
    assert decision.action == "allow"


def test_doom_loop_blocks_repeated_identical_calls(monkeypatch):
    monkeypatch.setenv("BUTLER_DOOM_LOOP_THRESHOLD", "3")
    assert doom_loop_threshold() == 3
    ctrl = ToolCallGuardrailController()
    args = {"path": "/same"}
    for _ in range(3):
        ctrl.before_call("read_file", args)
    decision = ctrl.before_call("read_file", args)
    assert decision.action == "block"
    assert decision.code == "doom_loop"


def test_usage_billable_includes_cache():
    assert usage_billable_tokens(prompt_tokens=100, completion_tokens=50, cached_tokens=30) == 180


def test_record_usage_in_diagnostics():
    diag: dict = {}
    record_usage_in_diagnostics(diag, prompt_tokens=10, completion_tokens=5, cached_tokens=2)
    assert diag["context_usage_billable_total"] == 17
    assert diag["last_usage_cached_tokens"] == 2


def test_subagent_tool_filter_and_child_session_key(tmp_path):
    ws = tmp_path / "p"
    ws.mkdir(parents=True)
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        "delegate_subagent:\n  deny_tools: [terminal]\n",
        encoding="utf-8",
    )
    tools = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "delegate_task"}},
        {"function": {"name": "terminal"}},
    ]
    filtered = filter_tools_for_subagent(tools, workspace=ws, role="dev")
    names = {t["function"]["name"] for t in filtered}
    assert "read_file" in names
    assert "delegate_task" not in names
    assert "terminal" not in names
    assert make_child_session_key("wx:1", "task_abc") == "wx:1::delegate::task_abc"


def test_instruction_walkup_after_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_INSTRUCTION_WALKUP", "1")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "AGENTS.md").write_text("## Rule\nAlways run tests.", encoding="utf-8")
    target = proj / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("print(1)", encoding="utf-8")
    reset_instruction_claims(session_key="s1")
    record_read_path(target, session_key="s1", workspace_root=proj)
    block = drain_pending_instructions(session_key="s1")
    assert "AGENTS.md" in block
    assert "Always run tests" in block
    assert drain_pending_instructions(session_key="s1") == ""


def test_create_task_sets_child_session_key(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    from butler.runtime.task_store import create_task, get_task

    rec = create_task(session_key="cli:u1", role="dev", task_preview="fix")
    assert rec["child_session_key"] == "cli:u1::delegate::" + rec["task_id"]
    loaded = get_task(rec["task_id"])
    assert loaded is not None
    assert loaded["child_session_key"] == rec["child_session_key"]
