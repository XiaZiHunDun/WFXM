"""Tests for butler.memory.transcript_recall (P3-H phase 2)."""

from __future__ import annotations

import json

import pytest

from butler.core.transcript_fts import rebuild_all_transcripts
from butler.memory.retrieval_telemetry import (
    clear_last_retrieval,
    get_last_retrieval_by_scope,
)
from butler.memory.transcript_recall import search_transcript_recall


@pytest.mark.unit
def test_transcript_recall_requires_query():
    out = search_transcript_recall(" ")
    assert out["ok"] is False


@pytest.mark.unit
def test_transcript_recall_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "0")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    out = search_transcript_recall("hello world")
    assert out["ok"] is False
    assert "TRANSCRIPT" in out.get("error", "")


@pytest.mark.unit
def test_transcript_recall_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sessions = tmp_path / "sessions" / "recall-sess"
    sessions.mkdir(parents=True)
    (sessions / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": "phase2 transcript keyword"}) + "\n",
        encoding="utf-8",
    )
    rebuild_all_transcripts()

    clear_last_retrieval("recall-sess")
    out = search_transcript_recall(
        "phase2 transcript",
        session_key="recall-sess",
        limit=5,
    )
    assert out["ok"] is True
    assert out["scope"] == "transcript"
    assert out["results"]
    assert out["results"][0]["session_key"] == "recall-sess"

    by_scope = get_last_retrieval_by_scope("recall-sess")
    assert "transcript" in by_scope
    assert by_scope["transcript"]["mode"].startswith("transcript")


@pytest.mark.unit
def test_butler_recall_transcript_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    from butler.config import reload_butler_settings
    from butler.memory.facade import ButlerMemoryService

    reload_butler_settings()
    sessions = tmp_path / "sessions" / "tool-sess"
    sessions.mkdir(parents=True)
    (sessions / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": "butler recall transcript test"}) + "\n",
        encoding="utf-8",
    )
    rebuild_all_transcripts()

    svc = ButlerMemoryService()
    svc.initialize(session_id="tool-sess")
    raw = svc.handle_tool_call(
        "butler_recall",
        {"scope": "transcript", "query": "recall transcript", "limit": 3},
    )
    data = json.loads(raw)
    assert data.get("ok") is True
    assert data.get("scope") == "transcript"
    assert data.get("results")


@pytest.mark.unit
def test_parse_recall_scopes_all_and_comma():
    from butler.memory.recall_scopes import parse_recall_scopes

    scopes, err = parse_recall_scopes("all")
    assert err is None
    assert "transcript" in scopes
    assert "coding" in scopes

    scopes2, err2 = parse_recall_scopes("experience,transcript")
    assert err2 is None
    assert scopes2 == ["experience", "transcript"]

    _, err3 = parse_recall_scopes("nope")
    assert err3


@pytest.mark.unit
def test_multi_scope_search_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    from butler.config import reload_butler_settings
    from butler.memory.search_cli import run_memory_search

    reload_butler_settings()
    sessions = tmp_path / "sessions" / "multi"
    sessions.mkdir(parents=True)
    (sessions / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": "multi scope search xyz"}) + "\n",
        encoding="utf-8",
    )
    rebuild_all_transcripts()

    payload = run_memory_search(
        tmp_path,
        "multi scope",
        scope="transcript,experience",
        limit=5,
        json_out=True,
    )
    assert payload.get("ok") is True
    by_scope = payload.get("by_scope") or {}
    assert "transcript" in by_scope
    assert "experience" in by_scope
    assert by_scope["transcript"].get("ok") is True


@pytest.mark.unit
def test_rag_diagnostics_per_scope_lines():
    from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

    lines = format_rag_diagnostic_lines(
        {
            "semantic_enabled": False,
            "rag_by_scope": {
                "experience": {
                    "mode": "hybrid",
                    "candidates": 3,
                    "query": "pytest",
                    "fallbacks": 0,
                },
                "transcript": {
                    "mode": "transcript-fts",
                    "candidates": 1,
                    "query": "galaxy",
                    "fallbacks": 0,
                },
            },
        }
    )
    joined = "\n".join(lines)
    assert "各 scope 最近召回" in joined
    assert "experience:" in joined
    assert "transcript:" in joined
