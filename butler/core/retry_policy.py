"""Retry policy helpers for AgentLoop API attempts."""

from __future__ import annotations

from typing import Any

from butler.transport.retry_utils import compute_retry_delay


def retry_delay_for_config(config: Any, attempt_index: int) -> float:
    """Compute retry delay from a LoopConfig-like object."""
    return compute_retry_delay(
        attempt_index,
        base_delay=getattr(config, "retry_delay", 1.0),
        max_delay=getattr(config, "retry_max_delay", 30.0),
        jitter_ratio=getattr(config, "retry_jitter_ratio", 0.25),
    )
