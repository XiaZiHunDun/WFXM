"""Tests for butler.gateway.durable_outbox."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from butler.gateway.durable_outbox import (
    durable_outbox_enabled,
    enqueue_outbox_message,
    mark_outbox_failed,
    mark_outbox_sent,
    outbox_counts,
)


@pytest.fixture(autouse=True)
def _patch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / ".butler"))
    monkeypatch.setenv("BUTLER_GATEWAY_DURABLE_OUTBOX", "1")
    import butler.config as _cfg
    _cfg._settings = None
    yield
    _cfg._settings = None


def test_enqueue_creates_pending_file(tmp_path: Path):
    entry_id = enqueue_outbox_message("chat_123", "hello", kind="completion")
    assert entry_id
    pending = tmp_path / ".butler" / "gateway_outbox" / "pending" / f"{entry_id}.json"
    assert pending.is_file()
    row = json.loads(pending.read_text())
    assert row["chat_id"] == "chat_123"
    assert row["status"] == "pending"
    assert row["body"] == "hello"


def test_mark_sent_moves_to_sent_dir(tmp_path: Path):
    entry_id = enqueue_outbox_message("chat_1", "body", kind="turn")
    assert mark_outbox_sent(entry_id)
    pending = tmp_path / ".butler" / "gateway_outbox" / "pending" / f"{entry_id}.json"
    sent = tmp_path / ".butler" / "gateway_outbox" / "sent" / f"{entry_id}.json"
    assert not pending.exists()
    assert sent.is_file()
    row = json.loads(sent.read_text())
    assert row["status"] == "sent"
    assert "sent_at" in row
    assert row["attempts"] == 1


def test_mark_failed_moves_to_failed_dir(tmp_path: Path):
    entry_id = enqueue_outbox_message("chat_2", "body2", kind="delegate")
    assert mark_outbox_failed(entry_id, error="timeout")
    failed = tmp_path / ".butler" / "gateway_outbox" / "failed" / f"{entry_id}.json"
    assert failed.is_file()
    row = json.loads(failed.read_text())
    assert row["status"] == "failed"
    assert row["error"] == "timeout"


def test_mark_nonexistent_entry_returns_false():
    assert not mark_outbox_sent("nonexistent_id")
    assert not mark_outbox_failed("nonexistent_id")


def test_outbox_counts_aggregates_correctly(tmp_path: Path):
    e1 = enqueue_outbox_message("c1", "a", kind="completion")
    e2 = enqueue_outbox_message("c1", "b", kind="completion")
    e3 = enqueue_outbox_message("c2", "c", kind="turn")
    mark_outbox_sent(e1)
    mark_outbox_failed(e3, error="err")
    counts = outbox_counts()
    assert counts["pending"] == 1
    assert counts["sent"] == 1
    assert counts["failed"] == 1


def test_outbox_counts_filter_by_chat_id(tmp_path: Path):
    enqueue_outbox_message("c1", "x", kind="completion")
    enqueue_outbox_message("c2", "y", kind="completion")
    counts = outbox_counts(chat_id="c1")
    assert counts["pending"] == 1


def test_disabled_outbox_returns_empty_string(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DURABLE_OUTBOX", "0")
    result = enqueue_outbox_message("c1", "body", kind="completion")
    assert result == ""


def test_trim_respects_max_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DURABLE_OUTBOX_MAX", "10")
    import time
    for i in range(15):
        enqueue_outbox_message("c", f"msg_{i}", kind="completion")
        time.sleep(0.01)
    pending_dir = tmp_path / ".butler" / "gateway_outbox" / "pending"
    assert len(list(pending_dir.glob("*.json"))) <= 10


def test_body_truncated_to_4000_chars(tmp_path: Path):
    long_body = "x" * 5000
    entry_id = enqueue_outbox_message("c1", long_body, kind="completion")
    pending = tmp_path / ".butler" / "gateway_outbox" / "pending" / f"{entry_id}.json"
    row = json.loads(pending.read_text())
    assert len(row["body"]) == 4000
