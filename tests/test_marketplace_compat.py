"""Tests for marketplace compatibility cards and GitHub directory fetch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_fetch_github_directory_tree():
    from butler.registry.skill_sources.github import fetch_github_directory

    listing = [
        {"type": "file", "name": "SKILL.md", "path": "skills/demo/SKILL.md", "download_url": "https://x/s.md"},
        {"type": "dir", "name": "references", "path": "skills/demo/references"},
    ]
    ref_listing = [
        {"type": "file", "name": "guide.md", "path": "skills/demo/references/guide.md", "download_url": "https://x/g.md"},
    ]

    def fake_get(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/contents/skills/demo"):
            resp.status_code = 200
            resp.json.return_value = listing
        elif url.endswith("/contents/skills/demo/references"):
            resp.status_code = 200
            resp.json.return_value = ref_listing
        else:
            resp.status_code = 404
            resp.json.return_value = {}
        return resp

    def fake_safe_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("s.md"):
            resp.text = "---\nname: demo\n---\n\nBody\n"
        else:
            resp.text = "# Guide\n"
        return resp

    with patch("httpx.get", side_effect=fake_get):
        with patch("butler.registry.url_safety.safe_registry_get", side_effect=fake_safe_get):
            files = fetch_github_directory("owner", "repo", "skills/demo", ref="master")
    assert files is not None
    assert "SKILL.md" in files
    assert any(k.endswith("guide.md") for k in files)


@pytest.mark.unit
def test_marketplace_compat_install_followup(tmp_path, monkeypatch):
    from butler.registry.marketplace_compat import format_install_followup, get_compatibility

    compat = get_compatibility("webnovel-writer")
    assert compat is not None
    assert compat.get("claude_plugin") == "webnovel-writer"
    assert "webnovel-write" in (compat.get("adopted") or {}).get("skills", [])

    mcp_path = tmp_path / "mcp.yaml"
    monkeypatch.setattr(
        "butler.registry.paths.default_mcp_config_path",
        lambda: mcp_path,
    )
    text = format_install_followup("marketplace:webnovel-writer/webnovel-write")
    assert "firecrawl" in text
    assert "butler mcp add" in text

    mcp_path.write_text("servers:\n  firecrawl: {}\n", encoding="utf-8")
    text2 = format_install_followup("marketplace:webnovel-writer/webnovel-write")
    assert "firecrawl" not in text2 or "建议配置 MCP" not in text2


@pytest.mark.unit
def test_check_directory_skill_layout(tmp_path):
    from butler.registry.marketplace_compat import check_directory_skill_layout

    ws = tmp_path / "proj"
    skills = ws / ".butler" / "skills"
    skills.mkdir(parents=True)
    skill_dir = skills / "demo-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\n\nInner\n", encoding="utf-8")
    (skill_dir / "references" / "guide.md").write_text("# g\n", encoding="utf-8")
    (skills / "demo-skill.md").write_text(
        "---\nname: demo-skill\ninstall_type: directory\ncontent_path: demo-skill/SKILL.md\n---\n\n",
        encoding="utf-8",
    )
    ok, detail = check_directory_skill_layout("demo-skill", workspace=ws)
    assert ok is True
    assert "refs=" in detail


@pytest.mark.unit
def test_webnovel_marketplace_has_compatibility():
    from butler.registry.skill_sources.marketplace import (
        ClaudeMarketplaceSource,
        _catalog_entries,
        _find_plugin,
        _marketplace_json_for,
    )

    cat = next(c for c in _catalog_entries() if c.id == "webnovel-writer")
    data = _marketplace_json_for(cat)
    assert data is not None
    assert isinstance(data.get("compatibility"), dict)
    plugin = _find_plugin(data, "webnovel-write")
    assert plugin is not None
    assert plugin.get("install_mode") == "directory"
    assert "webnovel-write" in str((plugin.get("source") or {}).get("path"))

    src = ClaudeMarketplaceSource()
    with patch(
        "butler.registry.skill_sources.marketplace.fetch_github_directory",
        return_value={
            "SKILL.md": "---\nname: webnovel-write\n---\n\nWrite\n",
            "references/guide.md": "# g\n",
        },
    ):
        bundle = src.fetch("marketplace:webnovel-writer/webnovel-write")
    assert bundle is not None
    assert len(bundle.files) >= 2
