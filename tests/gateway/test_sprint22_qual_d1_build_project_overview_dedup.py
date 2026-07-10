"""Sprint 22-7 QUAL-21-D-1: `_build_project_overview` 重复 try/except 块去重.

`butler/gateway/handler_helpers.py:380-410` 中 3 处 try/except
结构完全同构 (todos / jobs / summary), 区别只是 try 内
的具体读取 + 文案生成. 复制粘贴 3 份 try/except, 后续若
新增 sub-info (如 session_count) 容易再次复制.

修复: 抽 `_safe_overview_sub(fn, label) -> str | None` helper,
把 try/except 集中. 行为不变.

行为保证 (本测试):
1) todos sub-info: 文件存在 + 有 pending → "待办 N 项" (旧)
2) jobs sub-info: runtime_enabled + 有 jobs → "定时任务 N 个" (旧)
3) summary sub-info: 文件存在 + turns > 0 → "上次会话 N 轮" (旧)
4) **每个 sub-info 路径抛异常时, _build_project_overview 仍返
   合法字符串 (项目名仍在), 不向外抛** (这是去重后的核心不变量)
5) 旧测试 (test_sprint18_handler_helpers_read_json_cached.py)
   全部继续 pass — 行为完全保留
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from butler.gateway.handler_helpers import _build_project_overview
from butler.tools._file_cache import clear_cache


def _make_orchestrator(projects):
    pm = SimpleNamespace()
    pm.list_projects = lambda: projects
    pm.get_current = lambda session_key=None: projects[0] if projects else None
    pm.resolve_active_project_name = lambda session_key=None: (
        projects[0].name if projects else "(无)"
    )
    return SimpleNamespace(project_manager=pm)


def _make_project(name, workspace):
    return SimpleNamespace(
        name=name,
        type="lead",
        pack="default",
        description="test project",
        workspace=str(workspace),
    )


@pytest.mark.unit
class TestBuildProjectOverviewDedup:
    """`_build_project_overview` 3 sub-info 路径异常都不应冒泡."""

    def setup_method(self):
        clear_cache()

    def test_todos_sub_info_still_works(self, tmp_path):
        """todos 路径: 文件 + pending → '待办 N 项' (旧行为)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        todos = ws / ".butler" / "todos.json"
        todos.parent.mkdir()
        todos.write_text(
            json.dumps([
                {"status": "pending", "text": "a"},
                {"status": "pending", "text": "b"},
                {"status": "done", "text": "c"},
            ]),
            encoding="utf-8",
        )
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        result = _build_project_overview(orch, "session:sk")
        assert "待办 2 项" in result

    def test_jobs_sub_info_still_works(self, tmp_path):
        """jobs 路径: runtime_enabled + jobs → '定时任务 N 个' (旧行为)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "runtime").mkdir()
        (ws / "runtime" / "jobs.yaml").write_text("jobs: []\n", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])

        fake_rows = [{"name": "j1"}, {"name": "j2"}]

        class _FakeRuntimeSvc:
            @staticmethod
            def list_jobs_status(name):
                return fake_rows

            @staticmethod
            def runtime_enabled():
                return True

        with patch.dict(
            "sys.modules",
            {"butler.runtime.service": _FakeRuntimeSvc},
        ):
            result = _build_project_overview(orch, "session:sk")
        assert "定时任务 2 个" in result

    def test_summary_sub_info_still_works(self, tmp_path):
        """summary 路径: 文件 + turns > 0 → '上次会话 N 轮' (旧行为)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text(json.dumps({"turns": 9}), encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        result = _build_project_overview(orch, "session:sk")
        assert "上次会话 9 轮" in result

    def test_todos_path_exception_does_not_propagate(self, tmp_path):
        """todos 路径 read_json_cached 抛异常 → _build_project_overview 不崩."""
        ws = tmp_path / "ws"
        ws.mkdir()
        todos = ws / ".butler" / "todos.json"
        todos.parent.mkdir()
        todos.write_text("[]", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])

        def boom(_path):
            raise RuntimeError("simulated todos I/O error")

        with patch("butler.gateway.handler_helpers.read_json_cached", boom):
            result = _build_project_overview(orch, "session:sk")
        # 项目名仍在, 没崩
        assert "p1" in result
        # todos 信息没出现 (因异常被吞)
        assert "待办" not in result

    def test_summary_path_exception_does_not_propagate(self, tmp_path):
        """summary 路径 read_json_cached 抛异常 → 不崩."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text("{}", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])

        def boom(_path):
            raise RuntimeError("simulated summary I/O error")

        with patch("butler.gateway.handler_helpers.read_json_cached", boom):
            result = _build_project_overview(orch, "session:sk")
        assert "p1" in result
        assert "上次会话" not in result

    def test_jobs_path_exception_does_not_propagate(self, tmp_path):
        """jobs 路径 list_jobs_status 抛异常 → 不崩."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "runtime").mkdir()
        (ws / "runtime" / "jobs.yaml").write_text("jobs: []\n", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])

        class _FakeRuntimeSvc:
            @staticmethod
            def list_jobs_status(name):
                raise RuntimeError("simulated jobs error")

            @staticmethod
            def runtime_enabled():
                return True

        with patch.dict(
            "sys.modules",
            {"butler.runtime.service": _FakeRuntimeSvc},
        ):
            result = _build_project_overview(orch, "session:sk")
        assert "p1" in result
        assert "定时任务" not in result

    def test_all_three_subpaths_fail_simultaneously(self, tmp_path):
        """3 个 sub-info 全炸 → overview 仍合法 (项目行还在)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / ".butler").mkdir(parents=True, exist_ok=True)
        todos = ws / ".butler" / "todos.json"
        todos.write_text("[]", encoding="utf-8")
        (ws / "runtime").mkdir()
        (ws / "runtime" / "jobs.yaml").write_text("jobs: []\n", encoding="utf-8")
        summary = ws / ".butler" / "session_summary.json"
        summary.write_text("{}", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])

        class _FakeRuntimeSvc:
            @staticmethod
            def list_jobs_status(name):
                raise RuntimeError("boom jobs")

            @staticmethod
            def runtime_enabled():
                return True

        def boom_json(_path):
            raise RuntimeError("boom json")

        with patch.dict(
            "sys.modules",
            {"butler.runtime.service": _FakeRuntimeSvc},
        ):
            with patch("butler.gateway.handler_helpers.read_json_cached", boom_json):
                result = _build_project_overview(orch, "session:sk")
        # 项目行还在, 没崩
        assert "p1" in result
        # 3 个 sub-info 都被吞
        assert "待办" not in result
        assert "定时任务" not in result
        assert "上次会话" not in result

    def test_dedup_helper_exists(self):
        """应有 `_safe_overview_sub` (或类似) helper 在 handler_helpers module."""
        from butler.gateway import handler_helpers

        candidate_names = (
            "_safe_overview_sub",
            "_safe_subinfo",
            "_try_sub",
            "_safe_run",
        )
        assert any(hasattr(handler_helpers, name) for name in candidate_names), (
            f"handler_helpers 应有去重 try/except 的 helper, 候选: {candidate_names}, "
            f"实际 attrs: {[a for a in dir(handler_helpers) if a.startswith('_safe') or a.startswith('_try')]}"
        )
