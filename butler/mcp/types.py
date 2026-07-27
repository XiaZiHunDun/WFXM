"""MCP configuration types with pydantic models for runtime validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import pydantic
from pydantic import ConfigDict, Field, ValidationError


# ── Legacy Dataclasses (backward compatible) ──


@dataclass(frozen=True)
class McpToolPolicy:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    transport: Literal["stdio", "http"]
    timeout_seconds: float = 60.0
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    sse: bool = False
    hosts_allow: tuple[str, ...] = ()
    tools: McpToolPolicy = field(default_factory=McpToolPolicy)
    classify: dict[str, str] = field(default_factory=dict)


@dataclass
class McpToolRef:
    server_id: str
    original_name: str
    registered_name: str
    classification: str  # readonly | mutating | network
    input_schema: dict[str, Any]
    description: str = ""


@dataclass
class McpServerStatus:
    server_id: str
    transport: str
    connected: bool = False
    tool_count: int = 0
    last_error: str = ""
    degraded: bool = False


# ── Pydantic Models (new runtime validation) ──


class McpRequest(pydantic.BaseModel):  # type: ignore[misc]
    """MCP request message."""

    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: dict[str, Any] = pydantic.Field(default_factory=dict)


class McpResponse(pydantic.BaseModel):  # type: ignore[misc]
    """MCP response message."""

    jsonrpc: str = "2.0"
    id: str | int | None = None


class McpSuccessResponse(McpResponse):
    """Successful MCP response."""

    result: dict[str, Any]


class McpError(pydantic.BaseModel):  # type: ignore[misc]
    """MCP error object."""

    code: int
    message: str
    data: Optional[Any] = None


class McpErrorResponse(McpResponse):
    """Error MCP response."""

    error: McpError


class McpToolCall(pydantic.BaseModel):  # type: ignore[misc]
    """MCP tool call request."""

    name: str
    arguments: dict[str, Any] = pydantic.Field(default_factory=dict)


class McpToolResult(pydantic.BaseModel):  # type: ignore[misc]
    """MCP tool execution result."""

    success: bool
    content: Any = None
    error: str = ""
    server_id: str = ""
    tool_name: str = ""
    duration_ms: float = 0.0

    model_config = pydantic.ConfigDict(frozen=True)


class McpCapability(pydantic.BaseModel):  # type: ignore[misc]
    """MCP server capability."""

    name: str
    version: str = "1.0"


class McpToolDescription(pydantic.BaseModel):  # type: ignore[misc]
    """MCP tool description."""

    name: str
    description: str = ""
    inputSchema: dict[str, Any] = pydantic.Field(default_factory=dict)


# ── Validation Functions ──


def validate_mcp_request(data: dict[str, Any]) -> tuple[bool, McpRequest | dict[str, Any]]:
    """Validate MCP request data."""
    try:
        return True, McpRequest(**data)
    except pydantic.ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(l) for l in error.get("loc", []))
            msg = error.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return False, {
            "error": f"Invalid MCP request: {', '.join(errors)}",
            "code": "MCP_REQUEST_VALIDATION_FAILED",
            "validation_errors": errors,
        }


def validate_mcp_response(data: dict[str, Any]) -> tuple[bool, McpResponse | dict[str, Any]]:
    """Validate MCP response data."""
    try:
        if "error" in data:
            return True, McpErrorResponse(**data)
        elif "result" in data:
            return True, McpSuccessResponse(**data)
        return True, McpResponse(**data)
    except pydantic.ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(l) for l in error.get("loc", []))
            msg = error.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return False, {
            "error": f"Invalid MCP response: {', '.join(errors)}",
            "code": "MCP_RESPONSE_VALIDATION_FAILED",
            "validation_errors": errors,
        }


__all__ = [
    "McpToolPolicy",
    "McpServerConfig",
    "McpToolRef",
    "McpServerStatus",
    "McpRequest",
    "McpResponse",
    "McpSuccessResponse",
    "McpErrorResponse",
    "McpError",
    "McpToolCall",
    "McpToolResult",
    "McpCapability",
    "McpToolDescription",
    "validate_mcp_request",
    "validate_mcp_response",
]
