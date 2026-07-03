"""Vision fallback provider best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def try_vision_fallback_provider_safe(
    name: str,
    run: Callable[[], str],
) -> tuple[str | None, str | None]:
    try:
        return run(), None
    except Exception as exc:
        logger.warning("Vision fallback %s failed: %s", name, exc)
        return None, str(exc)
