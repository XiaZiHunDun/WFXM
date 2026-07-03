"""Debug-gated best-effort calls for LLM retry paths (PERF-11-9)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from butler.core.llm_retry_safe_ops import safe_call_ops

logger = logging.getLogger(__name__)


def safe_call(fn: Callable[[], Any], msg: str, *, _logger: logging.Logger | None = None) -> Any:
    """Run ``fn`` when DEBUG is enabled; swallow exceptions with debug log."""
    return safe_call_ops(fn, msg, log=_logger or logger)


__all__ = ["safe_call"]
