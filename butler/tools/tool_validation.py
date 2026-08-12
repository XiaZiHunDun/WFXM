"""Runtime validation for tool arguments using pydantic models.

Provides:
- Pydantic models for builtin tool parameters
- Validation functions for tool arguments
- Schema-to-model conversion utilities
- Unified ToolFailure type for error handling
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Type

import pydantic

from butler.tools.file_io import MAX_READ_FILE_LINES
from butler.tools.terminal_impl import MAX_TERMINAL_TIMEOUT_SECONDS


class ToolValidationError(Exception):
    """Raised when tool arguments fail validation."""

    def __init__(self, tool_name: str, errors: list[str]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Validation failed for {tool_name}: {', '.join(errors)}")


@dataclass(frozen=True)
class ToolFailure:
    """Unified tool failure type for consistent error handling.

    Based on opencode's ToolFailure pattern. Provides a consistent way to
    represent tool execution failures across the codebase.

    Attributes:
        message: Human-readable error message
        code: Error code for programmatic handling
        tool_name: Name of the tool that failed
        cause: Optional underlying exception
        retryable: Whether the operation can be retried
    """

    message: str
    code: str = "TOOL_FAILURE"
    tool_name: str = ""
    cause: Optional[Exception] = None
    retryable: bool = False

    def __str__(self) -> str:
        parts = [f"[{self.code}]"]
        if self.tool_name:
            parts.append(f"{self.tool_name}:")
        parts.append(self.message)
        return " ".join(parts)

    @classmethod
    def from_validation_error(cls, error: ToolValidationError) -> "ToolFailure":
        """Create a ToolFailure from a validation error."""
        return cls(
            message=str(error),
            code="VALIDATION_ERROR",
            tool_name=error.tool_name,
            retryable=False,
        )

    @classmethod
    def from_exception(cls, exc: Exception, tool_name: str = "") -> "ToolFailure":
        """Create a ToolFailure from an exception."""
        return cls(
            message=str(exc),
            code=type(exc).__name__,
            tool_name=tool_name,
            cause=exc,
            retryable=False,
        )

    @classmethod
    def timeout(cls, tool_name: str) -> "ToolFailure":
        """Create a timeout failure."""
        return cls(
            message="Tool execution timed out",
            code="TIMEOUT",
            tool_name=tool_name,
            retryable=True,
        )

    @classmethod
    def permission_denied(cls, tool_name: str, reason: str = "") -> "ToolFailure":
        """Create a permission denied failure."""
        message = "Permission denied"
        if reason:
            message += f": {reason}"
        return cls(
            message=message,
            code="PERMISSION_DENIED",
            tool_name=tool_name,
            retryable=False,
        )


from butler.core.effects import Result, Ok, Err


def tool_result_ok(value: Any) -> Result[Any, ToolFailure]:
    """Create a successful tool result."""
    return Ok(value)


def tool_result_err(failure: ToolFailure) -> Result[Any, ToolFailure]:
    """Create a failed tool result."""
    return Err(failure)


def dispatch_tool_safe(
    tool_name: str,
    args: dict[str, Any],
    dispatch_fn: Callable[[str, dict[str, Any]], str],
) -> Result[str, ToolFailure]:
    """Wrap a tool dispatch function with ToolFailure error handling.

    Converts the string-based tool dispatch into a Result type,
    extracting structured error information from the result string.

    Args:
        tool_name: Name of the tool to dispatch
        args: Tool arguments
        dispatch_fn: The underlying dispatch function (e.g., registry.dispatch_tool)

    Returns:
        Ok(result_string) on success, Err(ToolFailure) on failure.
    """
    try:
        # Validate args first
        is_valid, result = validate_tool_args(tool_name, args)
        if not is_valid:
            errors = result if isinstance(result, list) else [str(result)]
            return Err(ToolFailure(
                message="; ".join(errors),
                code="VALIDATION_ERROR",
                tool_name=tool_name,
                retryable=False,
            ))

        # Dispatch the tool
        raw_result = dispatch_fn(tool_name, args)

        # Check for error indicators in the result
        result_lower = raw_result[:500].lower() if raw_result else ""
        if '"ok": false' in result_lower or '"error"' in result_lower:
            # Try to extract error code
            code = "TOOL_FAILURE"
            if '"code"' in raw_result[:500]:
                import json as _json
                try:
                    payload = _json.loads(raw_result)
                    code = payload.get("code", code)
                    message = payload.get("error", payload.get("message", raw_result[:200]))
                except Exception:
                    message = raw_result[:200]
            else:
                message = raw_result[:200]

            return Err(ToolFailure(
                message=message,
                code=code,
                tool_name=tool_name,
                retryable=code in ("TIMEOUT", "RETRY", "TRANSIENT"),
            ))

        return Ok(raw_result)
    except TimeoutError:
        return Err(ToolFailure.timeout(tool_name))
    except PermissionError as e:
        return Err(ToolFailure.permission_denied(tool_name, str(e)))
    except Exception as e:
        return Err(ToolFailure.from_exception(e, tool_name))


class ReadFileArgs(pydantic.BaseModel):
    """Arguments for read_file tool."""

    path: str = pydantic.Field(description="Absolute or relative file path")
    offset: int = pydantic.Field(
        default=1,
        description="Line number to start from (1-indexed)",
        ge=1,
    )
    limit: int = pydantic.Field(
        default=500,
        description=f"Max lines to read (1-{MAX_READ_FILE_LINES})",
        ge=1,
        le=MAX_READ_FILE_LINES,
    )

    model_config = pydantic.ConfigDict(extra="forbid")


class WriteFileArgs(pydantic.BaseModel):
    """Arguments for write_file tool."""

    path: str = pydantic.Field(description="File path to write")
    content: str = pydantic.Field(description="Content to write")

    model_config = pydantic.ConfigDict(extra="forbid")


class PatchFileArgs(pydantic.BaseModel):
    """Arguments for patch tool."""

    path: str = pydantic.Field(description="File path")
    old_string: str = pydantic.Field(description="Exact text to find")
    new_string: str = pydantic.Field(description="Replacement text")

    model_config = pydantic.ConfigDict(extra="forbid")


class DeleteFileArgs(pydantic.BaseModel):
    """Arguments for delete_file tool."""

    path: str = pydantic.Field(description="File path to delete")

    model_config = pydantic.ConfigDict(extra="forbid")


class TerminalArgs(pydantic.BaseModel):
    """Arguments for terminal tool."""

    command: str = pydantic.Field(description="Shell command to execute")
    timeout: int = pydantic.Field(
        default=30,
        description=f"Timeout in seconds (1-{MAX_TERMINAL_TIMEOUT_SECONDS})",
        ge=1,
        le=MAX_TERMINAL_TIMEOUT_SECONDS,
    )
    workdir: str | None = pydantic.Field(
        default=None,
        description="Working directory",
    )

    model_config = pydantic.ConfigDict(extra="forbid")


class SearchFilesArgs(pydantic.BaseModel):
    """Arguments for search_files tool."""

    pattern: str = pydantic.Field(description="Search pattern (regex)")
    path: str = pydantic.Field(
        default=".",
        description="Directory or file to search in",
    )
    include: str | None = pydantic.Field(
        default=None,
        description="Glob pattern to filter files",
    )

    model_config = pydantic.ConfigDict(extra="forbid")


class ListDirectoryArgs(pydantic.BaseModel):
    """Arguments for list_directory tool."""

    path: str = pydantic.Field(
        default=".",
        description="Directory path",
    )

    model_config = pydantic.ConfigDict(extra="forbid")


class DelegateTaskArgs(pydantic.BaseModel):
    """Arguments for delegate_task tool."""

    role: str = pydantic.Field(
        description="Agent role: 'dev', 'content', or 'review'",
        pattern="^(dev|content|review)$",
    )
    category: str | None = pydantic.Field(
        default=None,
        description="Optional preset: quick, deep, ultrabrain, ui-build",
    )
    task: str = pydantic.Field(description="Task description")
    context: str | None = pydantic.Field(
        default=None,
        description="Additional context for the agent",
    )

    model_config = pydantic.ConfigDict(extra="forbid")


class RunWorkflowArgs(pydantic.BaseModel):
    """Arguments for run_workflow tool."""

    name: str = pydantic.Field(
        description="Workflow name (e.g. novel-factory)",
    )
    hint: str = pydantic.Field(
        default="",
        description="Optional user goal appended to each step",
    )

    model_config = pydantic.ConfigDict(extra="forbid")


# Mapping of tool names to their pydantic models
TOOL_ARG_MODELS: dict[str, Type[pydantic.BaseModel]] = {
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "patch": PatchFileArgs,
    "delete_file": DeleteFileArgs,
    "terminal": TerminalArgs,
    "search_files": SearchFilesArgs,
    "list_directory": ListDirectoryArgs,
    "delegate_task": DelegateTaskArgs,
    "run_workflow": RunWorkflowArgs,
}


def validate_tool_args(tool_name: str, args: dict[str, Any]) -> tuple[bool, dict[str, Any] | list[str]]:
    """Validate tool arguments against pydantic model.

    Returns:
        Tuple of (is_valid, result). If valid, result is the validated args dict.
        If invalid, result is a list of error messages.
    """
    model_class = TOOL_ARG_MODELS.get(tool_name)
    if model_class is None:
        # No model defined, skip validation
        return True, args

    try:
        model = model_class(**args)
        return True, model.model_dump()
    except pydantic.ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(l) for l in error.get("loc", []))
            msg = error.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return False, errors


def validate_tool_args_strict(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Validate tool arguments strictly, raising exception on failure."""
    is_valid, result = validate_tool_args(tool_name, args)
    if not is_valid:
        raise ToolValidationError(tool_name, result)
    return result


def register_tool_arg_model(tool_name: str, model_class: Type[pydantic.BaseModel]) -> None:
    """Register a pydantic model for tool argument validation."""
    TOOL_ARG_MODELS[tool_name] = model_class


def get_tool_arg_model(tool_name: str) -> Type[pydantic.BaseModel] | None:
    """Get the pydantic model for a tool."""
    return TOOL_ARG_MODELS.get(tool_name)


def model_to_json_schema(model_class: Type[pydantic.BaseModel]) -> dict[str, Any]:
    """Convert a pydantic model to JSON schema."""
    return model_class.model_json_schema()


__all__ = [
    "ToolValidationError",
    "ToolFailure",
    "ReadFileArgs",
    "WriteFileArgs",
    "PatchFileArgs",
    "DeleteFileArgs",
    "TerminalArgs",
    "SearchFilesArgs",
    "ListDirectoryArgs",
    "DelegateTaskArgs",
    "RunWorkflowArgs",
    "validate_tool_args",
    "validate_tool_args_strict",
    "register_tool_arg_model",
    "get_tool_arg_model",
    "model_to_json_schema",
    "tool_result_ok",
    "tool_result_err",
    "dispatch_tool_safe",
    "TOOL_ARG_MODELS",
]
