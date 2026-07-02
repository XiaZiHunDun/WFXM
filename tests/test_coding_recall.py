"""Tests for butler.memory.coding_recall (P3-H phase 1)."""

from __future__ import annotations

import json

import pytest

from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary
from butler.memory.coding_recall import search_coding_experiences
from butler.memory.memory_scope import infer_default_scope, tenant_coding_experiences_path


@pytest.mark.unit
def test_search_coding_requires_query():
    out = search_coding_experiences("  ", butler_home="/tmp/x")
    assert out["ok"] is False


@pytest.mark.unit
def test_search_coding_tenant_l4(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    l4 = tenant_coding_experiences_path(tmp_path)
    l4.parent.mkdir(parents=True, exist_ok=True)
    lib = ExperienceLibrary(theorem_lib=TheoremLibrary())
    exp = CodingExperience(
        id="B9_EX_demo_verify",
        title="pytest verify gate",
        context="run pytest after patch",
        pattern="always run pytest before claiming done",
        domain=["b9"],
        theorem_basis={"T01"},
        scope=infer_default_scope(exp_id="B9_EX_demo_verify", domain=["b9"]),
    )
    lib.add(exp, skip_validation=True)
    lib.save_to_file(str(l4))

    out = search_coding_experiences(
        "pytest verify",
        butler_home=tmp_path,
        limit=5,
    )
    assert out["ok"] is True
    assert out["results"]
    assert out["results"][0]["id"] == "B9_EX_demo_verify"


@pytest.mark.unit
def test_butler_recall_coding_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings
    from butler.memory.facade import ButlerMemoryService

    reload_butler_settings()
    l4 = tenant_coding_experiences_path(tmp_path)
    l4.parent.mkdir(parents=True, exist_ok=True)
    lib = ExperienceLibrary(theorem_lib=TheoremLibrary())
    lib.add(
        CodingExperience(
            id="B9_EX_tool_recall",
            title="tool recall coding",
            context="coding scope test",
            pattern="use butler_recall coding",
            domain=["prod"],
            theorem_basis={"T01"},
            scope=infer_default_scope(exp_id="B9_EX_tool_recall", domain=["prod"]),
        ),
        skip_validation=True,
    )
    lib.save_to_file(str(l4))

    svc = ButlerMemoryService()
    svc.initialize(session_id="test")
    raw = svc.handle_tool_call(
        "butler_recall",
        {"scope": "coding", "query": "tool recall", "limit": 3},
    )
    data = json.loads(raw)
    assert data.get("ok") is True
    assert data.get("scope") == "coding"
    assert any(r.get("id") == "B9_EX_tool_recall" for r in data.get("results") or [])
