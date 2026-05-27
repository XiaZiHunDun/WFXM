"""Unified logging configuration for CLI and Gateway entry points.

Reads ``BUTLER_LOG_LEVEL`` (default ``INFO``) and applies a consistent
format across all Butler entry points.
"""

from __future__ import annotations

import logging
import os

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_CONFIGURED = False


def configure_logging(*, level: str | None = None) -> None:
    """Configure root logger once for Butler.

    Args:
        level: Explicit level override. Falls back to ``BUTLER_LOG_LEVEL``
               env var, then ``INFO``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    resolved = (level or os.getenv("BUTLER_LOG_LEVEL", "") or "INFO").upper()
    numeric = getattr(logging, resolved, logging.INFO)
    logging.basicConfig(level=numeric, format=_LOG_FORMAT)
    logging.getLogger("butler").setLevel(numeric)

    noisy_loggers = ("httpx", "httpcore", "openai", "anthropic", "urllib3")
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(max(numeric, logging.WARNING))
