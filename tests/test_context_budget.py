"""Tests for context token budgeting tiers."""

from butler.core.context_budget import (
    compact_circuit_open,
    calculate_token_warning_state,
    format_context_budget_line,
    get_auto_compact_threshold,
    get_effective_context_window,
)


def test_effective_window_and_auto_threshold_cc_style(monkeypatch):
    monkeypatch.delenv("BUTLER_CONTEXT_WARNING_BUFFER", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_COMPACT_RESERVE", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_OUTPUT_RESERVE", raising=False)
    eff = get_effective_context_window(128_000)
    assert eff == 128_000 - 20_000
    auto = get_auto_compact_threshold(128_000)
    assert auto == eff - 13_000


def test_calculate_token_warning_state_tiers(monkeypatch):
    monkeypatch.delenv("BUTLER_CONTEXT_WARNING_BUFFER", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_COMPACT_RESERVE", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_OUTPUT_RESERVE", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_BLOCKING_BUFFER", raising=False)

    from butler.core.context_budget import load_context_thresholds

    t = load_context_thresholds(128_000)

    assert calculate_token_warning_state(10_000, max_context_tokens=128_000)["context_tier"] == "ok"

    warn = calculate_token_warning_state(t.warn_at_tokens + 1, max_context_tokens=128_000)
    assert warn["context_tier"] == "warn"

    critical = calculate_token_warning_state(t.auto_compact_at_tokens + 1, max_context_tokens=128_000)
    assert critical["context_tier"] == "critical"
    assert critical["context_is_above_auto_compact"] is True

    blocking = calculate_token_warning_state(t.blocking_at_tokens + 1, max_context_tokens=128_000)
    assert blocking["context_tier"] == "blocking"


def test_compact_circuit_open():
    assert not compact_circuit_open(2, max_context_tokens=128000)
    assert compact_circuit_open(3, max_context_tokens=128000)


def test_format_context_budget_line_circuit():
    line = format_context_budget_line({
        "context_estimated_tokens": 70000,
        "context_effective_tokens": 108000,
        "context_tier_label": "临界",
        "context_compact_circuit_open": True,
        "context_compact_consecutive_failures": 3,
        "context_auto_compact_enabled": True,
        "context_tokens_until_auto_compact": 0,
        "context_blocking_at_tokens": 105000,
    })
    assert "压缩熔断" in line
    assert "阻塞线" in line
