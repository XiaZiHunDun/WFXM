"""Harness feature flags (PR-X4 / 主线 L)."""

from __future__ import annotations

from butler.env_parse import env_truthy


def mcp_deferred_tools_enabled() -> bool:
    return env_truthy("BUTLER_MCP_DEFERRED_TOOLS", default=False)


def mcp_deferred_same_turn_enabled() -> bool:
    """When true, experience ``mcp:`` promote merges schemas into the same turn."""
    return env_truthy("BUTLER_MCP_DEFERRED_SAME_TURN", default=False)


def ask_clarification_enabled() -> bool:
    return env_truthy("BUTLER_ASK_CLARIFICATION", default=True)


def static_system_reminder_enabled() -> bool:
    return env_truthy("BUTLER_STATIC_SYSTEM_REMINDER", default=False)


__all__ = [
    "ask_clarification_enabled",
    "mcp_deferred_same_turn_enabled",
    "mcp_deferred_tools_enabled",
    "static_system_reminder_enabled",
]
