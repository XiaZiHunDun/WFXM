"""Debug-gated best-effort calls for LLM retry paths (PERF-11-9)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def safe_call(fn: Callable[[], Any], msg: str, *, _logger: logging.Logger | None = None) -> Any:
    """Run ``fn`` when DEBUG is enabled; swallow exceptions with debug log."""
    log = _logger or logger
    if not log.isEnabledFor(logging.DEBUG):
        return None
    try:
        return fn()
    except Exception as exc:
        log.debug("%s: %s", msg, exc)
        return None


__all__ = ["safe_call"]
