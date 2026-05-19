"""Interruptible LLM calls with stale-timeout (Hermes run_agent L7166+)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class StaleApiCallError(TimeoutError):
    """Raised when an API call exceeds stale threshold without completing."""


def run_interruptible(
    fn: Callable[[], T],
    *,
    check_interrupt: Callable[[], bool] | None = None,
    stale_timeout: float = 90.0,
    poll_interval: float = 0.3,
) -> T:
    """Run fn in a worker thread; poll for interrupt or stale timeout."""
    result: dict[str, Any] = {"value": None, "error": None}

    def _worker() -> None:
        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = exc

    start = time.monotonic()
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while thread.is_alive():
        thread.join(timeout=poll_interval)
        if check_interrupt and check_interrupt():
            logger.info("API call interrupted by user")
            raise InterruptedError("interrupted")
        elapsed = time.monotonic() - start
        if elapsed > stale_timeout:
            logger.warning("API call stale after %.0fs (limit %.0fs)", elapsed, stale_timeout)
            raise StaleApiCallError(
                f"No response from provider after {int(elapsed)}s"
            )

    if result["error"] is not None:
        raise result["error"]
    return result["value"]
