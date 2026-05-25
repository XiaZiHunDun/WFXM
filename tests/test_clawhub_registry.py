"""ClawHub source tests (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.registry.skill_sources.clawhub import ClawHubSource


@pytest.mark.unit
def test_clawhub_search_parses_items():
    source = ClawHubSource()
    payload = {
        "items": [
            {
                "slug": "demo-skill",
                "displayName": "Demo Skill",
                "summary": "A demo",
                "tags": ["test"],
            }
        ]
    }
    with patch.object(source, "inspect", return_value=None):
        with patch("butler.registry.skill_sources.clawhub.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: payload)
            with patch("butler.registry.skill_sources.clawhub.read_cache", return_value=None):
                with patch("butler.registry.skill_sources.clawhub.write_cache"):
                    hits = source.search("demo", limit=5)
    assert len(hits) == 1
    assert hits[0].identifier == "clawhub:demo-skill"
    assert hits[0].trust == "community"


@pytest.mark.unit
def test_clawhub_fetch_extracts_skill_md():
    import io
    import zipfile

    source = ClawHubSource()
    skill_payload = {
        "slug": "demo-skill",
        "latestVersion": {"version": "1.0.0"},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: demo-skill\ndescription: x\n---\n\nBody\n")
    zip_bytes = buf.getvalue()

    def fake_get(url, **kwargs):
        resp = MagicMock()
        if "/skills/demo-skill" in url and "versions" not in url and "download" not in url:
            resp.status_code = 200
            resp.json = lambda: skill_payload
        elif "download" in url:
            resp.status_code = 200
            resp.content = zip_bytes
            resp.headers = {}
        else:
            resp.status_code = 404
            resp.json = lambda: {}
        return resp

    with patch("butler.registry.skill_sources.clawhub.httpx.get", side_effect=fake_get):
        bundle = source.fetch("clawhub:demo-skill")
    assert bundle is not None
    assert "SKILL.md" in bundle.files
    assert bundle.trust == "community"
