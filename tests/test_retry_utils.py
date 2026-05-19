"""Retry backoff utility tests."""

from butler.transport.retry_utils import compute_retry_delay


def test_exponential_backoff_without_jitter():
    delays = [
        compute_retry_delay(i, base_delay=0.5, max_delay=10, jitter_ratio=0)
        for i in range(4)
    ]

    assert delays == [0.5, 1.0, 2.0, 4.0]


def test_backoff_is_capped():
    delay = compute_retry_delay(
        attempt_index=10,
        base_delay=1.0,
        max_delay=3.0,
        jitter_ratio=0,
    )

    assert delay == 3.0


def test_jitter_adds_delay_with_configured_ratio():
    low = compute_retry_delay(
        attempt_index=1,
        base_delay=1.0,
        max_delay=10,
        jitter_ratio=0.25,
        random_fn=lambda: 0.0,
    )
    mid = compute_retry_delay(
        attempt_index=1,
        base_delay=1.0,
        max_delay=10,
        jitter_ratio=0.25,
        random_fn=lambda: 0.5,
    )
    high = compute_retry_delay(
        attempt_index=1,
        base_delay=1.0,
        max_delay=10,
        jitter_ratio=0.25,
        random_fn=lambda: 1.0,
    )

    assert low == 2.0
    assert mid == 2.25
    assert high == 2.5


def test_zero_base_delay_stays_zero():
    assert compute_retry_delay(3, base_delay=0, max_delay=10, jitter_ratio=0.5) == 0


def test_jitter_never_returns_negative_delay():
    delay = compute_retry_delay(
        attempt_index=1,
        base_delay=1.0,
        max_delay=10.0,
        jitter_ratio=2.0,
        random_fn=lambda: 0.0,
    )

    assert delay == 2.0


def test_jittered_delay_respects_max_delay():
    delay = compute_retry_delay(
        attempt_index=10,
        base_delay=1.0,
        max_delay=3.0,
        jitter_ratio=0.5,
        random_fn=lambda: 1.0,
    )

    assert delay == 3.0
