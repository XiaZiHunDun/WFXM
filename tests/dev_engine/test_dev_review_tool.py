"""Tests for dev_review tool integration."""

from __future__ import annotations

import pytest

from butler.dev_engine.dev_loop import create_dev_state
from butler.dev_engine.dev_state import EditRecord
from butler.dev_engine.dev_tools import clear_state, set_state, tool_dev_review


@pytest.mark.unit
def test_dev_review_updates_state(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_DEV_ENGINE", "1")
    sk = "test_review_sk"
    clear_state(sk)
    state = create_dev_state("review task")
    set_state(sk, state)

    fp = tmp_path / "bad.py"
    fp.write_text("password = 'supersecretvalue123'\n", encoding="utf-8")
    state.edit_history.append(
        EditRecord(operation="write", path="bad.py", new_content=fp.read_text(encoding="utf-8"))
    )

    out = tool_dev_review(str(tmp_path), session_key=sk)
    assert out["passed"] is False
    assert out["findings_count"] >= 1
    assert state.review_summary.findings_count >= 1
    clear_state(sk)


@pytest.mark.unit
def test_dev_review_clean_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_DEV_ENGINE", "1")
    sk = "test_review_clean"
    clear_state(sk)
    fp = tmp_path / "ok.py"
    fp.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    out = tool_dev_review(str(tmp_path), changed_files=["ok.py"], session_key=sk)
    assert out["passed"] is True
    clear_state(sk)
