"""Parallel tool batch best-effort and fail-closed helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def normalize_path_safe(path: str) -> str:
    def _run() -> str:
        return str(Path(path).expanduser().resolve())

    result = safe_best_effort(_run, label="parallel_tools.normalize_path", default=path)
    return result if isinstance(result, str) else path


def batch_parallel_allowed(tool_calls: list[Any]) -> bool | None:
    """Return None when guard check skipped; False/True when evaluated."""

    def _run() -> bool:
        from butler.core.batch_sequence_guard import (
            batch_has_destructive_and_reads,
            batch_stale_guard_enabled,
        )

        if batch_stale_guard_enabled() and batch_has_destructive_and_reads(tool_calls):
            return False
        return True

    result = safe_best_effort(_run, label="parallel_tools.batch_guard", default=None)
    if result is None:
        return None
    return bool(result)


def parse_tool_args_safe(tc: Any) -> dict[str, Any]:
    name = tc.name if hasattr(tc, "name") else tc.get("name", "")

    def _run() -> dict[str, Any]:
        if hasattr(tc, "args_dict"):
            args = tc.args_dict()
            return args if isinstance(args, dict) else {}
        if isinstance(tc, dict):
            raw = (tc.get("function") or {}).get("arguments", "{}")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    result = safe_best_effort(_run, label=f"parallel_tools.args.{name}", default={})
    return result if isinstance(result, dict) else {}


def dispatch_parallel_tool_loud(
    dispatch_fn: Any,
    name: str,
    args: dict[str, Any],
    *,
    tool_id: str,
    finalize: Any,
) -> str:
    try:
        return str(dispatch_fn(name, args, tool_call_id=tool_id))
    except Exception as exc:
        return str(
            finalize(
                name,
                args,
                {
                    "error": f"Tool execution failed: {exc}",
                    "code": "TOOL_DISPATCH_ERROR",
                },
            )
        )
