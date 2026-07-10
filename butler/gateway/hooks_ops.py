"""Gateway in-process hook invocation helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def run_hook_call_safe(name: str, fn: Callable[..., Any], **kwargs: Any) -> Any | None:
    try:
        return fn(**kwargs)
    except Exception as exc:
        logger.warning("Hook %s failed: %s", name, exc)
        return None


def run_mutating_hook_safe(
    name: str,
    fn: Callable[..., Any],
    input_data: dict[str, Any],
    output_data: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        result = fn(input_data, output_data)
        if isinstance(result, dict):
            return result
        return None
    except TypeError:
        try:
            fn(input_data, output_data)
            return None
        except Exception as exc:
            logger.warning("Hook %s failed: %s", name, exc)
            return None
    except Exception as exc:
        logger.warning("Hook %s failed: %s", name, exc)
        return None
