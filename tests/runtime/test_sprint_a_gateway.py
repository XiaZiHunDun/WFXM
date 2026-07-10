"""Sprint A: external_id idempotency, task stale, recovery metrics, tool masking."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from butler.gateway.inbound_idempotency import (
    check_and_reserve_inbound,
    complete_inbound,
    reset_session,
)
from butler.runtime.task_store import (
    create_task,
    is_task_stale,
    mark_stale_tasks,
    task_stale_minutes,
)
from butler.core.tool_output_masking import apply_unified_tool_masking, tool_masking_enabled
from butler.core.context_compressor import truncate_tool_responses_to_budget
from butler.ops.retry_buckets import format_recovery_bucket_lines, record_recovery_event


def test_external_id_duplicate_rejected():
    reset_session("s-idem")
    assert check_and_reserve_inbound("s-idem", "msg-001").accept
    complete_inbound("s-idem", "msg-001")
    dup = check_and_reserve_inbound("s-idem", "msg-001")
    assert not dup.accept
    assert dup.reason == "duplicate_done"
    reset_session("s-idem")


def test_external_id_inflight_duplicate():
    reset_session("s-inflight")
    assert check_and_reserve_inbound("s-inflight", "msg-002").accept
    inflight = check_and_reserve_inbound("s-inflight", "msg-002")
    assert not inflight.accept
    assert inflight.reason == "duplicate_inflight"
    reset_session("s-inflight")


def test_task_stale_detection(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "bh"))
    monkeypatch.setenv("BUTLER_TASK_STALE_MINUTES", "30")
    rec = create_task(session_key="stale-sess", role="dev", task_preview="long job")
    rec["updated_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=task_stale_minutes() + 5)
    ).isoformat()
    rec["status"] = "running"
    from butler.runtime import task_store

    task_store._write(str(rec["task_id"]), rec)
    assert is_task_stale(rec)
    stale = mark_stale_tasks("stale-sess", auto_fail=False)
    assert len(stale) >= 1


def test_recovery_metrics_format():
    record_recovery_event("schema_recovery")
    lines = format_recovery_bucket_lines()
    assert any("schema_recovery" in ln for ln in lines)


def test_truncate_tool_responses_to_budget():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "x" * 400_000},
    ]
    out = truncate_tool_responses_to_budget(msgs)
    assert "tool-result-truncated" in str(out[1].get("content") or "")


def test_unified_tool_masking_runs():
    if not tool_masking_enabled():
        pytest.skip("masking disabled")
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "read_file"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "a" * 200_000},
        {"role": "assistant", "tool_calls": [{"id": "2", "function": {"name": "read_file"}}]},
        {"role": "tool", "tool_call_id": "2", "content": "recent"},
    ]
    out = apply_unified_tool_masking(msgs)
    assert len(out) == len(msgs)
