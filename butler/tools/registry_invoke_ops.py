"""Registered tool handler invocation with error envelope (P0-A / P2-F)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from tenacity import RetryError

from butler.core.effects import with_retry

logger = logging.getLogger(__name__)

# Tools with side effects that should NOT be retried (idempotency risk)
NO_RETRY_TOOLS = frozenset({
    "write_file",
    "patch",
    "delete_file",
    "terminal",
    "opencode_task",
    "delegate_task",
    "run_workflow",
    "mcp_install",
    "mcp_remove",
})


def call_tool_with_retry(
    name: str,
    fn: Callable[[], Any],
    *,
    max_attempts: int = 2,
    wait_seconds: float = 0.1,
    retry_on: tuple[type[Exception], ...] = (OSError, ConnectionError),
) -> Any:
    """
    Call a tool function with retry logic, respecting NO_RETRY_TOOLS.

    Args:
        name: Tool name (used for NO_RETRY_TOOLS check)
        fn: Callable to invoke
        max_attempts: Maximum number of attempts
        wait_seconds: Wait time between retries
        retry_on: Exception types to retry on

    Returns:
        The result of calling fn()

    Raises:
        Original exception if retries are exhausted
        Any exception from fn() if tool is in NO_RETRY_TOOLS
    """
    if name in NO_RETRY_TOOLS:
        return fn()

    @with_retry(max_attempts=max_attempts, wait_seconds=wait_seconds, retry_on=retry_on)
    def _call_with_retry() -> Any:
        return fn()

    try:
        return _call_with_retry()
    except RetryError as exc:
        original_exc = getattr(exc, 'last_attempt', None)
        if original_exc is not None:
            original_exc = getattr(original_exc, 'exception', None)
        raise original_exc if original_exc is not None else exc


def invoke_registered_tool_handler(
    *,
    name: str,
    args: dict[str, Any],
    call_args: dict[str, Any],
    handler: Any,
    started_at: float,
    finalize_result: Callable[..., str],
    apply_hooks: Callable[..., str],
) -> str:
    from butler.tools.tool_implicit_context import merge_implicit_tool_args

    merged = merge_implicit_tool_args(call_args)

    try:
        result = call_tool_with_retry(name, lambda: handler(**merged))
        if name == "web_search":
            from butler.tools.registry_gates import note_web_search_outcome

            note_web_search_outcome(result)
        return apply_hooks(
            name,
            args,
            finalize_result(name, args, result, started_at=started_at),
        )
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        from butler.tools.registry_gates import tool_error_payload

        payload = tool_error_payload(name, exc)
        err_result = finalize_result(
            name,
            args,
            payload,
            started_at=started_at,
        )
        return apply_hooks(name, args, err_result, failed=True)
