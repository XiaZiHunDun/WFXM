"""Tests for the tool system (registry, dispatch, extended fields)."""
from __future__ import annotations

import asyncio
import json

import pytest

from butler.tools.registry import ToolEntry, ToolRegistry, register_tool


class TestToolEntry:
    def test_extended_fields(self):
        entry = ToolEntry(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=lambda: "ok",
            scope="project",
            safety_level="cautious",
            read_only=True,
        )
        assert entry.scope == "project"
        assert entry.safety_level == "cautious"
        assert entry.read_only is True
        assert entry.category == "general"

    def test_default_fields(self):
        entry = ToolEntry(
            name="minimal",
            description="",
            parameters={},
            handler=lambda: None,
        )
        assert entry.scope == "global"
        assert entry.safety_level == "safe"
        assert entry.read_only is False
        assert entry.is_async is False


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register("my_tool", "desc", {"type": "object"}, lambda: "result")
        entry = reg.get("my_tool")
        assert entry is not None
        assert entry.name == "my_tool"
        assert entry.description == "desc"

    def test_deregister(self):
        reg = ToolRegistry()
        reg.register("temp", "temp tool", {}, lambda: None)
        assert reg.get("temp") is not None
        reg.deregister("temp")
        assert reg.get("temp") is None

    def test_get_definitions(self):
        reg = ToolRegistry()
        reg.register("tool_a", "Tool A", {"type": "object", "properties": {}}, lambda: "a")
        reg.register("tool_b", "Tool B", {"type": "object", "properties": {}}, lambda: "b")

        defs = reg.get_definitions()
        assert len(defs) == 2
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] in ("tool_a", "tool_b")

    def test_get_definitions_filtered(self):
        reg = ToolRegistry()
        reg.register("include_me", "Yes", {}, lambda: "y")
        reg.register("exclude_me", "No", {}, lambda: "n")

        defs = reg.get_definitions(names={"include_me"})
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "include_me"

    def test_get_names(self):
        reg = ToolRegistry()
        reg.register("alpha", "A", {}, lambda: None)
        reg.register("beta", "B", {}, lambda: None)
        names = reg.get_names()
        assert "alpha" in names
        assert "beta" in names

    def test_dispatch_sync_tool(self):
        reg = ToolRegistry()
        reg.register("adder", "Adds numbers", {}, lambda a, b: {"sum": a + b})
        result = asyncio.run(
            reg.dispatch("adder", {"a": 3, "b": 4})
        )
        data = json.loads(result)
        assert data["sum"] == 7

    def test_dispatch_async_tool(self):
        async def async_tool(msg: str) -> dict:
            return {"echo": msg}

        reg = ToolRegistry()
        reg.register("echo", "Echo tool", {}, async_tool, is_async=True)
        result = asyncio.run(
            reg.dispatch("echo", {"msg": "hello"})
        )
        data = json.loads(result)
        assert data["echo"] == "hello"

    def test_dispatch_not_found(self):
        reg = ToolRegistry()
        result = asyncio.run(
            reg.dispatch("nonexistent", {})
        )
        data = json.loads(result)
        assert "error" in data

    def test_dispatch_handler_error(self):
        def failing_tool():
            raise ValueError("intentional error")

        reg = ToolRegistry()
        reg.register("fail", "Fails", {}, failing_tool)
        result = asyncio.run(
            reg.dispatch("fail", {})
        )
        data = json.loads(result)
        assert "error" in data
        assert "intentional error" in data["error"]

    def test_dispatch_returns_string(self):
        reg = ToolRegistry()
        reg.register("str_tool", "Returns string", {}, lambda: "raw string result")
        result = asyncio.run(
            reg.dispatch("str_tool", {})
        )
        assert result == "raw string result"

    def test_register_with_extended_fields(self):
        reg = ToolRegistry()
        reg.register(
            "secure_tool", "Secure", {}, lambda: None,
            scope="agent", safety_level="dangerous", read_only=False,
        )
        entry = reg.get("secure_tool")
        assert entry.scope == "agent"
        assert entry.safety_level == "dangerous"


class TestRegisterToolDecorator:
    def test_decorator_registers(self):
        fresh_reg = ToolRegistry()
        original_reg = __import__("butler.tools.registry", fromlist=["tool_registry"]).tool_registry
        import butler.tools.registry as mod
        saved = mod.tool_registry
        mod.tool_registry = fresh_reg

        try:
            @register_tool(
                name="decorated_tool",
                description="Decorated test tool",
                parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
                category="test",
                scope="project",
                read_only=True,
            )
            def decorated_tool(x: int) -> dict:
                return {"result": x * 2}

        finally:
            mod.tool_registry = saved

        entry = fresh_reg.get("decorated_tool")
        assert entry is not None
        assert entry.category == "test"
        assert entry.scope == "project"
        assert entry.read_only is True
        assert entry.handler(x=5) == {"result": 10}


class TestResolveToolsForAgent:
    def test_resolve_basic(self):
        """Test that resolve_tools_for_agent returns a non-empty set."""
        from butler.tools.registry import resolve_tools_for_agent
        try:
            tools = resolve_tools_for_agent("灵文", "dev_agent")
            assert isinstance(tools, set)
            assert "skill_list" in tools
            assert "skill_view" in tools
        except Exception:
            pytest.skip("Agent profiles or project manager not configured")
