"""Tests for tenant → project skills sync."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_types import InstalledSkillRecord
from butler.registry.skills_project_sync import sync_tenant_skills_to_project
from butler.skills.layout import write_directory_stub


@pytest.mark.unit
def test_sync_tenant_directory_skills_to_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "butler_home"
    tenant = "default"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    from butler.registry.paths import skills_root

    src = skills_root(tenant_id=tenant)
    src.mkdir(parents=True, exist_ok=True)
    skill_dir = src / "demo-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: d\n---\n\nBody\n",
        encoding="utf-8",
    )
    (skill_dir / "references" / "guide.md").write_text("# g\n", encoding="utf-8")
    write_directory_stub(src, "demo-skill", description="d", content_rel="demo-skill/SKILL.md")

    SkillLockFile(tenant_id=tenant).record_install(
        InstalledSkillRecord(
            name="demo-skill",
            source="marketplace",
            identifier="marketplace:demo/demo-skill",
            version="1",
            installed_at="2026-06-20T00:00:00+00:00",
            content_hash="abc",
            install_path="demo-skill.md",
            scan_verdict="clean",
            trust="community",
        )
    )

    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "stack.yaml").write_text(
        "skills:\n  skills_expected:\n    - demo-skill\n    - local-only\n",
        encoding="utf-8",
    )
    (ws / ".butler" / "skills").mkdir(parents=True)
    (ws / ".butler" / "skills" / "local-only.md").write_text("---\nname: local-only\n---\n", encoding="utf-8")

    ok, msg, actions = sync_tenant_skills_to_project(ws, tenant_id=tenant)
    assert ok is True
    assert any("demo-skill" in a for a in actions)

    dest = ws / ".butler" / "skills"
    assert (dest / "demo-skill.md").is_file()
    assert (dest / "demo-skill" / "SKILL.md").is_file()
    assert (dest / "demo-skill" / "references" / "guide.md").is_file()
    assert (dest / "local-only.md").is_file()
    text = (dest / "demo-skill.md").read_text(encoding="utf-8")
    assert "install_type: directory" in text


@pytest.mark.unit
def test_sync_project_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    from butler.registry.paths import skills_root

    src = skills_root(tenant_id="default")
    src.mkdir(parents=True, exist_ok=True)
    (src / "flat.md").write_text("---\nname: flat\n---\n\nx\n", encoding="utf-8")
    SkillLockFile(tenant_id="default").record_install(
        InstalledSkillRecord(
            name="flat",
            source="bundled",
            identifier="bundled:flat",
            version=None,
            installed_at="2026-06-20T00:00:00+00:00",
            content_hash="x",
            install_path="flat.md",
            scan_verdict="clean",
            trust="trusted",
        )
    )
    ws = tmp_path / "proj"
    ws.mkdir()
    ok, msg, actions = sync_tenant_skills_to_project(ws, tenant_id="default", dry_run=True)
    assert ok is True
    assert "dry-run" in msg
    assert actions
    assert not (ws / ".butler" / "skills" / "flat.md").exists()
