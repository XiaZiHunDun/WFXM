"""Debug-gated best-effort calls for LLM retry paths (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any


def safe_call_ops(
    fn: Callable[[], Any],
    msg: str,
    *,
    log: logging.Logger,
) -> Any:
    if not log.isEnabledFor(logging.DEBUG):
        return None
    try:
        return fn()
    except Exception as exc:
        log.debug("%s: %s", msg, exc)
        return None
