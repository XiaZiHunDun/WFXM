"""429/529 overload retry policy tests."""

from __future__ import annotations

import pytest

from butler.core import llm_retry_ops
from butler.core.llm_retry_errors import handle_classified_llm_error, overload_delay
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.transport.error_classifier import ClassifiedError, FailoverReason


class FakeOverloadedError(Exception):
    status_code = 529


def _handle(classified: ClassifiedError, attempt: int, monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr("butler.core.llm_retry_errors.time.sleep", delays.append)
    step, _, _ = handle_classified_llm_error(
        exc=FakeOverloadedError("529 overloaded"),
        classified=classified,
        attempt=attempt,
        config=LoopConfig(max_retries=3),
        callbacks=LoopCallbacks(),
        messages=[],
        messages_to_send=[],
        tools_to_send=None,
        compress_attempted=False,
        schema_recovery_attempted=False,
        compress_messages=lambda messages: messages,
        prepare_messages=lambda: [],
        diagnostics={},
        try_activate_fallback=lambda: False,
    )
    return step, delays


@pytest.mark.parametrize(
    ("attempt", "expected_action", "expected_delay"),
    [
        (0, "sleep_continue", 5.0),
        (1, "sleep_continue", 10.0),
        (2, "sleep_continue", 20.0),
        (3, "sleep_continue", 40.0),
        (4, "break", None),
    ],
)
def test_overload_backoff_schedule(attempt, expected_action, expected_delay, monkeypatch):
    classified = ClassifiedError(reason=FailoverReason.overloaded, retryable=True)
    step, delays = _handle(classified, attempt, monkeypatch)
    assert step.action == expected_action
    assert delays == ([expected_delay] if expected_delay is not None else [])


def test_rate_limit_uses_overload_backoff(monkeypatch):
    classified = ClassifiedError(reason=FailoverReason.rate_limit, retryable=True)
    step, delays = _handle(classified, 0, monkeypatch)
    assert step.action == "sleep_continue"
    assert delays == [5.0]


def test_overload_delay_capped():
    assert overload_delay(0) == 5.0
    assert overload_delay(3) == 40.0
    assert overload_delay(10) == 60.0


def test_retry_loop_allows_five_overload_attempts(monkeypatch):
    calls = 0

    def fake_execute(**kwargs):
        nonlocal calls
        calls += 1
        raise FakeOverloadedError("529 overloaded")

    monkeypatch.setattr(llm_retry_ops, "execute_llm_call", fake_execute)
    monkeypatch.setattr("butler.core.llm_retry_errors.time.sleep", lambda _: None)

    response, interrupted, last_error = llm_retry_ops.run_llm_with_retry_loop(
        client=object(),
        config=LoopConfig(max_retries=3),
        callbacks=LoopCallbacks(),
        tools=[],
        messages=[],
        diagnostics={},
        prepare_messages=lambda: [],
        compress_messages=lambda messages: messages,
        interrupt_check=lambda: False,
        try_activate_fallback=lambda: False,
        empty_retries=[],
        messages_to_send=[],
        tools_to_send=[],
        cache_fp=None,
    )

    assert calls == 5
    assert response is None
    assert interrupted is False
    assert isinstance(last_error, FakeOverloadedError)
