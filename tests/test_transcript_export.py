"""Session transcript markdown export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.core.transcript_export import (
    build_session_markdown,
    export_session_markdown,
    load_transcript_rows,
)


@pytest.mark.unit
def test_load_and_build_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setattr(
        "butler.config.get_butler_home",
        lambda: tmp_path,
    )
    sk = "wx:export-1"
    from butler.core.session_transcript import transcript_path

    path = transcript_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "user", "ts": "2026-01-01T00:00:00Z", "content_preview": "hello"},
        {"type": "assistant", "ts": "2026-01-01T00:00:01Z", "content_preview": "hi", "tool_calls": 1},
        {"type": "compaction_turn", "ts": "2026-01-01T00:01:00Z", "iteration": 2},
    ]
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    loaded = load_transcript_rows(sk, max_lines=10)
    assert len(loaded) == 3
    md = build_session_markdown(sk, max_lines=10, include_tasks=False, include_report=False)
    assert "hello" in md
    assert "compaction_turn" in md

    out = export_session_markdown(sk, max_lines=10)
    assert out["ok"]
    assert Path(out["path"]).is_file()
    assert "wx_export-1" in out["path"] or "wx:export-1" in out["path"] or out["path"].endswith(".md")


@pytest.mark.unit
def test_export_to_project_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    sk = "wx:proj-export"
    from butler.core.session_transcript import transcript_path

    path = transcript_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "user", "content_preview": "x"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ws = tmp_path / "proj"
    ws.mkdir()
    result = export_session_markdown(sk, max_lines=50, workspace=ws)
    assert result["ok"]
    assert (ws / ".butler" / "exports").is_dir()
