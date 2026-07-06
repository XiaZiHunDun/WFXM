"""Inter-message delay for WeChat multi-chunk outbound (OpenClaw human-delay subset)."""

from __future__ import annotations

import os
import random


def outbound_block_delay_ms() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_OUTBOUND_BLOCK_DELAY_MS", 0, min=0))
    except ValueError:
        return 0


def inter_chunk_delay_seconds(*, fallback_seconds: float = 0.0) -> float:
    """Random delay in seconds; uses BUTLER_OUTBOUND_BLOCK_DELAY_MS when set."""
    ms = outbound_block_delay_ms()
    if ms > 0:
        lo = ms * 0.5
        hi = ms * 1.5
        return random.uniform(lo, hi) / 1000.0
    return max(0.0, float(fallback_seconds))
