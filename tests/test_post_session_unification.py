"""M3: single post_session runner, watermark dedup, mutex."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from butler.session.lifecycle import (
    drain_post_session_buffer,
    get_post_session_pairs_extracted,
    record_post_session_turn,
    reset_post_session_watermark,
    run_post_session_extraction,
    trigger_session_end,
)


def _orch_with_provider():
    orch = MagicMock()
    orch.butler_memory = MagicMock()
    orch._project_memory = None
    orch._skill_manager = MagicMock()
    orch.project_manager.current_project = "proj"
    provider = MagicMock()
    provider._turn_buffer = []
    provider._orchestrator = orch
    orch.memory_provider = provider
    return orch, provider


def test_incremental_flush_calls_processor_once(monkeypatch):
    monkeypatch.setenv("BUTLER_POST_SESSION_BUFFER_MESSAGES", "4")
    orch, provider = _orch_with_provider()
    processor = MagicMock()
    processor.process = MagicMock(
        return_value={"memory_updates": 1, "skills_extracted": 0, "errors": []}
    )

    with patch(
        "butler.session.post_session_ops._execute_post_session",
        return_value={"memory_updates": 1, "skills_extracted": 0},
    ) as execute:
        record_post_session_turn(orch, provider, "u1", "a1", session_id="s1")
        record_post_session_turn(orch, provider, "u2", "a2", session_id="s1")
        time.sleep(0.3)

    execute.assert_called_once()
    assert get_post_session_pairs_extracted(orch, "s1") == 2
    assert provider._turn_buffer == []


def test_session_end_skips_already_extracted_pairs():
    orch, provider = _orch_with_provider()
    orch._post_session_pairs_extracted = {"s1": 4}
    loop = MagicMock()
    loop.messages = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "5"},
        {"role": "assistant", "content": "6"},
        {"role": "user", "content": "7"},
        {"role": "assistant", "content": "8"},
    ]
    with patch("butler.session.post_session_ops._execute_post_session") as execute:
        result = trigger_session_end(orch, loop, session_id="s1")

    assert result["reason"] == "short_history"
    execute.assert_not_called()
    reset_post_session_watermark(orch, "s1")


def test_session_end_processes_only_tail_after_watermark():
    orch, provider = _orch_with_provider()
    orch._post_session_pairs_extracted = {"s1": 2}
    loop = MagicMock()
    loop.messages = [
        {"role": "user", "content": "x" * 80},
        {"role": "assistant", "content": "y" * 80},
        {"role": "user", "content": "x" * 80},
        {"role": "assistant", "content": "y" * 80},
        {"role": "user", "content": "x" * 80},
        {"role": "assistant", "content": "y" * 80},
        {"role": "user", "content": "new"},
        {"role": "assistant", "content": "tail"},
    ]
    captured: list[list] = []

    def _capture(o, msgs):
        captured.append(list(msgs))
        return {"memory_updates": 1, "skills_extracted": 0}

    with patch("butler.session.post_session_ops._execute_post_session", side_effect=_capture):
        result = trigger_session_end(orch, loop, session_id="s1")

    assert result.get("memory_updates") == 1
    assert len(captured) == 1
    assert len(captured[0]) == 4
    assert captured[0][-2]["content"] == "new"


def test_post_session_lock_serializes_calls():
    orch, _ = _orch_with_provider()
    order: list[str] = []

    def slow_execute(o, msgs):
        order.append("start")
        time.sleep(0.15)
        order.append("end")
        return {"memory_updates": 0, "skills_extracted": 0}

    msgs = [
        {"role": "user", "content": "a" * 80},
        {"role": "assistant", "content": "b" * 80},
        {"role": "user", "content": "c" * 80},
        {"role": "assistant", "content": "d" * 80},
    ]

    with patch("butler.session.post_session_ops._execute_post_session", side_effect=slow_execute):
        run_post_session_extraction(orch, msgs, background=True, session_id="lock")
        run_post_session_extraction(orch, msgs, background=False, session_id="lock")

    time.sleep(0.5)
    assert order.count("start") == 2
    assert order.index("end") < order.index("start", 1) or order == ["start", "end", "start", "end"]
