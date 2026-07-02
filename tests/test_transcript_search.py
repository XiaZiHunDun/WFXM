"""FTS and scroll tests for transcript search."""

import json
import os

import pytest

from butler.core.transcript_fts import index_transcript_line, rebuild_all_transcripts, search_fts
from butler.core.transcript_search import search_transcripts


@pytest.mark.unit
def test_fts_index_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sessions = tmp_path / "sessions" / "sess-a"
    sessions.mkdir(parents=True)
    tpath = sessions / "transcript.jsonl"
    tpath.write_text(
        json.dumps({"type": "user", "content": "hello galaxy"}) + "\n"
        + json.dumps({"type": "assistant", "content": "reply about galaxy"}) + "\n",
        encoding="utf-8",
    )
    stats = rebuild_all_transcripts()
    assert stats["lines"] >= 2
    hits = search_fts("galaxy", limit=5)
    assert hits
    assert hits[0]["session_key"] == "sess-a"


@pytest.mark.unit
def test_search_transcripts_uses_fts(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sessions = tmp_path / "sessions" / "cur"
    sessions.mkdir(parents=True)
    (sessions / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": "unique-keyword-xyz"}) + "\n",
        encoding="utf-8",
    )
    rebuild_all_transcripts()
    hits = search_transcripts("unique-keyword-xyz", session_key="cur")
    assert len(hits) == 1
    assert hits[0]["preview"]
