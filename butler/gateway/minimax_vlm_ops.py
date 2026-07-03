"""MiniMax VLM best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def describe_minimax_primary_safe(
    run: Callable[[], str],
    *,
    path: str,
) -> tuple[str | None, Exception | None]:
    try:
        return run(), None
    except Exception as exc:
        logger.warning("MiniMax vision failed for %s: %s", path, exc)
        return None, exc


def describe_with_fallbacks_safe(
    run: Callable[[], tuple[str, str]],
) -> tuple[str | None, str | None, Exception | None]:
    try:
        text, provider = run()
        return text, provider, None
    except Exception as exc:
        return None, None, exc
