"""Tool registry - singleton pattern inspired by Hermes Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Any]


@dataclass
class ToolEntry:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    is_async: bool = False
    category: str = "general"
    scope: str = "global"        # "global" | "project" | "agent"
    safety_level: str = "safe"   # "safe" | "cautious" | "dangerous"
    read_only: bool = False


class ToolRegistry:
    """Singleton tool registry with thread-safe operations."""

    def __init__(self):
        self._entries: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()
        self._generation = 0

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        is_async: bool = False,
        category: str = "general",
        scope: str = "global",
        safety_level: str = "safe",
        read_only: bool = False,
    ) -> None:
        with self._lock:
            self._entries[name] = ToolEntry(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
                is_async=is_async,
                category=category,
                scope=scope,
                safety_level=safety_level,
                read_only=read_only,
            )
            self._generation += 1

    def deregister(self, name: str) -> None:
        with self._lock:
            self._entries.pop(name, None)
            self._generation += 1

    def get(self, name: str) -> ToolEntry | None:
        with self._lock:
            return self._entries.get(name)

    def get_definitions(self, names: set[str] | None = None) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions."""
        with self._lock:
            entries = list(self._entries.values())

        definitions = []
        for entry in entries:
            if names and entry.name not in names:
                continue
            definitions.append({
                "type": "function",
                "function": {
                    "name": entry.name,
                    "description": entry.description,
                    "parameters": entry.parameters,
                },
            })
        return definitions

    def get_names(self) -> list[str]:
        with self._lock:
            return list(self._entries.keys())

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        entry = self.get(name)
        if entry is None:
            return json.dumps({"error": f"Tool '{name}' not found"})

        try:
            if entry.is_async:
                result = await entry.handler(**arguments)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: entry.handler(**arguments))

            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Tool '{name}' error: {e}\n{traceback.format_exc()}")
            return json.dumps({"error": str(e)})


tool_registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    is_async: bool = False,
    category: str = "general",
    scope: str = "global",
    safety_level: str = "safe",
    read_only: bool = False,
):
    """Decorator for tool registration."""
    def decorator(fn: ToolHandler) -> ToolHandler:
        tool_registry.register(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            is_async=is_async,
            category=category,
            scope=scope,
            safety_level=safety_level,
            read_only=read_only,
        )
        return fn
    return decorator


def resolve_tools_for_agent(project_name: str, role: str) -> set[str]:
    """Dynamically resolve available tools for an agent based on project config and role."""
    from butler.executors.agent_profiles import get_profile
    from butler.core.project_manager import project_manager

    profile = get_profile(role)
    if not profile:
        return set()

    base_tools = set(profile.tools)

    proj = project_manager.get_project(project_name)
    if proj and hasattr(proj, 'tools_config') and proj.tools_config:
        role_config = proj.tools_config.get(role, {})
        if isinstance(role_config, dict):
            if "include" in role_config:
                base_tools |= set(role_config["include"])
            if "exclude" in role_config:
                base_tools -= set(role_config["exclude"])

    base_tools |= {"skill_list", "skill_view"}

    return base_tools
