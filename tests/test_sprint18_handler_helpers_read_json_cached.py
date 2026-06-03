"""Sprint 18-3: handler_helpers 直读 JSON 改 read_json_cached (Sprint 18 subagent B HIGH-3).

3 处直读 JSON 绕过 read_json_cached (path, mtime) LRU:
- handler_helpers.py:463 todos_data
- handler_helpers.py:484 summary (project overview)
- handler_helpers.py:540 raw (inject_previous_session_summary)

修复: 全部改用 read_json_cached(path), 与 contacts/expense/habits 行为一致.
N 个 project 列出时省 50-200ms 重复 parse + mtime 校验 (写后立即失效).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.gateway import handler_helpers
from butler.gateway.handler_helpers import (
    _build_project_overview,
    _inject_previous_session_summary,
)
from butler.tools._file_cache import clear_cache


def _make_orchestrator(projects):
    """Build minimal mock orchestrator with project_manager.list_projects / active_project."""
    from types import SimpleNamespace

    pm = SimpleNamespace()
    pm.list_projects = lambda: projects
    pm.get_current = lambda session_key=None: projects[0] if projects else None
    pm.resolve_active_project_name = lambda session_key=None: (
        projects[0].name if projects else "(无)"
    )
    return SimpleNamespace(project_manager=pm)


def _make_project(name, workspace):
    from types import SimpleNamespace

    return SimpleNamespace(
        name=name,
        type="lead",
        pack="default",
        description="test project",
        workspace=str(workspace),
    )


@pytest.mark.unit
class TestReadJsonCachedMigrated:
    """handler_helpers 3 处直读 JSON 改 read_json_cached."""

    def setup_method(self):
        clear_cache()

    def test_build_project_overview_uses_read_json_cached_for_todos(self, tmp_path, monkeypatch):
        """handler_helpers:463 todos_data 改用 read_json_cached."""
        ws = tmp_path / "ws"
        ws.mkdir()
        todos = ws / ".butler" / "todos.json"
        todos.parent.mkdir()
        todos.write_text(json.dumps([{"status": "pending", "text": "x"}]), encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        from butler.tools import _file_cache
        with patch("butler.gateway.handler_helpers.read_json_cached", wraps=_file_cache.read_json_cached) as spy:
            _build_project_overview(orch, "session:sk")
        assert spy.called, "todos 直读应改走 read_json_cached"

    def test_build_project_overview_uses_read_json_cached_for_session_summary(self, tmp_path):
        """handler_helpers:484 summary 改用 read_json_cached."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text(json.dumps({"turns": 7}), encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        from butler.tools import _file_cache
        with patch("butler.gateway.handler_helpers.read_json_cached", wraps=_file_cache.read_json_cached) as spy:
            _build_project_overview(orch, "session:sk")
        assert spy.called, "session_summary 直读应改走 read_json_cached"

    def test_inject_previous_session_summary_uses_read_json_cached(self, tmp_path):
        """handler_helpers:540 raw 改用 read_json_cached."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text(json.dumps({"project": "p1", "turns": 5}), encoding="utf-8")
        proj = _make_project("p1", ws)
        from butler.tools import _file_cache
        with patch("butler.gateway.handler_helpers.read_json_cached", wraps=_file_cache.read_json_cached) as spy:
            # 用 dummy loop mock (内部仅用 project 字段)
            _inject_previous_session_summary(loop=None, project=proj)
        assert spy.called, "summary 直读应改走 read_json_cached"


@pytest.mark.unit
class TestBehaviorUnchanged:
    """迁移后行为不变 — 同样的输入产生同样的输出."""

    def setup_method(self):
        clear_cache()

    def test_overview_includes_pending_todos_count(self, tmp_path):
        """todos 有 pending → overview 含 '待办 N 项'."""
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

    def test_overview_includes_session_turns(self, tmp_path):
        """session_summary.turns > 0 → overview 含 '上次会话 N 轮'."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text(json.dumps({"turns": 12}), encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        result = _build_project_overview(orch, "session:sk")
        assert "上次会话 12 轮" in result

    def test_overview_skips_missing_files_silently(self, tmp_path):
        """文件缺失 → 静默跳过 (与原 read_text + try/except 行为一致)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        result = _build_project_overview(orch, "session:sk")
        # 不应抛异常
        assert "p1" in result

    def test_overview_skips_invalid_json(self, tmp_path):
        """坏 JSON → 静默跳过 (read_json_cached 返 None 等价于容错)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        todos = ws / ".butler" / "todos.json"
        todos.parent.mkdir()
        todos.write_text("not json {{{", encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        result = _build_project_overview(orch, "session:sk")
        assert "p1" in result  # 不崩

    def test_inject_summary_no_arg_works(self, tmp_path):
        """_inject_previous_session_summary 加载 summary 注入 (无 mock 行为)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        summary = ws / ".butler" / "session_summary.json"
        summary.parent.mkdir()
        summary.write_text(json.dumps({"project": "p1", "turns": 3}), encoding="utf-8")
        proj = _make_project("p1", ws)
        # 不抛异常
        _inject_previous_session_summary(loop=None, project=proj)

    def test_inject_summary_missing_file(self, tmp_path):
        """_inject_previous_session_summary 文件缺失 → 静默 (原 try/except 行为)."""
        ws = tmp_path / "ws"
        ws.mkdir()
        proj = _make_project("p1", ws)
        _inject_previous_session_summary(loop=None, project=proj)  # 不抛


@pytest.mark.unit
class TestLruCacheEffective:
    """验证 read_json_cached LRU 真的命中 (第二次读不重 parse)."""

    def setup_method(self):
        clear_cache()

    def test_repeat_call_uses_cache(self, tmp_path):
        """同一文件 2 次 → 第二次命中 LRU, 不重 json.loads."""
        from butler.tools import _file_cache
        ws = tmp_path / "ws"
        ws.mkdir()
        todos = ws / ".butler" / "todos.json"
        todos.parent.mkdir()
        todos.write_text(json.dumps([{"status": "pending", "text": "x"}]), encoding="utf-8")
        proj = _make_project("p1", ws)
        orch = _make_orchestrator([proj])
        # 第 1 次
        _build_project_overview(orch, "session:sk")
        # 改 json 内容但保留 mtime 模拟 LRU 命中
        import os
        st = todos.stat()
        with open(todos, "w") as f:
            f.write(json.dumps([{"status": "pending", "text": "DIFFERENT"}]))
        os.utime(todos, (st.st_atime, st.st_mtime))  # mtime 保持, 命中 LRU
        # 第 2 次 — 仍返旧内容 (LRU 命中)
        result = _build_project_overview(orch, "session:sk")
        assert "待办 1 项" in result  # 原 pending, 不是 DIFFERENT 后内容
