"""Tests for butler.ops.delegate_failure_capture."""

from __future__ import annotations

import json
from unittest.mock import patch

from butler.ops.delegate_failure_capture import (
    DATASET_NAME,
    build_failure_dataset_item,
    capture_delegate_failure,
    capture_enabled,
    failure_audit_summary,
    sanitize_text,
    should_capture_failure,
)


def test_sanitize_text_redacts_secrets_and_home():
    home = "/home/testuser"
    text = f"{home}/.env API_KEY=sk-secret12345 token=abc"
    out = sanitize_text(text.replace("/home/testuser", str(__import__("pathlib").Path.home())))
    assert "sk-secret" not in out
    assert "[REDACTED]" in out or "~" in out


def test_should_capture_dev_failure(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "1")
    assert should_capture_failure(role="dev", success=False) is True
    assert should_capture_failure(role="dev", success=True, dev_engine={"verify_passed": False}) is True
    assert should_capture_failure(role="dev", success=True, dev_engine={"verify_passed": True}) is False
    assert should_capture_failure(role="content", success=False) is False


def test_should_capture_all_roles(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "all")
    assert should_capture_failure(role="content", success=False) is True


def test_build_failure_dataset_item():
    item = build_failure_dataset_item(
        role="dev",
        task="fix hello.py",
        context="workspace=/tmp",
        issues=["verify failed"],
        trace_id="trace-1",
        task_id="task-1",
        dev_engine={"verify_passed": False, "edits": 2},
        failure_reason="verify_failed",
    )
    assert item.input["task"] == "fix hello.py"
    assert item.metadata["trace_id"] == "trace-1"
    assert item.source_id == "task-1"


@patch("butler.ops.eval_bridge.push_score", return_value=True)
@patch("butler.ops.eval_bridge.push_dataset_item", return_value=True)
@patch("butler.ops.eval_bridge.create_dataset", return_value="ds-1")
def test_capture_delegate_failure_pushes(mock_create, mock_item, mock_score, monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "1")

    summary = capture_delegate_failure(
        role="dev",
        task="fix syntax",
        success=False,
        trace_id="t-99",
        task_id="tid-1",
        issues=["missing colon"],
    )
    assert summary["captured"] is True
    assert summary["dataset_pushed"] is True
    assert summary["score_pushed"] is True
    mock_create.assert_called_once_with(
        DATASET_NAME,
        "Production dev delegate failures for annotation and B9 expansion",
    )

    audit = failure_audit_summary()
    assert audit["total"] >= 1


def test_capture_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "0")
    summary = capture_delegate_failure(role="dev", task="x", success=False)
    assert summary["captured"] is False


def test_capture_enabled_follows_langfuse(monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", raising=False)
    monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
    assert capture_enabled() is True
    monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "0")
    assert capture_enabled() is False
