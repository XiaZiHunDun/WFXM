"""Bundled tenant skill installation."""

from __future__ import annotations

from pathlib import Path

from butler.skills.seed_bundled import ensure_bundled_tenant_skills


def test_ensure_design_system_skill(tmp_path: Path):
    installed = ensure_bundled_tenant_skills(tmp_path, "default")
    skill = tmp_path / "tenants" / "default" / "skills" / "design-system.md"
    assert skill.is_file()
    assert installed and installed[0] == skill
    text = skill.read_text(encoding="utf-8")
    assert "design-system" in text
    # idempotent
    assert ensure_bundled_tenant_skills(tmp_path, "default") == []
