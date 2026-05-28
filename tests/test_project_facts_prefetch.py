"""Project facts.json refresh and prefetch/recall integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from butler.memory.project_memory import ProjectMemory
from butler.session.lifecycle import prefetch_turn_memory


def _orch_with_project(tmp_path: Path) -> MagicMock:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi"]\n',
        encoding="utf-8",
    )
    (tmp_path / "project.yaml").write_text(
        "name: demo\nworkspace: .\n",
        encoding="utf-8",
    )
    orch = MagicMock()
    proj = MagicMock()
    proj.name = "demo"
    proj.workspace = tmp_path
    orch.project_manager.get_current.return_value = proj
    orch.project_manager.current_project = "demo"
    orch.project_manager.resolve_active_project_name.return_value = "demo"
    orch._project_memory = ProjectMemory(tmp_path)
    orch._project_memory.refresh_facts()
    orch.butler_memory = None
    return orch


def test_refresh_facts_writes_build_system(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi"]\n',
        encoding="utf-8",
    )
    pm = ProjectMemory(tmp_path)
    facts = pm.refresh_facts()
    assert facts.get("build_system") == "python"
    assert pm.facts.format_for_prompt()
    assert "FastAPI" in pm.facts.format_for_prompt()


def test_prefetch_includes_project_facts(tmp_path):
    orch = _orch_with_project(tmp_path)
    orch._project_memory = ProjectMemory(tmp_path)
    orch._project_memory.refresh_facts()

    from butler.memory.diagnostics import _resolve_project_memory

    def _resolve(orch_obj, _sk):
        return orch._project_memory, "demo"

    import butler.memory.diagnostics as diag_mod

    orig = diag_mod._resolve_project_memory
    diag_mod._resolve_project_memory = _resolve
    try:
        ctx = prefetch_turn_memory(orch, "用什么框架")
    finally:
        diag_mod._resolve_project_memory = orig

    assert "Project facts (auto)" in ctx
    assert "FastAPI" in ctx or "python" in ctx.lower()


def test_butler_recall_project_scope(tmp_path, monkeypatch, tmp_butler_home):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    pm = ProjectMemory(tmp_path)
    pm.refresh_facts()
    pm.markdown.append("Notes", "守门测试用 pytest", classification="fact")

    from butler.memory_plugin import ButlerMemoryService

    svc = ButlerMemoryService()
    svc._butler_global = MagicMock()
    svc._butler_global.semantic = None
    svc._project_memory = pm
    svc._project_root = tmp_path

    import json

    out = json.loads(
        svc._recall({"scope": "project", "query": "pytest", "limit": 5})
    )
    assert out["ok"] is True
    assert "pytest" in out.get("facts", "").lower() or any(
        "pytest" in (r.get("content") or "").lower() for r in out.get("results", [])
    )
