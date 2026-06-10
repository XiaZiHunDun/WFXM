"""P2: workflow step permissions and human-in-the-loop gates."""

from __future__ import annotations

from pathlib import Path

from butler.execution_context import use_workflow_step
from butler.human_gate import (
    check_workflow_step_approval,
    clear_session_gates,
    is_step_approved,
    mark_step_approved,
    resolve_human_gate_message,
)
from butler.permissions import evaluate_workflow_step_permission, get_workflow_step_tool_allowlist
from butler.report import AgentReport
from butler.workflows.runner import WorkflowRunner


def test_workflow_step_tool_allowlist(tmp_path):
    ws = tmp_path / "proj"
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        "workflow_steps:\n  write_step:\n    tools: [read_file, write_file]\n",
        encoding="utf-8",
    )
    ok = evaluate_workflow_step_permission("read_file", "write_step", workspace=ws)
    assert ok is not None and ok.allowed
    bad = evaluate_workflow_step_permission("terminal", "write_step", workspace=ws)
    assert bad is not None and not bad.allowed


def test_workflow_step_permission_uses_canonical_tool_names(tmp_path):
    ws = tmp_path / "proj"
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        "workflow_steps:\n  edit_step:\n    tools: [edit_file, search_code]\n",
        encoding="utf-8",
    )

    allow = get_workflow_step_tool_allowlist("edit_step", workspace=ws)
    assert allow == {"patch", "search_files"}

    ok = evaluate_workflow_step_permission("patch", "edit_step", workspace=ws)
    assert ok is not None and ok.allowed


def test_workflow_step_context_blocks_tool(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        "workflow_steps:\n  s1:\n    tools: [read_file]\n",
        encoding="utf-8",
    )
    from butler.permissions import check_project_permission_block

    class _Pm:
        def get_current(self, session_key: str = ""):
            class _P:
                workspace = ws

            return _P()

    class _Orch:
        project_manager = _Pm()

    monkeypatch.setattr(
        "butler.execution_context.get_current_orchestrator",
        lambda: _Orch(),
    )
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: "sk",
    )

    with use_workflow_step("s1"):
        block = check_project_permission_block("write_file", {"path": "a.txt"})
    assert block is not None and "仅允许工具" in block


def test_human_gate_confirm_flow(tmp_butler_home):
    sk = "wechat:gate-1"
    clear_session_gates(sk)
    assert not check_workflow_step_approval(sk, "novel-factory", "review")
    out = resolve_human_gate_message(sk, "确认", owner_verified=True)
    assert out is not None and "已确认" in out
    assert is_step_approved(sk, "novel-factory", "review")
    assert check_workflow_step_approval(sk, "novel-factory", "review")
    clear_session_gates(sk)


def test_agent_report_step_outcomes():
    report = AgentReport(
        headline="wf",
        failed_steps=["b"],
        step_outcomes={"a": "ok", "b": "approval_pending"},
    )
    data = report.to_dict()
    assert data["failed_steps"] == ["b"]
    assert data["step_outcomes"]["b"] == "approval_pending"
    restored = AgentReport.from_dict(data)
    assert restored.step_outcomes.get("b") == "approval_pending"


def test_workflow_runner_cache_includes_step_failures():
    from butler.report import clear_report_cache, get_last_report
    from butler.task_orchestrator import AgentResult, TaskGraphResult

    class _Wf:
        name = "test-wf"

    graph = TaskGraphResult(
        success=False,
        execution_order=["a", "b"],
        nodes={
            "a": AgentResult(success=True, response="ok"),
            "b": AgentResult(success=False, error="workflow_step_approval_pending"),
        },
    )
    clear_report_cache("sk-cache")
    WorkflowRunner._cache_workflow_report(_Wf(), graph, session_key="sk-cache")
    report = get_last_report("sk-cache")
    assert report is not None
    assert "b" in report.failed_steps
    assert report.step_outcomes.get("b") == "approval_pending"
