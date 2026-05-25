"""OpenCode P2 features: transcript compact events, post-commit, todos, hooks."""

from __future__ import annotations

import json

import pytest

from butler.core.post_commit import (
    clear_after_commit_queue,
    enqueue_after_commit,
    flush_after_commit,
    pending_after_commit_count,
)
from butler.core.session_todos import (
    load_session_todos,
    replace_session_todos,
    todos_path,
)
from butler.core.session_transcript import (
    load_transcript_tail,
    record_compact_done,
    record_compact_scheduled,
    transcript_path,
)
from butler.gateway.hooks import clear_hooks, register_hook, trigger_hooks_mutating


def test_post_commit_queue_runs_in_order():
    clear_after_commit_queue()
    seen: list[int] = []

    enqueue_after_commit(lambda: seen.append(1))
    enqueue_after_commit(lambda: seen.append(2))
    assert pending_after_commit_count() == 2
    assert flush_after_commit() == 2
    assert seen == [1, 2]
    assert pending_after_commit_count() == 0


def test_session_todos_replace_all(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    replace_session_todos(
        "cli:test",
        [
            {"content": "first", "status": "pending"},
            {"content": "done", "status": "completed"},
        ],
    )
    items = load_session_todos("cli:test")
    assert len(items) == 2
    replace_session_todos("cli:test", [])
    assert load_session_todos("cli:test") == []
    assert todos_path("cli:test").is_file()


def test_transcript_compact_events(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "wx:p2"
    record_compact_scheduled(sk, source="test", messages_before=10, tokens_estimated=5000)
    record_compact_done(sk, source="test", messages_after=4, tokens_after=1200, summary_chars=800)
    rows = load_transcript_tail(sk, max_lines=10)
    types = [r.get("type") for r in rows]
    assert "compact_scheduled" in types
    assert "compact_done" in types
    assert transcript_path(sk).is_file()


def test_trigger_hooks_mutating_merges_output():
    clear_hooks("test_mutate")
    register_hook(
        "test_mutate",
        lambda inp, out: out.update({"extra": inp.get("n", 0) + 1}),
    )
    result = trigger_hooks_mutating("test_mutate", {"n": 1}, {"base": True})
    assert result["base"] is True
    assert result["extra"] == 2
    clear_hooks("test_mutate")


def test_transcript_diagnostic_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "diag"
    record_compact_scheduled(sk, source="test")
    from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines

    lines = format_transcript_diagnostic_lines(sk)
    assert any("Transcript" in ln for ln in lines)
