"""Per-tool automatic retry for transient failures (LangChain ToolRetryMiddleware subset)."""

from __future__ import annotations

import os
import time
from typing import Callable

from butler.env_parse import env_truthy

_NO_RETRY_TOOLS = frozenset({
    "write_file",
    "patch",
    "edit_file",
    "terminal",
    "run_shell",
    "git_commit",
    "git_add",
    "delegate_task",
    "run_workflow",
    "session_todos_write",
})


def tool_retry_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RETRY", default=True)


def tool_retry_max_attempts() -> int:
    try:
        return max(1, min(5, int(os.getenv("BUTLER_TOOL_RETRY_MAX", "2"))))
    except ValueError:
        return 2


def tool_retry_backoff_seconds(attempt: int) -> float:
    base = 0.4
    try:
        base = float(os.getenv("BUTLER_TOOL_RETRY_BACKOFF_SECONDS", "0.4"))
    except ValueError:
        pass
    return base * (attempt + 1)


def _is_transient_error(result: str) -> bool:
    text = (result or "").strip().lower()
    if not text:
        return False
    if text.startswith('{"error"') or text.startswith("error:"):
        markers = (
            "timeout",
            "timed out",
            "connection",
            "network",
            "temporarily",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
            "econnreset",
            "broken pipe",
        )
        return any(m in text for m in markers)
    return False


def should_retry_tool(name: str, result: str, attempt: int) -> bool:
    if not tool_retry_enabled():
        return False
    if name in _NO_RETRY_TOOLS:
        return False
    if attempt >= tool_retry_max_attempts() - 1:
        return False
    return _is_transient_error(result)


def run_tool_with_retry(
    name: str,
    args: dict,
    dispatch: Callable[[str, dict], str],
) -> str:
    """Invoke tool dispatch with bounded retries on transient errors."""
    last = dispatch(name, args)
    attempt = 0
    while should_retry_tool(name, last, attempt):
        time.sleep(tool_retry_backoff_seconds(attempt))
        attempt += 1
        last = dispatch(name, args)
    return last
