"""Runtime validation for tool arguments using pydantic models.

Provides:
- Pydantic models for builtin tool parameters
- Validation functions for tool arguments
- Schema-to-model conversion utilities
"""

from __future__ import annotations

from typing import Any, Callable, Type

import pydantic

from butler.tools.file_io import MAX_READ_FILE_LINES
from butler.tools.terminal_impl import MAX_TERMINAL_TIMEOUT_SECONDS


class ToolValidationError(Exception):
    """Raised when tool arguments fail validation."""

    def __init__(self, tool_name: str, errors: list[str]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Validation failed for {tool_name}: {', '.join(errors)}")


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
    "TOOL_ARG_MODELS",
]
