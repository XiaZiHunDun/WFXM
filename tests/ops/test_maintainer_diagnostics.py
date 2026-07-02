"""Tests for transcript FTS drift diagnostics."""

from __future__ import annotations

import json

from butler.config import reload_butler_settings


def test_transcript_fts_drift_detects_gap(tmp_butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    reload_butler_settings()
    sessions = tmp_butler_home / "sessions" / "wx_test"
    sessions.mkdir(parents=True)
    tpath = sessions / "transcript.jsonl"
    lines = [
        json.dumps({"type": "user", "content_preview": "hello"}),
        json.dumps({"type": "assistant", "content_preview": "hi"}),
    ]
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from butler.ops.transcript_diagnostics import transcript_fts_drift

    drift = transcript_fts_drift()
    assert drift["transcript_jsonl_lines"] == 2
    assert drift["transcript_fts_stale"] is True


def test_transcript_fts_drift_after_index(tmp_butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    reload_butler_settings()
    sessions = tmp_butler_home / "sessions" / "sess1"
    sessions.mkdir(parents=True)
    tpath = sessions / "transcript.jsonl"
    tpath.write_text(
        json.dumps({"type": "user", "content_preview": "indexed line"}) + "\n",
        encoding="utf-8",
    )
    from butler.core.transcript_fts import index_transcript_file
    from butler.ops.transcript_diagnostics import transcript_fts_drift

    index_transcript_file(tpath, session_key="sess1")
    drift = transcript_fts_drift(session_key="sess1")
    assert drift["transcript_jsonl_lines"] == 1
    assert drift["transcript_fts_rows"] == 1
    assert drift["transcript_fts_stale"] is False


def test_format_embedding_recommends_fastembed(monkeypatch):
    monkeypatch.delenv("BUTLER_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("BUTLER_EMBEDDING_MODEL", raising=False)
    reload_butler_settings()
    from butler.ops.embedding_diagnostics import (
        collect_embedding_snapshot,
        format_embedding_status_line,
    )

    snap = collect_embedding_snapshot()
    assert snap.get("embedding_recommend_fastembed") is True
    line = format_embedding_status_line(snap)
    assert "fastembed" in line or "hashing" in line.lower() or "local" in line


def test_format_vector_sync_lines_after_record():
    from butler.memory.vector_sync_telemetry import (
        format_vector_sync_lines,
        get_vector_sync_times,
        record_vector_sync,
    )

    record_vector_sync("project_pending", project="demo")
    assert get_vector_sync_times()
    lines = format_vector_sync_lines()
    joined = "\n".join(lines)
    assert "最近向量写入" in joined
    assert "project_pending:demo" in joined
