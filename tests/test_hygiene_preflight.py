"""Tests for AgentLoop hygiene preflight extraction."""

from unittest.mock import Mock

import pytest

from butler.core.hygiene_preflight import run_hygiene_preflight


def test_hygiene_preflight_skips_short_history_and_clears_stale_diagnostics():
    diagnostics = {
        "hygiene_compressed": True,
        "hygiene_estimated_tokens": 900,
        "hygiene_messages_after": 1,
    }
    messages = [{"role": "user", "content": "short"}]

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 1,
        compress=Mock(),
    )

    assert result.compressed is False
    assert result.messages == messages
    assert diagnostics["hygiene_checked"] is True
    assert diagnostics["hygiene_compressed"] is False
    assert "hygiene_estimated_tokens" not in diagnostics
    assert "hygiene_messages_after" not in diagnostics


def test_hygiene_preflight_compresses_when_over_auto_threshold():
    diagnostics: dict[str, object] = {}
    messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]
    compressed = [{"role": "user", "content": "summary"}]
    compress = Mock(return_value=compressed)

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 100_000,
        compress=compress,
    )

    assert result.compressed is True
    assert result.messages == compressed
    assert diagnostics["hygiene_compressed"] is True
    assert compress.call_args.kwargs["threshold_ratio"] == 0.0


def test_hygiene_preflight_uses_hard_message_limit_without_token_threshold():
    diagnostics: dict[str, object] = {}
    messages = [{"role": "user", "content": f"short {i}"} for i in range(10)]
    compressed = [{"role": "user", "content": "summary"}]
    compress = Mock(return_value=compressed)

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 10,
        compress=compress,
        hard_message_limit=5,
    )

    assert result.compressed is True
    assert result.messages == compressed
    assert compress.call_args.kwargs["threshold_ratio"] == 0.0


def test_hygiene_preflight_circuit_breaker_skips_compress():
    diagnostics: dict[str, object] = {}
    messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]
    compress = Mock()

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 100_000,
        compress=compress,
        consecutive_compact_failures=3,
    )

    assert result.compressed is False
    assert diagnostics.get("context_compact_circuit_open") is True
    compress.assert_not_called()


def test_hygiene_preflight_noop_does_not_increment_failures():
    diagnostics: dict[str, object] = {}
    messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]
    compress = Mock(return_value=messages)

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 100_000,
        compress=compress,
        consecutive_compact_failures=2,
    )

    assert result.compressed is False
    assert diagnostics.get("hygiene_compact_noop") is True
    assert diagnostics.get("context_compact_consecutive_failures") == 2


def test_hygiene_preflight_exception_increments_failures():
    diagnostics: dict[str, object] = {}
    messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]

    def _boom(*_a, **_k):
        raise RuntimeError("compact api failed")

    result = run_hygiene_preflight(
        messages,
        max_context_tokens=128_000,
        diagnostics=diagnostics,
        estimate_tokens=lambda _: 100_000,
        compress=_boom,
        consecutive_compact_failures=1,
    )

    assert result.compressed is False
    assert diagnostics.get("context_compact_consecutive_failures") == 2
    assert diagnostics.get("hygiene_compact_failed") is True
