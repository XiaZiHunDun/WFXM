"""M1 memory unification: orchestrator and memory_provider share instances."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project_manager import ProjectManager


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _setup_projects_dir(tmp_path: Path, monkeypatch) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "mem-proj"
    proj.mkdir()
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "mem-proj",
                "type": "software",
                "description": "memory unification test",
                "workspace": str(proj),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()


@pytest.fixture
def orchestrator(tmp_path, monkeypatch, tmp_butler_home):
    _setup_projects_dir(tmp_path, monkeypatch)
    from butler.orchestrator import ButlerOrchestrator

    orch = ButlerOrchestrator(user_id="owner", channel="test")
    yield orch
    _reset_singletons()


class TestMemorySingleInstance:
    def test_provider_shares_butler_memory_without_project(self, orchestrator):
        provider = orchestrator.memory_provider
        assert provider is not None
        assert orchestrator.butler_memory is provider._butler_global

    def test_provider_shares_project_memory_after_switch(self, orchestrator):
        orchestrator.project_manager.switch_project("mem-proj")
        provider = orchestrator.memory_provider
        assert provider is not None
        assert orchestrator._project_memory is not None
        assert orchestrator._project_memory is provider._project_memory

    def test_project_switch_keeps_provider_in_sync(self, orchestrator):
        orchestrator.project_manager.switch_project("mem-proj")
        provider = orchestrator.memory_provider
        assert orchestrator.butler_memory is provider._butler_global
        assert orchestrator._project_memory is provider._project_memory

        orchestrator.on_project_switch("", "mem-proj")

        assert orchestrator.butler_memory is provider._butler_global
        assert orchestrator._project_memory is provider._project_memory

    def test_prefetch_delegates_to_session_lifecycle_when_linked(self, orchestrator, monkeypatch):
        from butler.session_lifecycle import prefetch_turn_memory

        calls: list[tuple] = []

        def _spy(orch, query, **kwargs):
            calls.append((orch, query, kwargs))
            return "spy-prefetch"

        monkeypatch.setattr(
            "butler.session_lifecycle.prefetch_turn_memory",
            _spy,
        )
        provider = orchestrator.memory_provider
        assert provider is not None
        out = provider.prefetch("hello query")
        assert out.endswith("spy-prefetch")
        assert calls and calls[0][0] is orchestrator
        assert calls[0][1] == "hello query"

    def test_remember_visible_via_butler_memory_after_tool_write(self, orchestrator, monkeypatch):
        orchestrator.project_manager.switch_project("mem-proj")
        from butler.tools.memory_tools import tool_butler_remember
        from butler.execution_context import use_execution_context

        with use_execution_context(orchestrator, session_key="test-session"):
            raw = tool_butler_remember(
                scope="owner_experience",
                content="unification marker xyzzy",
                category="test",
            )
        assert '"ok": true' in raw.replace(" ", "").lower() or '"ok":true' in raw.replace(" ", "").lower()

        hits = orchestrator.butler_memory.experience.search("xyzzy", limit=5)
        assert any("xyzzy" in (h.get("content") or "") for h in hits)
