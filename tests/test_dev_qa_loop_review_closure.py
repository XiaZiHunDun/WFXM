"""Workflow QA + review closure integration tests."""

from __future__ import annotations

import json

import pytest

from butler.core.plan_snapshot import qa_response_is_fail
from butler.core.review_context_adapter import parse_llm_review_text, review_text_passed
from butler.dev_engine.review_closure import (
    maybe_persist_review_closure,
    nexus_sprint_review_handoff,
    summarize_review_for_delegate,
)


@pytest.mark.unit
def test_qa_fail_aligns_with_review_adapter():
    text = "FAIL\nblocking issue in foo.py"
    assert qa_response_is_fail(text)
    view = parse_llm_review_text(text)
    assert view.passed is False
    assert review_text_passed(text) is False


@pytest.mark.unit
def test_qa_pass_aligns():
    text = "PASS\nverified read_file"
    assert not qa_response_is_fail(text)
    assert review_text_passed(text)


@pytest.mark.unit
def test_review_closure_persist(tmp_path, monkeypatch):
    path = tmp_path / "reflexion.jsonl"
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE", "1")
    monkeypatch.setenv("BUTLER_REFLECTION_CLOSURE_WRITE", "1")
    monkeypatch.setattr("butler.core.reflection_closure._experience_path", lambda: path)
    view = parse_llm_review_text("FAIL\nneeds fix")
    maybe_persist_review_closure(view, session_key="sk1", source="test")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["trigger"] == "review_fail"


@pytest.mark.unit
def test_nexus_sprint_handoff():
    assert "nexus-micro" in nexus_sprint_review_handoff("nexus-sprint")
    assert nexus_sprint_review_handoff("deep") == ""


@pytest.mark.unit
def test_summarize_for_delegate():
    view = parse_llm_review_text("FAIL\nissue")
    summary = summarize_review_for_delegate(view)
    assert summary["passed"] is False
    assert summary["findings_count"] >= 1
