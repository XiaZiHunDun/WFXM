"""PR-F4: sessions list CLI."""

from __future__ import annotations

import json
from pathlib import Path

from butler.cli.sessions_cli import list_sessions


def test_list_sessions_finds_transcript(tmp_path, monkeypatch):
    root = tmp_path / "sessions" / "wx-test"
    root.mkdir(parents=True)
    transcript = root / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "content": "hi"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("butler.cli.sessions_cli._sessions_root", lambda: tmp_path / "sessions")
    rows = list_sessions(search="wx", limit=5)
    assert len(rows) == 1
    assert rows[0]["session_key"] == "wx-test"
    assert rows[0]["transcript_lines"] == 1
