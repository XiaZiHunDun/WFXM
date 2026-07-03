"""Tool boundary checker fail-closed helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def run_tool_boundary_checker_safe(
    tool: str,
    checker: Callable[[dict[str, Any]], Any],
    payload: dict[str, Any],
    *,
    violation_factory: Callable[[str, str, str], Any],
) -> Any:
    try:
        return checker(payload)
    except Exception as exc:
        logger.error("tool boundary check %s failed (fail-closed): %s", tool, exc, exc_info=exc)
        return violation_factory(
            tool,
            "BOUNDARY_CHECK_ERROR",
            f"参数边界校验异常 (fail-closed): {type(exc).__name__}",
        )
