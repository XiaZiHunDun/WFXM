"""Unified Tool Failure type for functional error handling.

Provides ToolFailure and ToolResult types that integrate with the
Result monad for standardized tool execution error handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from butler.core.effects.result_monad import Err, Ok, Result

T = TypeVar("T")


@dataclass
class ToolFailure:
    """Structured tool failure information for Result-based error handling.

    Integrates with the Result monad to provide consistent error
    reporting across all tool executions.

    Attributes:
        tool_name: Name of the tool that failed.
        message: Human-readable error description.
        kind: Error classification (retry/replan/stop).
        code: Machine-readable error code for programmatic handling.
        exc: Optional original exception.
        context: Additional context for debugging.
    """

    tool_name: str
    message: str
    kind: str = "replan"
    code: str = "TOOL_ERROR_REPLAN"
    exc: BaseException | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_result(self) -> Result[Any, "ToolFailure"]:
        """Convert failure to an Err result."""
        return Err(self)

    @property
    def is_retryable(self) -> bool:
        return self.kind == "retry"

    @property
    def is_fatal(self) -> bool:
        return self.kind == "stop"

    @property
    def needs_replan(self) -> bool:
        return self.kind == "replan"

    def __str__(self) -> str:
        return f"[{self.code}] {self.tool_name}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "error": self.message,
            "error_kind": self.kind,
            "code": self.code,
            "retryable": self.is_retryable,
            "fatal": self.is_fatal,
            "context": self.context,
        }


@dataclass
class ToolSuccess(Generic[T]):
    """Successful tool execution result.

    Integrates with the Result monad for consistent success handling.

    Attributes:
        tool_name: Name of the tool that succeeded.
        result: The tool's return value.
        output: Formatted output string for display.
        metadata: Additional metadata about the execution.
    """

    tool_name: str
    result: T
    output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_result(self) -> Result[T, ToolFailure]:
        """Convert success to an Ok result."""
        return Ok(self.result)

    def __str__(self) -> str:
        return f"[OK] {self.tool_name}: {self.output[:100]}"


def tool_success(tool_name: str, result: T, output: str = "", **metadata: Any) -> ToolSuccess[T]:
    """Create a ToolSuccess for functional tool execution."""
    return ToolSuccess(
        tool_name=tool_name,
        result=result,
        output=output,
        metadata=metadata,
    )


def tool_failure(
    tool_name: str,
    message: str,
    *,
    kind: str = "replan",
    code: str = "",
    exc: BaseException | None = None,
    **context: Any,
) -> ToolFailure:
    """Create a ToolFailure for functional tool execution.

    Args:
        tool_name: Name of the tool that failed.
        message: Human-readable error description.
        kind: Error classification ('retry', 'replan', 'stop').
        code: Machine-readable error code. Auto-derived if empty.
        exc: Original exception if available.
        **context: Additional context for debugging.
    """
    if not code:
        code_map = {
            "retry": "TOOL_ERROR_RETRY",
            "replan": "TOOL_ERROR_REPLAN",
            "stop": "TOOL_ERROR_STOP",
        }
        code = code_map.get(kind, "TOOL_ERROR_REPLAN")

    return ToolFailure(
        tool_name=tool_name,
        message=message,
        kind=kind,
        code=code,
        exc=exc,
        context=context,
    )


def tool_result_from_fn(
    tool_name: str,
    f: Callable[[], T],
    *,
    catch: type[Exception] | tuple[type[Exception], ...] = Exception,
    error_kind: str = "retry",
) -> Result[T, ToolFailure]:
    """Execute a tool function and return a Result with ToolFailure.

    Wraps tool execution to provide consistent error handling using
    the Result monad with ToolFailure as the error type.

    Args:
        tool_name: Name of the tool being executed.
        f: The tool function to execute.
        catch: Exception types to catch.
        error_kind: Default error kind for caught exceptions.

    Returns:
        Result containing the tool's return value or a ToolFailure.
    """
    try:
        return Ok(f())
    except catch as e:
        kind = error_kind
        if hasattr(e, "error_kind"):
            kind = getattr(e, "error_kind", error_kind)
        return Err(tool_failure(tool_name, str(e), kind=kind, exc=e))


__all__ = [
    "ToolFailure",
    "ToolSuccess",
    "tool_success",
    "tool_failure",
    "tool_result_from_fn",
]
