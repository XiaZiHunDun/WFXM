"""Async delegate scheduling and help."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.runtime.async_delegate import (
    delegate_async_enabled,
    schedule_background_delegate,
    should_delegate_async,
)
from butler.runtime.delegate_job import build_async_delegate_tool_result


@pytest.mark.unit
def test_should_delegate_async_requires_bridge(monkeypatch):
    monkeypatch.setenv("BUTLER_DELEGATE_ASYNC", "1")
    assert not should_delegate_async(bridge=None, depth=0)
    assert should_delegate_async(bridge=MagicMock(), depth=0)
    assert not should_delegate_async(bridge=MagicMock(), depth=1)


@pytest.mark.unit
def test_category_background_false(monkeypatch):
    monkeypatch.setenv("BUTLER_DELEGATE_ASYNC", "1")
    assert not should_delegate_async(
        bridge=MagicMock(),
        depth=0,
        category_meta={"background": False},
    )


@pytest.mark.unit
def test_build_async_tool_result():
    raw = build_async_delegate_tool_result(
        task_id="task_abc",
        child_session_key="wx:1::delegate::task_abc",
        role="dev",
        task_preview="fix bug",
    )
    data = json.loads(raw)
    assert data["background"] is True
    assert data["task_id"] == "task_abc"


@pytest.mark.unit
def test_schedule_background_delegate_marks_task_background(monkeypatch):
    monkeypatch.setenv("BUTLER_DELEGATE_ASYNC", "1")
    finished: list[str] = []
    marked: dict[str, bool] = {}

    def _fake_run(job) -> None:
        finished.append(job.task_id)

    def _fake_update(task_id: str, **fields) -> dict:
        marked[str(task_id)] = bool(fields.get("background"))
        return {"task_id": task_id, **fields}

    monkeypatch.setattr(
        "butler.runtime.async_delegate.run_delegate_job",
        _fake_run,
    )
    monkeypatch.setattr(
        "butler.runtime.task_store.update_task",
        _fake_update,
    )

    from butler.runtime.delegate_job import DelegateJob

    job = DelegateJob(
        agent=MagicMock(),
        orch=MagicMock(),
        user_msg="hi",
        raw_user_msg="hi",
        role="dev",
        task="hi",
        session_key="wx:1",
        child_session_key="wx:1::delegate::task_bg01",
        task_id="task_bg01",
    )
    schedule_background_delegate(job)
    import time

    deadline = time.time() + 2.0
    while time.time() < deadline and not finished:
        time.sleep(0.05)

    assert finished == ["task_bg01"]
    assert marked.get("task_bg01") is True
