"""Speech STT telemetry fail-closed helpers (P0-A)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def transcribe_with_stt_telemetry(
    run: Callable[[], T],
    *,
    provider: str,
    t0: float,
) -> T:
    from butler.gateway.media_telemetry import record_media_event

    try:
        text = run()
        record_media_event(
            "stt",
            provider=provider,
            ok=True,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        return text
    except Exception as exc:
        record_media_event(
            "stt",
            provider=provider,
            ok=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc)[:80],
        )
        logger.debug("speech_stt transcribe failed: %s", exc)
        raise
