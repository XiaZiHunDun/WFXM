"""AP-5: structured event emission wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.core.metrics_sink import get_default_sink, set_default_sink
from butler.core.structured_events import (
    args_digest,
    emit_llm_api_call,
    emit_retrieval,
    emit_tool_action,
    prompt_hash_from_messages,
)


class _CaptureSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def observe_ms(self, name: str, milliseconds: float) -> None:
        pass

    def inc(self, name: str, value: int = 1) -> None:
        pass

    def record_event(self, name: str, fields: dict, *, session_key: str = "") -> None:
        self.events.append((name, dict(fields)))


@pytest.mark.unit
def test_prompt_hash_no_raw_content():
    h1 = prompt_hash_from_messages([{"role": "user", "content": "secret-a"}])
    h2 = prompt_hash_from_messages([{"role": "user", "content": "secret-b"}])
    assert h1 != h2
    assert len(h1) == 16


@pytest.mark.unit
def test_emit_llm_api_call_uses_sink():
    sink = _CaptureSink()
    saved = get_default_sink()
    set_default_sink(sink)
    try:
        emit_llm_api_call(
            duration_ms=12.5,
            status="ok",
            provider="openai",
            prompt_hash="abc123",
            token_in=10,
            token_out=5,
            session_key="sk",
        )
    finally:
        set_default_sink(saved)
    assert sink.events[0][0] == "llm_api_call"
    assert sink.events[0][1]["prompt_hash"] == "abc123"
    assert "secret" not in str(sink.events)


@pytest.mark.unit
def test_runtime_metrics_sink_records_retrieval_degraded():
    from butler.ops.runtime_metrics_sink import RuntimeMetricsSink
    from butler.ops import runtime_metrics

    sink = RuntimeMetricsSink()
    sink.record_event(
        "retrieval",
        {"mode": "fts-error-fallback", "degraded": True, "fallbacks": 1},
        session_key="sk1",
    )
    snap = runtime_metrics.snapshot_session("sk1")
    assert any("retrieval_degraded" in str(k) for k in snap.get("counters", {}))
