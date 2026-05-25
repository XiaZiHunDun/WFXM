"""Tests for zero-dependency runtime metrics."""

from __future__ import annotations

from butler.ops import runtime_metrics as rm


def setup_function() -> None:
    rm.reset_global()


def test_inc_and_counter_value() -> None:
    rm.inc("llm_request", labels={"outcome": "ok", "provider": "test"})
    rm.inc("llm_request", labels={"outcome": "ok", "provider": "test"})
    assert rm.counter_value("llm_request", labels={"outcome": "ok", "provider": "test"}) == 2


def test_session_scoped_counters_isolated() -> None:
    rm.inc("gateway_completion_push", labels={"outcome": "sent"}, session_key="sess-a")
    rm.inc("gateway_completion_push", labels={"outcome": "sent"}, session_key="sess-b")
    assert rm.counter_value(
        "gateway_completion_push",
        labels={"outcome": "sent"},
        session_key="sess-a",
    ) == 1
    snap = rm.snapshot_global()
    assert "gateway_completion_push{outcome=sent}" not in (snap.get("counters") or {})


def test_reset_session_clears_session_metrics_only() -> None:
    rm.inc("llm_request", labels={"outcome": "ok"})
    rm.inc("gateway_completion_push", labels={"outcome": "sent"}, session_key="sk1")
    rm.reset_session("sk1")
    assert rm.counter_value(
        "gateway_completion_push",
        labels={"outcome": "sent"},
        session_key="sk1",
    ) == 0
    assert rm.counter_value("llm_request", labels={"outcome": "ok"}) == 1


def test_reset_counters_named() -> None:
    rm.inc("gateway_completion_push", labels={"outcome": "sent"}, session_key="a")
    rm.inc("gateway_completion_push", labels={"outcome": "failed"}, session_key="b")
    rm.reset_counters_named("gateway_completion_push")
    assert rm.counter_value(
        "gateway_completion_push",
        labels={"outcome": "sent"},
        session_key="a",
    ) == 0


def test_observe_ms_histogram_in_snapshot() -> None:
    for ms in (10.0, 20.0, 30.0, 40.0, 50.0):
        rm.observe_ms("turn_duration", ms, labels={"transition": "turn_completed"})
    snap = rm.snapshot_global()
    hist = (snap.get("histograms") or {}).get("turn_duration{transition=turn_completed}")
    assert hist is not None
    assert hist["count"] == 5
    assert hist["p50_ms"] is not None


def test_format_metrics_diagnostic_lines() -> None:
    rm.inc("llm_request", labels={"outcome": "ok", "provider": "p"})
    lines = rm.format_metrics_diagnostic_lines(session_key="wechat:u1")
    assert any("运行指标（进程累计）" in ln for ln in lines)
    assert any("llm_request" in ln for ln in lines)


def test_completion_telemetry_wrapper() -> None:
    from butler.gateway.completion_telemetry import (
        completion_push_stats,
        record_completion_push_sent,
        reset_completion_telemetry,
    )

    reset_completion_telemetry("sk")
    record_completion_push_sent(session_key="sk")
    assert completion_push_stats("sk")["sent"] == 1
    reset_completion_telemetry("sk")
    assert completion_push_stats("sk")["sent"] == 0
