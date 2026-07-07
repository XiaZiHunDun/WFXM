"""Tests for ToolRegistryReadPort (P2 contracts vertical slice)."""

from __future__ import annotations

from butler.contracts.tool_registry_ports import ToolRegistryReadPort
from butler.contracts.tool_registry_registry import (
    get_tool_registry_read,
    set_tool_registry_read,
)
from butler.tools.registry import register, reset_tool_registry
from butler.tools.tool_audit import _tool_result_code


class _StubRegistryRead:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    def is_tool_registered(self, name: str) -> bool:
        return name in self.names


def test_tool_result_code_uses_registry_port():
    read = _StubRegistryRead({"read_file"})
    set_tool_registry_read(read)
    try:
        assert _tool_result_code("missing_tool", {"error": "boom"}, ok=False) == "TOOL_NOT_FOUND"
        assert _tool_result_code("read_file", {"error": "boom"}, ok=False) == "TOOL_ERROR"
        assert isinstance(read, ToolRegistryReadPort)
    finally:
        set_tool_registry_read(None)
        reset_tool_registry()


def test_live_registry_read_port_wired():
    reset_tool_registry()
    register("demo_tool", "demo", {"type": "object", "properties": {}}, lambda **_: "ok")
    port = get_tool_registry_read()
    assert port is not None
    assert port.is_tool_registered("demo_tool")
    assert not port.is_tool_registered("nope")
    reset_tool_registry()
