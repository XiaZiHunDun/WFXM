"""Pydantic models for tool arguments and responses.

Type-safe tool dispatch with runtime validation.
Inspired by Effect-TS/ZIO Schema layer.
"""

from __future__ import annotations

from typing import Any, Optional

import pydantic


# ── Base Tool Models ──


class ToolCall(pydantic.BaseModel):
    """Represents a tool call request."""

    name: str
    args: dict[str, Any] = pydantic.Field(default_factory=dict)

    model_config = pydantic.ConfigDict(frozen=True)


class ToolResult(pydantic.BaseModel):
    """Represents a tool execution result."""

    success: bool
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    tool_name: str = ""

    model_config = pydantic.ConfigDict(frozen=True)


class ToolError(pydantic.BaseModel):
    """Represents a tool execution error."""

    code: str
    message: str
    tool_name: str = ""
    details: dict[str, Any] = pydantic.Field(default_factory=dict)

    model_config = pydantic.ConfigDict(frozen=True)


# ── File Tool Models ──


class ReadFileArgs(pydantic.BaseModel):
    """Arguments for read_file tool."""

    path: str = pydantic.Field(..., description="File path to read")
    encoding: str = pydantic.Field("utf-8", description="File encoding")


class WriteFileArgs(pydantic.BaseModel):
    """Arguments for write_file tool."""

    path: str = pydantic.Field(..., description="File path to write")
    content: str = pydantic.Field(..., description="Content to write")
    append: bool = pydantic.Field(False, description="Append to file")


class PatchArgs(pydantic.BaseModel):
    """Arguments for patch tool."""

    path: str = pydantic.Field(..., description="File path to patch")
    old_string: str = pydantic.Field(..., description="Old string to replace")
    new_string: str = pydantic.Field("", description="New string (empty to delete)")


class DeleteFileArgs(pydantic.BaseModel):
    """Arguments for delete_file tool."""

    path: str = pydantic.Field(..., description="File path to delete")


# ── Terminal Tool Models ──


class TerminalArgs(pydantic.BaseModel):
    """Arguments for terminal tool."""

    command: str = pydantic.Field(..., description="Command to execute")
    cwd: Optional[str] = pydantic.Field(None, description="Working directory")


# ── Search Tool Models ──


class SearchArgs(pydantic.BaseModel):
    """Arguments for search tools."""

    query: str = pydantic.Field(..., description="Search query")
    limit: int = pydantic.Field(10, description="Maximum results")


class SearchResultItem(pydantic.BaseModel):
    """Single search result item."""

    path: str
    content: str
    score: float = 0.0


class SearchResult(pydantic.BaseModel):
    """Search tool result."""

    results: list[SearchResultItem] = pydantic.Field(default_factory=list)
    total: int = 0


# ── Symbol Search Models ──


class DevSearchSymbolsArgs(pydantic.BaseModel):
    """Arguments for dev_search_symbols tool."""

    name: str = pydantic.Field(..., description="Symbol name to search")


# ── Tool Schema Registry ──

TOOL_ARG_MODELS: dict[str, type[pydantic.BaseModel]] = {
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "patch": PatchArgs,
    "delete_file": DeleteFileArgs,
    "terminal": TerminalArgs,
    "dev_search_symbols": DevSearchSymbolsArgs,
}


def validate_tool_args(name: str, args: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Validate tool arguments using pydantic model.

    Returns (is_valid, result) where result is either validated args or error info.
    """
    model_class = TOOL_ARG_MODELS.get(name)
    if model_class is None:
        return True, args

    try:
        validated = model_class(**args)
        return True, validated.model_dump()
    except pydantic.ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(l) for l in error.get("loc", []))
            msg = error.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return False, {
            "error": f"Invalid arguments for {name}: {', '.join(errors)}",
            "code": "TOOL_ARGS_VALIDATION_FAILED",
            "tool": name,
            "validation_errors": errors,
        }


__all__ = [
    "ToolCall",
    "ToolResult",
    "ToolError",
    "ReadFileArgs",
    "WriteFileArgs",
    "PatchArgs",
    "DeleteFileArgs",
    "TerminalArgs",
    "SearchArgs",
    "SearchResultItem",
    "SearchResult",
    "DevSearchSymbolsArgs",
    "TOOL_ARG_MODELS",
    "validate_tool_args",
]
