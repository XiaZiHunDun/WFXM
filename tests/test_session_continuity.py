"""Phase 0: session tool truth + workspace anchoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_list_session_read_files_from_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.session_transcript import record_tool_action
    from butler.core.session_tool_index import list_session_read_files

    sk = "test:owner:proj"
    ws = tmp_path / "LingWen1"
    ws.mkdir()
    (ws / "docs").mkdir()
    (ws / "docs" / "README.md").write_text("hi", encoding="utf-8")

    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/README.md"}),
        source="loop",
    )
    record_tool_action(
        sk,
        tool_name="search_files",
        args_preview=json.dumps({"pattern": "test_"}),
        source="loop",
    )
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/README.md"}),
        source="loop",
    )

    paths = list_session_read_files(sk, workspace=ws)
    assert paths == ["docs/README.md"]


def test_session_read_recall_intent():
    from butler.core.session_recall_intent import (
        detect_session_read_recall_banner,
        is_session_read_recall_intent,
    )

    assert is_session_read_recall_intent("把我们刚才读过哪些文件列个清单")
    assert not is_session_read_recall_intent("读一下 workflow_state")

    banner = detect_session_read_recall_banner(
        "列个清单",
        "sk:1",
        workspace=None,
    )
    assert banner is not None
    assert "session_read_recall" in banner


def test_hydrate_loop_injects_system_block(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_RECOVERY_NOTICE", "0")
    from butler.core.session_hydration import hydrate_loop_on_create
    from butler.core.session_transcript import record_tool_action

    sk = "hydrate:test"
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/a.md"}),
        source="loop",
    )

    class _Loop:
        def __init__(self):
            self._messages: list[dict] = []

    class _Proj:
        workspace = str(tmp_path / "ws")

    loop = _Loop()
    diag = hydrate_loop_on_create(loop, sk, _Proj())
    assert diag["session_hydrated"] is True
    assert diag["session_read_paths"] == 1
    assert loop._messages
    assert loop._messages[0]["role"] == "system"
    assert "docs/a.md" in loop._messages[0]["content"]


def test_relative_docs_resolves_to_project_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("BUTLER_WORKSPACE_ANCHOR_STRICT", "1")

    projects = tmp_path / "projects"
    projects.mkdir()
    fixture_docs = projects / "docs"
    fixture_docs.mkdir()
    (fixture_docs / "trap.txt").write_text("trap", encoding="utf-8")

    proj_ws = projects / "LingWen1"
    (proj_ws / "docs").mkdir(parents=True)
    target = proj_ws / "docs" / "real.md"
    target.write_text("ok", encoding="utf-8")

    from butler.execution_context import use_execution_context
    from butler.tools.path_safety import check_tool_path

    class _PM:
        def get_current(self, *, session_key: str = ""):
            class _P:
                workspace = str(proj_ws)

            return _P()

    class _Orch:
        project_manager = _PM()

    with use_execution_context(_Orch(), session_key="wechat:u:灵文1号"):
        result = check_tool_path("docs/real.md")
    assert result.allowed
    assert result.path == target.resolve()


def test_format_tool_workspace_line_for_session(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    from butler.tools.path_safety import format_tool_workspace_line

    class _PM:
        def get_current(self, *, session_key: str = ""):
            class _P:
                workspace = str(tmp_path / "MyProj")

            return _P()

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())
    line = format_tool_workspace_line("wechat:x:MyProj")
    assert "MyProj" in line
    assert "工具工作区:" in line


def test_list_session_read_files_includes_delegate_source(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.session_transcript import record_tool_action
    from butler.core.session_tool_index import list_session_read_files

    sk = "delegate:read"
    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/loop.md"}),
        source="loop",
    )
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/delegate.md"}),
        source="delegate",
    )
    record_tool_action(
        sk,
        tool_name="search_files",
        args_preview=json.dumps({"pattern": "test"}),
        source="loop",
    )

    paths = list_session_read_files(sk, workspace=ws)
    assert paths == ["docs/loop.md", "docs/delegate.md"]


def test_list_session_read_files_loop_only_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.session_transcript import record_tool_action
    from butler.core.session_tool_index import list_session_read_files

    sk = "loop:only"
    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/loop.md"}),
        source="loop",
    )
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/delegate.md"}),
        source="delegate",
    )

    assert list_session_read_files(sk, workspace=ws, sources=("loop",)) == ["docs/loop.md"]


def test_session_reset_clears_read_file_index(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.session_tool_index import list_session_read_files
    from butler.core.session_transcript import record_session_reset, record_tool_action

    sk = "epoch:test"
    ws = tmp_path / "proj"
    ws.mkdir()
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/old.md"}),
        source="loop",
    )
    record_session_reset(sk, reason="new")
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/new.md"}),
        source="loop",
    )
    assert list_session_read_files(sk, workspace=ws) == ["docs/new.md"]


def test_hydrate_skips_paths_before_session_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_RECOVERY_NOTICE", "0")
    from butler.core.session_hydration import hydrate_loop_on_create
    from butler.core.session_transcript import record_session_reset, record_tool_action

    sk = "hydrate:epoch"
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/before.md"}),
        source="loop",
    )
    record_session_reset(sk, reason="new")

    class _Loop:
        def __init__(self):
            self._messages: list[dict] = []

    class _Proj:
        workspace = str(tmp_path / "ws")

    loop = _Loop()
    diag = hydrate_loop_on_create(loop, sk, _Proj())
    assert diag["session_hydrated"] is False
    assert diag["session_read_paths"] == 0
    assert loop._messages == []


def test_recovery_notice_false_after_session_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.session_hydration import should_show_recovery_notice
    from butler.core.session_transcript import (
        record_assistant_message,
        record_session_reset,
        record_tool_action,
    )

    sk = "recovery:epoch"
    record_tool_action(
        sk,
        tool_name="read_file",
        args_preview=json.dumps({"path": "docs/a.md"}),
        source="loop",
    )
    record_assistant_message(sk, "done", tool_calls=0)
    record_session_reset(sk, reason="new")
    assert should_show_recovery_notice(sk, gap_seconds=0.0) is False


def test_projects_docs_trap_remapped_to_default_project(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "灵文1号")
    monkeypatch.setenv("BUTLER_WORKSPACE_ANCHOR_STRICT", "1")

    projects = tmp_path / "projects"
    trap_docs = projects / "docs"
    trap_docs.mkdir(parents=True)
    (trap_docs / "pilot-log.md").write_text("fixture", encoding="utf-8")

    proj_ws = projects / "LingWen1"
    real = proj_ws / "docs" / "pilot-log.md"
    real.parent.mkdir(parents=True)
    real.write_text("real project doc", encoding="utf-8")

    class _PM:
        def get_project(self, name: str):
            if name == "灵文1号":
                class _P:
                    workspace = str(proj_ws)

                return _P()
            return None

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())

    from butler.tools.path_safety import check_tool_path

    result = check_tool_path("docs/pilot-log.md")
    assert result.allowed
    assert result.path == real.resolve()


def test_agent_loop_rebinds_execution_context_for_tools(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", "/tmp")
    from butler.core.agent_loop import AgentLoop
    from butler.execution_context import get_current_orchestrator, get_current_session_key

    class _Orch:
        pass

    orch = _Orch()
    loop = AgentLoop(client=object(), tool_dispatcher=lambda n, a: "ok")
    loop.bind_execution(orch, session_key="wechat:u:灵文1号")

    seen = {}

    def _dispatch(name, args):
        seen["orch"] = get_current_orchestrator()
        seen["sk"] = get_current_session_key()
        return "ok"

    loop.tool_dispatcher = _dispatch
    loop._dispatch_tool("read_file", {"path": "x"})
    assert seen["orch"] is orch
    assert seen["sk"] == "wechat:u:灵文1号"
