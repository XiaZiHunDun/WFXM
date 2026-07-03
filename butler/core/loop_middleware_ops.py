"""Loop middleware hook best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def run_middleware_hook_safe(
    hook: Callable[..., Any],
    messages: list[dict],
    *,
    label: str,
    tool_stats: Any = None,
) -> list[dict]:
    def _run() -> list[dict]:
        if tool_stats is not None:
            result = hook(messages, tool_stats=tool_stats)
        else:
            result = hook(messages)
        if not isinstance(result, list):
            raise ValueError("middleware hook must return list[dict]")
        return result

    outcome = safe_best_effort(_run, label=label, default=messages)
    return list(outcome) if isinstance(outcome, list) else list(messages)
