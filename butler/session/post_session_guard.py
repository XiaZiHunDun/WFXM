"""Post-session error boundary helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def post_session_error_result(exc: BaseException) -> dict[str, Any]:
    logger.warning("Post-session extraction failed: %s", exc)
    return {"skipped": True, "reason": "error", "error": str(exc)}


def guard_post_session(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    from butler.session.post_session_guard_ops import guard_post_session_safe

    return guard_post_session_safe(fn, error_result_fn=post_session_error_result)


__all__ = ["guard_post_session", "post_session_error_result"]
