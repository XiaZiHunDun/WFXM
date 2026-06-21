"""Extended stack diagnostics and project skill auto-sync tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.ops.stack_diagnostics import collect_stack_health
from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_types import InstalledSkillRecord
from butler.registry.skills_project_sync import (
    maybe_sync_after_registry_install,
    skill_auto_sync_project_enabled,
)


@pytest.mark.unit
def test_skill_present_requires_disk_not_lockfile_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "stack.yaml").write_text(
        "skills:\n  skills_expected: [ghost-skill]\n",
        encoding="utf-8",
    )
    SkillLockFile(tenant_id="default").record_install(
        InstalledSkillRecord(
            name="ghost-skill",
            source="marketplace",
            identifier="marketplace:demo/ghost-skill",
            version=None,
            installed_at="2026-06-20T00:00:00+00:00",
            content_hash="x",
            install_path="ghost-skill.md",
            scan_verdict="clean",
            trust="community",
        )
    )
    stats = collect_stack_health(ws)
    assert any("ghost-skill" in w for w in stats["warnings"])
    assert stats["ok"] is False


@pytest.mark.unit
def test_stack_checks_apis_marketplace_deploy_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)

    ws = tmp_path / "proj"
    (ws / ".butler" / "skills").mkdir(parents=True)
    (ws / ".butler" / "skills" / "demo.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (ws / "stack.yaml").write_text(
        """
version: 2
deploy_profile: gateway
python_extras:
  includes: [mcp]
apis:
  - id: minimax
    env: [MINIMAX_API_KEY]
    required: true
skills:
  skills_expected: [demo]
  marketplace_install:
    - marketplace:demo/demo
""".strip(),
        encoding="utf-8",
    )
    SkillLockFile(tenant_id="default").record_install(
        InstalledSkillRecord(
            name="demo",
            source="marketplace",
            identifier="marketplace:other/demo",
            version=None,
            installed_at="2026-06-20T00:00:00+00:00",
            content_hash="x",
            install_path="demo.md",
            scan_verdict="clean",
            trust="community",
        )
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    stats = collect_stack_health(ws)
    assert "api:minimax=ok" in stats["checks"]
    assert "deploy_profile:gateway=ok" in stats["checks"]
    assert any("marketplace" in w and "demo" in w for w in stats["warnings"])


@pytest.mark.unit
def test_maybe_sync_after_registry_install_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "butler_home"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: home)
    monkeypatch.setattr("butler.registry.paths.get_butler_home", lambda: home)
    monkeypatch.setenv("BUTLER_SKILL_AUTO_SYNC_PROJECT", "1")
    assert skill_auto_sync_project_enabled() is True

    from butler.registry.paths import skills_root

    src = skills_root(tenant_id="default")
    src.mkdir(parents=True, exist_ok=True)
    (src / "demo.md").write_text("---\nname: demo\n---\n\nbody\n", encoding="utf-8")

    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "stack.yaml").write_text("project: test\n", encoding="utf-8")

    monkeypatch.setattr(
        "butler.registry.skills_project_sync.resolve_default_project_workspace",
        lambda: ws,
    )

    rec = InstalledSkillRecord(
        name="demo",
        source="marketplace",
        identifier="marketplace:demo/demo",
        version=None,
        installed_at="2026-06-20T00:00:00+00:00",
        content_hash="x",
        install_path="demo.md",
        scan_verdict="clean",
        trust="community",
    )
    msg = maybe_sync_after_registry_install(rec, tenant_id="default")
    assert "已同步到项目" in msg
    assert (ws / ".butler" / "skills" / "demo.md").is_file()
