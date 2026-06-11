"""Tests for butler.ops.delegate_judge."""

from __future__ import annotations

from butler.ops.delegate_judge import (
    judge_delegate_outcome,
    judge_mode,
    maybe_judge_and_push,
)


def test_judge_success_with_verify(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_DELEGATE_JUDGE", "heuristic")
    result = judge_delegate_outcome(
        success=True,
        dev_engine={"verify_passed": True, "edits": 1, "fixes": 0},
        task="fix hello.py",
        summary="fixed greet return value",
    )
    assert result is not None
    assert result.score >= 0.8


def test_judge_verify_failed(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_DELEGATE_JUDGE", "heuristic")
    result = judge_delegate_outcome(
        success=True,
        dev_engine={"verify_passed": False, "edits": 2},
        issues=["tests failed"],
    )
    assert result is not None
    assert result.score < 0.8
    assert result.dimensions["test_adequacy"] <= 0.3


def test_judge_off_returns_none(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_DELEGATE_JUDGE", "off")
    assert judge_delegate_outcome(success=False) is None


def test_maybe_judge_and_push_no_trace(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_DELEGATE_JUDGE", "heuristic")
    result = maybe_judge_and_push(success=True, trace_id="")
    assert result is not None


def test_judge_mode_default(monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_DELEGATE_JUDGE", raising=False)
    assert judge_mode() == "heuristic"
