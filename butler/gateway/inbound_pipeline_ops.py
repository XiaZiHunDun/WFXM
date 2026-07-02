"""Best-effort helpers for declarative inbound pipeline runner (P0-A)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def run_inbound_step(
    step_name: str,
    run_fn: Callable[[], Any],
) -> Any | None:
    try:
        return run_fn()
    except Exception as exc:
        logger.warning("Inbound step %s raised: %s", step_name, exc)
        return None


__all__ = ["run_inbound_step"]
