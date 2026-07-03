"""Built-in tool implementation best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def run_tool_json_safe(fn: Callable[[], str]) -> str:
    try:
        return fn()
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def run_tool_json_with_failure_hook(
    fn: Callable[[], str],
    *,
    on_failure: Callable[[BaseException], None] | None = None,
) -> str:
    try:
        return fn()
    except Exception as exc:
        if on_failure is not None:
            on_failure(exc)
        return json.dumps({"error": str(exc)})


def push_workflow_failure_safe(
    workflow_name: str,
    exc: BaseException,
    *,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.execution_context import try_push_current_turn_workflow_failure

        try_push_current_turn_workflow_failure(
            workflow_name,
            exc,
            session_key=session_key,
        )

    safe_best_effort(_run, label="builtin_impl.workflow_failure_push", default=None)
