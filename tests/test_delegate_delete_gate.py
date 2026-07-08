"""Tests for delegate delete verification gate and subagent tool restore."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from butler.delegate.subagent_permissions import augment_subagent_tools_from_project
from butler.tools.delegate_delete_gate import (
    apply_delegate_delete_verify_gate,
    extract_delete_paths,
)
from butler.tools.delegate_impl import finalize_delegate_success
from butler.tools.project_tools import get_tool_definitions_for_project
from butler.tools.toolset_profiles import TOOLSET_WECHAT_MINIMAL, filter_definitions_by_toolset


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeResult:
    def __init__(self, status: str = "completed", *, final_response: str = "") -> None:
        self.status = _FakeStatus(status)
        self.final_response = final_response
        self.messages: list[dict[str, str]] = []


def test_extract_delete_paths_from_task():
    task = (
        "请开发代理用 delete_file 删除 docs/foo.py 和 docs/bar.md"
    )
    paths = extract_delete_paths(task)
    assert "docs/foo.py" in paths
    assert "docs/bar.md" in paths


def test_delete_gate_blocks_when_file_still_exists(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    target = ws / "docs"
    target.mkdir()
    (target / "temp.py").write_text("x", encoding="utf-8")
    project = SimpleNamespace(workspace=ws)
    task = "delete_file docs/temp.py"
    ok, issues = apply_delegate_delete_verify_gate(
        base_success=True,
        issues=[],
        task=task,
        changes=[],
        project=project,
        messages=[],
        summary="已删除",
    )
    assert ok is False
    assert any("DELETE_VERIFY_GATE" in i for i in issues)


def test_delete_gate_passes_after_real_delete(tmp_path):
    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    project = SimpleNamespace(workspace=ws)
    task = "delete_file docs/temp.py"
    messages = [
        {
            "role": "tool",
            "content": '{"success": true, "path": "docs/temp.py", "action": "deleted"}',
        }
    ]
    ok, issues = apply_delegate_delete_verify_gate(
        base_success=True,
        issues=[],
        task=task,
        changes=[],
        project=project,
        messages=messages,
        summary="docs/temp.py 已删除",
    )
    assert ok is True
    assert issues == []


def test_delete_gate_blocks_hallucinated_success_without_tool():
    ok, issues = apply_delegate_delete_verify_gate(
        base_success=True,
        issues=[],
        task="delete_file docs/missing.py",
        changes=[],
        project=SimpleNamespace(workspace="/tmp/unused"),
        messages=[],
        summary="两个文件 ✅ 已删除",
    )
    assert ok is False
    assert any("DELETE_VERIFY_GATE" in i for i in issues)


def test_finalize_delegate_success_applies_delete_gate(tmp_path):
    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "keep.py").write_text("1", encoding="utf-8")
    project = SimpleNamespace(workspace=ws)
    success, issues = finalize_delegate_success(
        _FakeResult(final_response="docs/keep.py ✅ 已删除"),
        changes=[],
        issues=[],
        project=project,
        task="delete_file docs/keep.py",
        messages=[],
    )
    assert success is False
    assert any("DELETE_VERIFY_GATE" in i for i in issues)


@pytest.mark.unit
def test_augment_subagent_restores_delete_file_under_wechat_minimal(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_TOOLSET", TOOLSET_WECHAT_MINIMAL)
    project = SimpleNamespace(
        workspace=tmp_path,
        tools=[
            "read_file",
            "write_file",
            "delete_file",
            "patch",
            "search_files",
            "list_directory",
        ],
        tool_modes=None,
    )
    minimal = get_tool_definitions_for_project(project, role="dev", optimize_schema=False)
    names = {str((t.get("function") or {}).get("name") or "") for t in minimal}
    assert "delete_file" not in names

    restored = augment_subagent_tools_from_project(minimal, project=project, role="dev")
    rnames = {str((t.get("function") or {}).get("name") or "") for t in restored}
    assert "delete_file" in rnames
    assert "write_file" in rnames


@pytest.mark.unit
def test_wechat_minimal_still_strips_lead_tools():
    defs = [
        {"type": "function", "function": {"name": n, "parameters": {}}}
        for n in ("read_file", "delete_file", "delegate_task")
    ]
    out = filter_definitions_by_toolset(defs, toolset=TOOLSET_WECHAT_MINIMAL)
    names = {d["function"]["name"] for d in out}
    assert "read_file" in names
    assert "delete_file" not in names
