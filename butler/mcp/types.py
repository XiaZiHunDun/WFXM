"""MCP configuration types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
