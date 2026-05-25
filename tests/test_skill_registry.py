"""Skill registry search/install tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.registry.skill_install import content_hash
from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_normalize import bundle_to_markdown
from butler.registry.skill_service import SkillRegistryService
from butler.registry.skill_types import SkillBundle


@pytest.mark.unit
def test_bundle_to_markdown():
    name, md = bundle_to_markdown(
        "demo",
        {"SKILL.md": "---\nname: demo\ndescription: test\n---\n\nBody here.\n"},
    )
    assert name == "demo"
    assert "Body here" in md


@pytest.mark.unit
def test_bundled_search_and_install(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_REGISTRY", "1")
    monkeypatch.setenv("BUTLER_SKILL_REGISTRY_SOURCES", "bundled")

    from butler.config import get_butler_home
    from butler.tenant import tenant_skills_dir

    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    repo_root = Path(__file__).resolve().parents[1]
    skill_src = repo_root / "projects/LingWen1/skills/lingwen-project-lead.md"
    if not skill_src.is_file():
        pytest.skip("lingwen skill file missing")

    catalog = repo_root / "butler/registry/catalog/skills/index.yaml"
    assert catalog.is_file()

    tenant = "default"
    svc = SkillRegistryService(tenant_id=tenant)
    hits = svc.search("lingwen", source_filter="bundled")
    assert any("lingwen" in h.name for h in hits)

    rec = svc.install("bundled:lingwen-project-lead", force=True)
    assert rec.name == "lingwen-project-lead"
    dest = tenant_skills_dir(home, tenant) / rec.install_path
    assert dest.is_file()
    assert SkillLockFile(tenant_id=tenant).get(rec.name) is not None

    ok, _ = svc.uninstall(rec.name)
    assert ok
