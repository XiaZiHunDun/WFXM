"""Prefetch warm best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def run_prefetch_warm_safe(
    fn: Callable[[], str],
    *,
    session_key: str,
    query: str,
    cache_fn: Callable[[str, str, str], None],
) -> None:
    try:
        ctx = fn()
        if str(ctx or "").strip():
            cache_fn(session_key, query, ctx)
    except Exception as exc:
        logger.debug("queue_prefetch warm failed: %s", exc)
