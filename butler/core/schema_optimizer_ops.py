"""Schema optimizer import best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def load_schema_sanitizer_safe() -> tuple[Callable[..., Any], Callable[..., Any]] | None:
    def _run() -> tuple[Callable[..., Any], Callable[..., Any]]:
        from butler.transport.schema_sanitizer import sanitize_tool_schemas, strip_pattern_and_format

        return sanitize_tool_schemas, strip_pattern_and_format

    result = safe_best_effort(_run, label="schema_optimizer.import", default=None)
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return None
