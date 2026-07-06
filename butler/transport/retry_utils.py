"""Retry backoff helpers for transient LLM API failures."""

from __future__ import annotations

import random
from typing import Callable


def compute_retry_delay(
    attempt_index: int,
    *,
    base_delay: float,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.25,
    random_fn: Callable[[], float] = random.random,
) -> float:
    """Return exponential backoff delay with additive jitter.

    ``attempt_index`` is zero-based for the sleep before the next retry.
    """
    base = max(0.0, float(base_delay))
    if base == 0:
        return 0.0

    cap = max(0.0, float(max_delay))
    jitter = max(0.0, float(jitter_ratio))
    delay = min(base * (2 ** max(0, attempt_index)), cap)
    if delay == 0 or jitter == 0:
        return float(delay)

    rand = min(1.0, max(0.0, float(random_fn())))
    return float(min(cap, delay + (delay * jitter * rand)))
