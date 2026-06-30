"""Unit tests for reflection closure write + inject."""

from __future__ import annotations

import json

import pytest

from butler.core.reflection_closure import (
    build_reflect_closure_banner,
    load_recent_reflect_hints,
    maybe_persist_reflect_closure,
    persist_reflect_episode,
)


@pytest.mark.unit
def test_persist_and_load_hints(tmp_path, monkeypatch):
    path = tmp_path / "reflexion.jsonl"
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE", "1")
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE_WRITE", "1")
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE_INJECT", "1")
    monkeypatch.setattr("butler.core.reflection_closure._experience_path", lambda: path)

    persist_reflect_episode(
        trigger="verify_fail",
        cause="tests failed",
        strategy="retry_fix",
        session_key="sk1",
        source="test",
    )
    hints = load_recent_reflect_hints(session_key="sk1", limit=2)
    assert len(hints) == 1
    assert "verify_fail" in hints[0]
    banner = build_reflect_closure_banner(session_key="sk1")
    assert "Reflection" in banner
    assert "verify_fail" in banner


@pytest.mark.unit
def test_maybe_persist_respects_closure_off(monkeypatch, tmp_path):
    path = tmp_path / "reflexion.jsonl"
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE", "0")
    monkeypatch.setattr("butler.core.reflection_closure._experience_path", lambda: path)
    maybe_persist_reflect_closure(trigger="stuck", cause="x", session_key="sk")
    assert not path.exists()


@pytest.mark.unit
def test_load_reads_jsonl_rows(tmp_path, monkeypatch):
    path = tmp_path / "reflexion.jsonl"
    path.write_text(
        json.dumps({"trigger": "doom_loop", "cause": "repeat", "strategy": "stop"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE", "1")
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE_INJECT", "1")
    monkeypatch.setattr("butler.core.reflection_closure._experience_path", lambda: path)
    hints = load_recent_reflect_hints(limit=1)
    assert hints and "doom_loop" in hints[0]
