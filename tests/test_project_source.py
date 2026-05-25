"""ProjectSource: projects/*/skills read-only index."""

from __future__ import annotations

import pytest

from butler.registry.skill_sources.project import ProjectSource


@pytest.mark.unit
def test_project_search_lingwen():
    src = ProjectSource()
    hits = src.search("lingwen", limit=10)
    assert any(h.identifier == "project:LingWen1/lingwen-project-lead" for h in hits)
    assert hits[0].trust == "builtin"


@pytest.mark.unit
def test_project_fetch_bundle():
    src = ProjectSource()
    bundle = src.fetch("project:LingWen1/lingwen-project-lead")
    assert bundle is not None
    assert "SKILL.md" in bundle.files
    assert bundle.trust == "builtin"
