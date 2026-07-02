"""Tests for P3-H phase 3 unified recall and observation search."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from butler.memory.observation_store import ObservationStore, observations_db_path
from butler.memory.observation_recall import search_observation_recall
from butler.memory.unified_recall import unified_hybrid_search


def _obs_row(**kwargs) -> dict[str, str]:
    base = {
        "row_id": "r1",
        "timestamp": "2026-06-30T12:00:00+00:00",
        "session_key": "sk",
        "tool": "read_file",
        "ok": "1",
        "path": "src/auth.py",
        "preview": "jwt verify middleware",
        "title": "read_file:src/auth.py",
        "content_hash": "abc",
    }
    base.update(kwargs)
    return base


@pytest.mark.unit
def test_observation_store_search_by_keyword(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many([_obs_row(), _obs_row(row_id="r2", preview="unrelated content", path="other.py")])
    hits = db.search("jwt verify", limit=5)
    assert len(hits) == 1
    assert hits[0]["path"] == "src/auth.py"


@pytest.mark.unit
def test_observation_recall_requires_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_RECALL", "0")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    out = search_observation_recall("jwt", project_workspace=tmp_path)
    assert out["ok"] is False


@pytest.mark.unit
def test_observation_recall_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_RECALL", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many([_obs_row()])
    out = search_observation_recall("jwt verify", project_workspace=tmp_path, limit=3)
    assert out["ok"] is True
    assert out["results"]
    assert out["results"][0]["path"] == "src/auth.py"


@pytest.mark.unit
def test_unified_recall_requires_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_UNIFIED_RECALL", "0")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    out = unified_hybrid_search(
        "pytest gate",
        butler_memory=SimpleNamespace(
            semantic=None,
            experience=SimpleNamespace(search=lambda *a, **k: []),
        ),
        limit=5,
    )
    assert out["ok"] is False


@pytest.mark.unit
def test_unified_recall_merges_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_MEMORY_UNIFIED_RECALL", "1")
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_RECALL", "1")
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
    from butler.config import reload_butler_settings
    from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary
    from butler.memory.butler_memory import ButlerMemory
    from butler.memory.memory_scope import infer_default_scope, tenant_coding_experiences_path
    from butler.memory.project_memory import ProjectMemory
    from butler.memory.observation_store import ObservationStore, observations_db_path

    reload_butler_settings()
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "project.yaml").write_text("name: demo\nworkspace: .\n", encoding="utf-8")
    pm = ProjectMemory(ws)
    pm.markdown.append("Notes", "pytest gate unified recall", classification="fact")

    l4 = tenant_coding_experiences_path(tmp_path)
    l4.parent.mkdir(parents=True, exist_ok=True)
    lib = ExperienceLibrary(theorem_lib=TheoremLibrary())
    lib.add(
        CodingExperience(
            id="B9_EX_unified",
            title="pytest gate coding",
            context="unified test",
            pattern="run pytest gate after patch",
            domain=["b9"],
            theorem_basis={"T01"},
            scope=infer_default_scope(exp_id="B9_EX_unified", domain=["b9"]),
        ),
        skip_validation=True,
    )
    lib.save_to_file(str(l4))

    bm = ButlerMemory(tmp_path)
    bm.experience.add("demo", "experience", "pytest gate experience row")

    obs = ObservationStore(observations_db_path(ws))
    obs.insert_many(
        [
            _obs_row(
                preview="pytest gate observation path",
                path="butler/memory/unified_recall.py",
            )
        ]
    )

    out = unified_hybrid_search(
        "pytest gate",
        butler_memory=bm,
        project_memory=pm,
        project_name="demo",
        project_workspace=ws,
        butler_home=tmp_path,
        limit=6,
    )
    assert out["ok"] is True
    assert out["results"]
    scopes = {str(r.get("recall_scope") or "") for r in out["results"]}
    assert scopes & {"experience", "project", "coding"}
    assert out["source_counts"]["experience"] >= 1


@pytest.mark.unit
def test_butler_recall_hybrid_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_MEMORY_UNIFIED_RECALL", "1")
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
    from butler.config import reload_butler_settings
    from butler.memory.facade import ButlerMemoryService

    reload_butler_settings()
    bm_svc = ButlerMemoryService()
    bm_svc.initialize(session_id="hybrid-test")
    bm_svc._butler_global.experience.add("demo", "experience", "hybrid scope smoke")
    raw = bm_svc.handle_tool_call(
        "butler_recall",
        {"scope": "hybrid", "query": "hybrid scope", "limit": 4},
    )
    data = json.loads(raw)
    assert data.get("ok") is True
    assert data.get("scope") == "hybrid"
