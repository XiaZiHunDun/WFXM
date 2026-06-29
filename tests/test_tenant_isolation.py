"""Sprint 3: tenant-scoped Butler memory and skills."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.memory.butler_memory import ButlerMemory
from butler.orchestrator import ButlerOrchestrator
from butler.orchestrator.templates import combined_skill_manager
from butler.project import Project
from butler.project.manager import ProjectManager
from butler.tenant import (
    DEFAULT_TENANT,
    migrate_legacy_memory_layout,
    resolve_tenant_for_project,
    tenant_memory_dir,
    tenant_skills_dir,
)


def _write_project(base: Path, folder: str, *, name: str, tenant: str | None = None) -> Path:
    proj_dir = base / folder
    proj_dir.mkdir(parents=True)
    data: dict = {
        "name": name,
        "type": "software",
        "description": name,
        "workspace": str(proj_dir),
    }
    if tenant is not None:
        data["tenant"] = tenant
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True),
        encoding="utf-8",
    )
    return proj_dir


@pytest.mark.module_test
class TestTenantResolution:
    def test_project_tenant_overrides_default(self, tmp_path):
        proj = Project.from_yaml(
            _write_project(tmp_path, "a", name="A", tenant="acme") / "project.yaml"
        )
        assert resolve_tenant_for_project(proj) == "acme"

    def test_inherit_settings_default_tenant(self, tmp_path):
        from butler.config import ButlerSettings

        proj = Project.from_yaml(
            _write_project(tmp_path, "b", name="B") / "project.yaml"
        )
        settings = ButlerSettings(default_tenant="corp-x")
        assert resolve_tenant_for_project(proj, settings) == "corp-x"


@pytest.mark.module_test
class TestTenantMemoryPaths:
    def test_separate_experience_databases(self, tmp_path):
        home = tmp_path / "butler-home"
        bm_a = ButlerMemory(home, tenant_id="tenant-a")
        bm_b = ButlerMemory(home, tenant_id="tenant-b")

        bm_a.experience.add("ProjA", "fact", "tenant-a secret marker")
        hits_b = bm_b.experience.search("tenant-a secret")
        assert hits_b == []

        hits_a = bm_a.experience.search("tenant-a secret")
        assert len(hits_a) >= 1

    def test_legacy_migration_to_default_tenant(self, tmp_path):
        home = tmp_path / "legacy"
        legacy_mem = home / "memory"
        legacy_mem.mkdir(parents=True)
        (legacy_mem / "profile.json").write_text('{"entries": ["legacy owner"]}', encoding="utf-8")

        bm = ButlerMemory(home, tenant_id=DEFAULT_TENANT)
        assert "legacy owner" in bm.profile.read()
        assert not (home / "memory").exists()
        assert tenant_memory_dir(home, DEFAULT_TENANT).exists()


@pytest.mark.integration
class TestOrchestratorTenantSwitch:
    def test_butler_memory_switches_with_project_tenant(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        projects_dir = tmp_path / "projects"
        _write_project(projects_dir, "p1", name="项目甲", tenant="alpha")
        _write_project(projects_dir, "p2", name="项目乙", tenant="beta")

        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        ProjectManager._instance = None
        reload_butler_settings()

        orch = ButlerOrchestrator(user_id="owner", channel="test")
        orch.project_manager.switch_project("项目甲")
        orch.butler_memory.experience.add("项目甲", "note", "alpha-only fact 42")

        orch.project_manager.switch_project("项目乙")
        assert orch.butler_memory.tenant_id == "beta"
        assert orch.butler_memory.experience.search("alpha-only") == []

        orch.project_manager.switch_project("项目甲")
        assert orch.butler_memory.experience.search("alpha-only") != []


@pytest.mark.integration
class TestTenantSkillDirs:
    def test_global_skills_use_tenant_directory(self, tmp_path):
        from butler.config import ButlerSettings

        settings = ButlerSettings(butler_home=tmp_path / "home")
        mgr = combined_skill_manager(settings, None, tenant_id="acme")
        assert mgr._skills_dir == tenant_skills_dir(settings.butler_home, "acme")
