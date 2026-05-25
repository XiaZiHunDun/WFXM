"""REG-P2: directory skills + Claude marketplace adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.registry.skill_normalize import bundle_install_layout
from butler.registry.skill_service import SkillRegistryService
from butler.registry.skill_types import SkillBundle
from butler.skills.manager import SkillManager


@pytest.mark.unit
def test_bundle_install_layout_directory():
    layout = bundle_install_layout(
        "demo-pdf",
        {
            "SKILL.md": "---\nname: demo-pdf\ndescription: d\n---\n\nBody\n",
            "reference.md": "# Ref\n",
        },
    )
    assert layout.kind == "directory"
    assert layout.name == "demo-pdf"
    assert "install_type: directory" in layout.stub_md
    assert "reference.md" in layout.directory_files


@pytest.mark.unit
def test_marketplace_search_and_fetch():
    from butler.registry.skill_sources.marketplace import ClaudeMarketplaceSource

    src = ClaudeMarketplaceSource()
    hits = src.search("demo-pdf", limit=5)
    assert any(h.identifier == "marketplace:demo/demo-pdf" for h in hits)
    bundle = src.fetch("marketplace:demo/demo-pdf")
    assert bundle is not None
    assert "SKILL.md" in bundle.files
    assert "reference.md" in bundle.files


@pytest.mark.unit
def test_marketplace_directory_install(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_REGISTRY", "1")
    monkeypatch.setenv("BUTLER_SKILL_REGISTRY_SOURCES", "marketplace")

    from butler.config import get_butler_home
    from butler.tenant import tenant_skills_dir

    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    tenant = "default"
    svc = SkillRegistryService(tenant_id=tenant)
    rec = svc.install("marketplace:demo/demo-pdf", force=True)
    assert rec.name == "demo-pdf"

    root = tenant_skills_dir(home, tenant)
    stub = root / "demo-pdf.md"
    assert stub.is_file()
    data = yaml.safe_load(stub.read_text(encoding="utf-8").split("---")[1])
    assert data.get("install_type") == "directory"
    assert (root / "demo-pdf" / "SKILL.md").is_file()
    assert (root / "demo-pdf" / "reference.md").is_file()

    mgr = SkillManager(root)
    skill = mgr.get_skill("demo-pdf")
    assert skill is not None
    assert "PDF-related demo" in skill.get("content", "")

    ok, _ = svc.uninstall("demo-pdf")
    assert ok
    assert not stub.is_file()
    assert not (root / "demo-pdf").exists()


@pytest.mark.unit
def test_skill_manager_directory_stub(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "demo-pdf").mkdir()
    (root / "demo-pdf" / "SKILL.md").write_text(
        "---\nname: demo-pdf\ndescription: inner\n---\n\nInner body\n",
        encoding="utf-8",
    )
    (root / "demo-pdf.md").write_text(
        "---\nname: demo-pdf\ndescription: stub\ninstall_type: directory\n"
        "content_path: demo-pdf/SKILL.md\n---\n\nStub\n",
        encoding="utf-8",
    )
    mgr = SkillManager(root)
    skill = mgr.get_skill("demo-pdf")
    assert skill is not None
    assert "Inner body" in skill["content"]
