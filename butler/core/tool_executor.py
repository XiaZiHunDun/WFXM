"""Tool-call execution — sequential and concurrent dispatch with middleware hooks.

This module enhances WFXM's tool execution with:
  - Middleware hooks for tool request/execution
  - Progress callbacks for real-time status updates
  - Enhanced concurrent execution with timeout support
  - Tool search unwrap mechanism
  - File checkpoint preflight for destructive operations
  - Session event emission for event sourcing
"""

from __future__ import annotations

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_MAX_TOOL_WORKERS = 8


def _emit_tool_events(
    function_name: str,
    function_args: dict[str, Any],
    result: str,
    tool_call_id: str,
    session_id: str,
    duration: float,
    is_error: bool,
) -> None:
    """Emit session events for tool execution lifecycle."""
    try:
        from butler.core.tool_event_emitter import (
            emit_tool_called_event,
            emit_tool_completed_event,
            emit_tool_failed_event,
        )

        duration_ms = int(duration * 1000)

        # Emit ToolCalled (if not already emitted by progress callback)
        emit_tool_called_event(
            session_id=session_id,
            tool_name=function_name,
            call_id=tool_call_id,
            args=function_args,
        )

        # Emit completion/failure event
        if is_error:
            error_message = result
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                if isinstance(parsed, dict) and parsed.get("error"):
                    error_message = parsed.get("error", str(result))
            except Exception:
                pass

            emit_tool_failed_event(
                session_id=session_id,
                tool_name=function_name,
                call_id=tool_call_id,
                error_message=error_message[:500],
                duration_ms=duration_ms,
            )
        else:
            emit_tool_completed_event(
                session_id=session_id,
                tool_name=function_name,
                call_id=tool_call_id,
                result=result,
                duration_ms=duration_ms,
            )
    except Exception as exc:
        logger.debug("Failed to emit tool events: %s", exc)


def _parse_tool_arguments(raw_arguments: Any) -> tuple[dict, Optional[str]]:
    """Parse model-emitted arguments without repairing or coercing them."""
    try:
        arguments = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        arguments = None
    if isinstance(arguments, dict):
        return arguments, None
    return {}, json.dumps(
        {
            "error": "Invalid tool arguments",
            "message": "Tool arguments must be a valid JSON object; tool was not executed.",
        },
        ensure_ascii=False,
    )


def _resolve_concurrent_tool_timeout() -> float | None:
    from butler.defaults.env_defaults import CONCURRENT_TOOL_TIMEOUT_S_DEFAULT, CONCURRENT_TOOL_TIMEOUT_S_STR_DEFAULT

    raw = os.getenv("BUTLER_CONCURRENT_TOOL_TIMEOUT_S", CONCURRENT_TOOL_TIMEOUT_S_STR_DEFAULT).strip()
    if not raw:
        return CONCURRENT_TOOL_TIMEOUT_S_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "invalid BUTLER_CONCURRENT_TOOL_TIMEOUT_S=%r; using %.0fs",
            raw,
            CONCURRENT_TOOL_TIMEOUT_S_DEFAULT,
        )
        return CONCURRENT_TOOL_TIMEOUT_S_DEFAULT
    if value <= 0:
        return None
    return value


def _is_interpreter_shutdown_submit_error(exc: RuntimeError) -> bool:
    return "cannot schedule new futures after interpreter shutdown" in str(exc)


def _cancelled_tool_result(reason: str = "user interrupt") -> str:
    return json.dumps(
        {
            "error": f"Tool execution cancelled by {reason}",
            "status": "cancelled",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Middleware hooks
# ---------------------------------------------------------------------------


def apply_tool_request_middleware(
    function_name: str,
    function_args: dict[str, Any],
    *,
    session_id: str = "",
    task_id: str = "",
    tool_call_id: str = "",
    turn_id: str = "",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply middleware hooks to tool request before execution.

    Returns (modified_args, middleware_trace).
    """
    trace: list[dict[str, Any]] = []
    args = dict(function_args)

    try:
        from butler.core.tool_middleware import apply_middleware as _apply_middleware
        result = _apply_middleware(
            "tool_request",
            function_name,
            args,
            session_id=session_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            turn_id=turn_id,
        )
        if result.get("modified_args") is not None:
            args = result["modified_args"]
        if result.get("trace"):
            trace.extend(result["trace"])
    except Exception as exc:
        logger.debug("tool_request middleware error: %s", exc)

    return args, trace


def run_tool_execution_middleware(
    function_name: str,
    function_args: dict[str, Any],
    execute: Callable[[dict[str, Any]], Any],
    *,
    session_id: str = "",
    task_id: str = "",
    tool_call_id: str = "",
    turn_id: str = "",
) -> Any:
    """Run tool execution wrapped with middleware hooks.

    The execute function receives the (possibly modified) args and returns the result.
    """
    try:
        from butler.core.tool_middleware import run_execution_middleware as _run_execution
        return _run_execution(
            function_name,
            function_args,
            execute,
            session_id=session_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            turn_id=turn_id,
        )
    except Exception as exc:
        logger.debug("tool_execution middleware error: %s", exc)
        return execute(function_args)


# ---------------------------------------------------------------------------
# Progress callbacks
# ---------------------------------------------------------------------------


class ToolProgressCallbacks:
    """Optional callbacks for tool execution progress."""

    def __init__(
        self,
        on_start: Callable[[str, dict[str, Any], str], None] | None = None,
        on_complete: Callable[[str, dict[str, Any], str, float, bool], None] | None = None,
        on_progress: Callable[[str, dict[str, Any], str], None] | None = None,
        on_output_risk: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.on_start = on_start
        self.on_complete = on_complete
        self.on_progress = on_progress
        self.on_output_risk = on_output_risk


# ---------------------------------------------------------------------------
# Concurrent execution
# ---------------------------------------------------------------------------


def execute_tool_calls_concurrent(
    tool_calls: list[Any],
    dispatch_fn: Callable[[str, dict[str, Any], str], str],
    *,
    session_id: str = "",
    task_id: str = "",
    turn_id: str = "",
    progress_callbacks: ToolProgressCallbacks | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    max_workers: int = _MAX_TOOL_WORKERS,
) -> list[tuple[Any, str]]:
    """Execute multiple tool calls concurrently using a thread pool.

    Results are collected in the original tool-call order.

    Args:
        tool_calls: List of tool call objects with name, arguments, and id attributes
        dispatch_fn: Function to dispatch a single tool call (name, args, tool_call_id -> result)
        session_id: Current session ID
        task_id: Current task ID
        turn_id: Current turn ID
        progress_callbacks: Optional progress callbacks
        interrupt_check: Function to check if execution should be interrupted
        max_workers: Maximum number of parallel workers

    Returns:
        List of (tool_call, result) tuples in original order
    """
    num_tools = len(tool_calls)
    if num_tools == 0:
        return []

    # Check interrupt before starting
    if interrupt_check and interrupt_check():
        results = []
        for tc in tool_calls:
            name = tc.name if hasattr(tc, "name") else tc.get("name", "")
            tc_id = str(getattr(tc, "id", "") or "")
            result = _cancelled_tool_result("user interrupt")
            if progress_callbacks and progress_callbacks.on_complete:
                progress_callbacks.on_complete(name, {}, result, 0.0, True)
            results.append((tc, result))
        return results

    # Parse args + pre-execution bookkeeping
    parsed_calls = []  # (tool_call, function_name, function_args, middleware_trace)
    for tool_call in tool_calls:
        function_name = tool_call.name if hasattr(tool_call, "name") else tool_call.get("name", "")
        function_args, malformed_result = _parse_tool_arguments(
            tool_call.arguments if hasattr(tool_call, "arguments") else tool_call.get("arguments", "{}")
        )

        if malformed_result is not None:
            parsed_calls.append((tool_call, function_name, function_args, [], malformed_result))
            continue

        # Apply middleware
        function_args, middleware_trace = apply_tool_request_middleware(
            function_name,
            function_args,
            session_id=session_id,
            task_id=task_id,
            tool_call_id=str(getattr(tool_call, "id", "") or ""),
            turn_id=turn_id,
        )
        parsed_calls.append((tool_call, function_name, function_args, middleware_trace, None))

    # Log tool calls
    tool_names = [name for _, name, _, _, _ in parsed_calls]
    logger.info("Concurrent: %d tool calls — %s", num_tools, ", ".join(tool_names))

    # Fire on_start callbacks
    if progress_callbacks and progress_callbacks.on_start:
        for tc, name, args, _, _ in parsed_calls:
            try:
                tc_id = str(getattr(tc, "id", "") or "")
                progress_callbacks.on_start(name, args, tc_id)
            except Exception as cb_err:
                logger.debug("Tool progress on_start callback error: %s", cb_err)

    # Prepare results array
    results: list[tuple[Any, str]] = [None] * num_tools  # type: ignore[assignment]
    for i, (tc, name, args, middleware_trace, malformed_result) in enumerate(parsed_calls):
        if malformed_result is not None:
            results[i] = (tc, malformed_result)

    def _run_tool(index: int, tool_call: Any, function_name: str, function_args: dict[str, Any]) -> None:
        """Worker function executed in a thread."""
        tool_call_id = str(getattr(tool_call, "id", "") or "")
        start_time = time.time()

        try:
            # Check interrupt at start of worker
            if interrupt_check and interrupt_check():
                result = _cancelled_tool_result("user interrupt")
                results[index] = (tool_call, result)
                if progress_callbacks and progress_callbacks.on_complete:
                    progress_callbacks.on_complete(function_name, function_args, result, 0.0, True)
                return

            # Run with middleware
            def _execute(args: dict[str, Any]) -> str:
                return dispatch_fn(function_name, args, tool_call_id)

            result = run_tool_execution_middleware(
                function_name,
                function_args,
                _execute,
                session_id=session_id,
                task_id=task_id,
                tool_call_id=tool_call_id,
                turn_id=turn_id,
            )

            duration = time.time() - start_time

            # Detect error
            is_error = False
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                if isinstance(parsed, dict) and parsed.get("error"):
                    is_error = True
            except Exception:
                pass

            logger.info(
                "tool %s %s (%.2fs, %d chars)",
                function_name,
                "failed" if is_error else "completed",
                duration,
                len(str(result)),
            )

            results[index] = (tool_call, result)

            # Emit session events for event sourcing
            if session_id:
                _emit_tool_events(
                    function_name=function_name,
                    function_args=function_args,
                    result=result,
                    tool_call_id=tool_call_id,
                    session_id=session_id,
                    duration=duration,
                    is_error=is_error,
                )

            # Fire completion callback
            if progress_callbacks and progress_callbacks.on_complete:
                try:
                    progress_callbacks.on_complete(function_name, function_args, result, duration, is_error)
                except Exception as cb_err:
                    logger.debug("Tool progress on_complete callback error: %s", cb_err)

        except Exception as tool_error:
            duration = time.time() - start_time
            result = f"Error executing tool '{function_name}': {tool_error}"
            logger.error("_invoke_tool raised for %s: %s", function_name, tool_error, exc_info=True)
            results[index] = (tool_call, result)

            # Emit failure event
            if session_id:
                _emit_tool_events(
                    function_name=function_name,
                    function_args=function_args,
                    result=result,
                    tool_call_id=tool_call_id,
                    session_id=session_id,
                    duration=duration,
                    is_error=True,
                )

            if progress_callbacks and progress_callbacks.on_complete:
                try:
                    progress_callbacks.on_complete(function_name, function_args, result, duration, True)
                except Exception as cb_err:
                    logger.debug("Tool progress on_complete callback error: %s", cb_err)

    # Execute concurrently
    runnable_calls = [
        (i, tc, name, args)
        for i, (tc, name, args, _, malformed) in enumerate(parsed_calls)
        if malformed is None
    ]

    if runnable_calls:
        actual_workers = min(len(runnable_calls), max_workers)
        timeout_s = _resolve_concurrent_tool_timeout()
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = []
            future_to_index = {}

            for i, tc, name, args in runnable_calls:
                try:
                    f = executor.submit(_run_tool, i, tc, name, args)
                    futures.append(f)
                    future_to_index[f] = i
                except RuntimeError as submit_error:
                    if not _is_interpreter_shutdown_submit_error(submit_error):
                        raise
                    logger.warning("interpreter shutdown while scheduling tools; skipping remaining")
                    break

            # Wait with interrupt and timeout checks
            while futures:
                wait_timeout = 5.0
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        logger.warning("concurrent tool batch timed out after %.1fs", timeout_s)
                        break
                    wait_timeout = min(wait_timeout, remaining)

                done, not_done = concurrent.futures.wait(futures, timeout=wait_timeout)

                if not not_done:
                    break

                # Check for interrupt
                if interrupt_check and interrupt_check():
                    logger.info("Interrupt: cancelling %d pending tools", len(not_done))
                    for f in not_done:
                        f.cancel()
                    break

                futures = list(not_done)

    # Handle any remaining None results (cancelled/timed out)
    for i, (tc, result) in enumerate(results):
        if result is None:
            tc = parsed_calls[i][0]
            name = parsed_calls[i][1]
            args = parsed_calls[i][2]
            if interrupt_check and interrupt_check():
                result = _cancelled_tool_result("user interrupt")
            else:
                result = f"Error executing tool '{name}': thread did not return a result"
            results[i] = (tc, result)

            if progress_callbacks and progress_callbacks.on_complete:
                try:
                    progress_callbacks.on_complete(name, args, result, 0.0, True)
                except Exception as cb_err:
                    logger.debug("Tool progress on_complete callback error: %s", cb_err)

    return results


# ---------------------------------------------------------------------------
# Sequential execution
# ---------------------------------------------------------------------------


def execute_tool_calls_sequential(
    tool_calls: list[Any],
    dispatch_fn: Callable[[str, dict[str, Any], str], str],
    *,
    session_id: str = "",
    task_id: str = "",
    turn_id: str = "",
    progress_callbacks: ToolProgressCallbacks | None = None,
    interrupt_check: Callable[[], bool] | None = None,
) -> list[tuple[Any, str]]:
    """Execute tool calls sequentially.

    Args:
        tool_calls: List of tool call objects
        dispatch_fn: Function to dispatch a single tool call
        session_id: Current session ID
        task_id: Current task ID
        turn_id: Current turn ID
        progress_callbacks: Optional progress callbacks
        interrupt_check: Function to check if execution should be interrupted

    Returns:
        List of (tool_call, result) tuples in original order
    """
    results = []

    for tc in tool_calls:
        # Check interrupt
        if interrupt_check and interrupt_check():
            name = tc.name if hasattr(tc, "name") else tc.get("name", "")
            result = _cancelled_tool_result("user interrupt")
            if progress_callbacks and progress_callbacks.on_complete:
                progress_callbacks.on_complete(name, {}, result, 0.0, True)
            results.append((tc, result))
            break

        function_name = tc.name if hasattr(tc, "name") else tc.get("name", "")
        function_args, malformed_result = _parse_tool_arguments(
            tc.arguments if hasattr(tc, "arguments") else tc.get("arguments", "{}")
        )
        tool_call_id = str(getattr(tc, "id", "") or "")

        if malformed_result is not None:
            if progress_callbacks and progress_callbacks.on_complete:
                progress_callbacks.on_complete(function_name, function_args, malformed_result, 0.0, True)
            results.append((tc, malformed_result))
            continue

        # Apply middleware
        function_args, _ = apply_tool_request_middleware(
            function_name,
            function_args,
            session_id=session_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            turn_id=turn_id,
        )

        # Fire on_start
        if progress_callbacks and progress_callbacks.on_start:
            try:
                progress_callbacks.on_start(function_name, function_args, tool_call_id)
            except Exception as cb_err:
                logger.debug("Tool progress on_start callback error: %s", cb_err)

        # Execute
        start_time = time.time()
        try:
            def _execute(args: dict[str, Any]) -> str:
                return dispatch_fn(function_name, args, tool_call_id)

            result = run_tool_execution_middleware(
                function_name,
                function_args,
                _execute,
                session_id=session_id,
                task_id=task_id,
                tool_call_id=tool_call_id,
                turn_id=turn_id,
            )
        except Exception as exc:
            result = f"Error executing tool '{function_name}': {exc}"

        duration = time.time() - start_time

        # Detect error
        is_error = False
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            if isinstance(parsed, dict) and parsed.get("error"):
                is_error = True
        except Exception:
            pass

        # Emit session events for event sourcing
        if session_id:
            _emit_tool_events(
                function_name=function_name,
                function_args=function_args,
                result=result,
                tool_call_id=tool_call_id,
                session_id=session_id,
                duration=duration,
                is_error=is_error,
            )

        # Fire on_complete
        if progress_callbacks and progress_callbacks.on_complete:
            try:
                progress_callbacks.on_complete(function_name, function_args, result, duration, is_error)
            except Exception as cb_err:
                logger.debug("Tool progress on_complete callback error: %s", cb_err)

        results.append((tc, result))

    return results


__all__ = [
    "ToolProgressCallbacks",
    "execute_tool_calls_concurrent",
    "execute_tool_calls_sequential",
    "apply_tool_request_middleware",
    "run_tool_execution_middleware",
    "_emit_tool_events",
]