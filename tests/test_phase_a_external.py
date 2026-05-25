"""Phase A: Hermes/LangChain/Dify/Langflow inspired gateway + context features."""

from __future__ import annotations

import json
import time

import pytest

from butler.core.compaction_cutoff import find_safe_tail_start
from butler.core.auto_continue import (
    capture_auto_continue_pending,
    clear_auto_continue_pending,
    is_continue_marker,
    resolve_auto_continue_user_message,
)
from butler.core.hygiene_preflight import run_hygiene_preflight
from butler.gateway.outbound_events import workflow_event
from butler.transport.memory_context_scrubber import StreamingMemoryContextScrubber


@pytest.mark.unit
def test_find_safe_tail_start_keeps_tool_pairs():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "function": {"name": "read_file"}}]},
        {"role": "tool", "tool_call_id": "tc1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]
    # Cut before assistant+tool pair must move tail start past the tool result
    assert find_safe_tail_start(messages, 1) == 3
    assert find_safe_tail_start(messages, 2) == 3


@pytest.mark.unit
def test_memory_context_scrubber_across_chunks():
    scrub = StreamingMemoryContextScrubber()
    part1 = scrub.feed("hello <memory-")
    part2 = scrub.feed("context>secret</memory-context> world")
    assert "secret" not in (part1 + part2)
    assert "world" in part2


@pytest.mark.unit
def test_auto_continue_fresh_pending(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.core.auto_continue._sessions_root", lambda: tmp_path)
    sk = "wx:continue-test"
    capture_auto_continue_pending(sk, user_preview="finish the refactor")
    assert is_continue_marker("继续")
    resolved = resolve_auto_continue_user_message(sk, "继续")
    assert resolved is not None
    assert "refactor" in resolved
    assert resolve_auto_continue_user_message(sk, "继续") is None


@pytest.mark.unit
def test_hygiene_preflight_prefers_usage_metadata():
    diag: dict = {
        "last_usage_prompt_tokens": 90000,
        "last_usage_completion_tokens": 5000,
        "context_usage_billable_total": 95000,
    }
    messages = [{"role": "user", "content": "x" * 200}] * 20

    def _est(msgs):
        return 1000

    def _compress(msgs, **kwargs):
        return msgs[:5]

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128000,
        diagnostics=diag,
        estimate_tokens=_est,
        compress=_compress,
        max_output_tokens=4096,
    )
    assert diag.get("hygiene_compact_trigger_source") == "usage_metadata"
    assert int(diag.get("hygiene_trigger_tokens") or 0) >= 95000


@pytest.mark.unit
def test_workflow_event_payload():
    ev = workflow_event("demo", "step1", phase="fail", step_index=1, step_total=3, error="timeout")
    d = ev.to_dict()
    assert d["kind"] == "workflow_step"
    assert d["phase"] == "fail"
    assert d["step_index"] == 1
