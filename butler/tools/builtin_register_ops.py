"""Best-effort builtin tool registration helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def register_harness_builtin_tools_safe(register: Callable[..., Any]) -> None:
    def _run() -> None:
        from butler.core.harness_flags import (
            ask_clarification_enabled,
            mcp_deferred_tools_enabled,
        )
        from butler.tools.builtin_register import (
            _tool_ask_clarification,
            _tool_load_mcp_tools,
            _tool_mcp_tool_search,
        )

        if mcp_deferred_tools_enabled():
            register(
                name="mcp_tool_search",
                description=(
                    "Search configured MCP tools by keyword without loading full schemas. "
                    "Use load_mcp_tools to promote names into the active tool set for this session."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 12},
                        "promote": {
                            "type": "boolean",
                            "description": "If true, also promote all matches for this session",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
                handler=_tool_mcp_tool_search,
                toolset="mcp",
            )
            register(
                name="load_mcp_tools",
                description="Promote MCP tool registered names so full schemas are available on the next LLM turn.",
                schema={
                    "type": "object",
                    "properties": {
                        "tool_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "MCP registered tool names (mcp_*)",
                        },
                    },
                    "required": ["tool_names"],
                },
                handler=_tool_load_mcp_tools,
                toolset="mcp",
            )
        if ask_clarification_enabled():
            register(
                name="ask_clarification",
                description=(
                    "Ask the user a clarifying question and end the current agent turn. "
                    "Use when requirements are ambiguous before destructive or expensive work."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional multiple-choice labels",
                        },
                    },
                    "required": ["question"],
                },
                handler=_tool_ask_clarification,
                toolset="butler",
            )

    safe_best_effort(_run, label="builtin_register.harness_tools", default=None)


def register_dev_engine_tools_safe(register: Callable[..., Any]) -> None:
    def _run() -> None:
        from butler.dev_engine.dev_tools import register_dev_engine_tools

        register_dev_engine_tools(register)

    safe_best_effort(_run, label="builtin_register.dev_engine_tools", default=None)
