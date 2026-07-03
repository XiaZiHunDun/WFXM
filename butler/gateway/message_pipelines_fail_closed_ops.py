"""Fail-closed inbound guard helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def run_fail_closed_guard(
    fn: Callable[[], Optional[str]],
    *,
    label: str,
    blocked_message: str,
) -> Optional[str]:
    try:
        return fn()
    except ImportError as exc:
        logger.info("%s module not available: %s", label, exc)
        return None
    except Exception as exc:
        logger.error("%s raised — fail-closed: %s", label, exc)
        return blocked_message


def run_injection_guard_fail_closed(
    fn: Callable[[], tuple[str, None]],
    *,
    label: str,
    text: str,
    blocked_message: str,
) -> tuple[str, Optional[str]]:
    try:
        return fn()
    except ImportError as exc:
        logger.info("%s module not available: %s", label, exc)
        return text, None
    except Exception as exc:
        logger.error("%s raised — fail-closed: %s", label, exc)
        return text, blocked_message
