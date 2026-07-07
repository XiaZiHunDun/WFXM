"""Tests for ToolDispatchPort (Wave 4)."""

from __future__ import annotations

from typing import Any

from butler.contracts.tool_dispatch_ports import ToolDispatchPort
from butler.contracts.tool_dispatch_registry import get_tool_dispatch, set_tool_dispatch


class _StubDispatch:
    def dispatch_one_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        tool_call_id: str = "",
        batch_guard: Any = None,
        prefetched: dict[str, str] | None = None,
        guardrails: Any = None,
        dispatch_tool: Any = None,
    ) -> str:
        return f"stub:{name}"


def test_tool_dispatch_port_registry():
    stub = _StubDispatch()
    set_tool_dispatch(stub)
    try:
        port = get_tool_dispatch()
        assert port is not None
        assert isinstance(port, ToolDispatchPort)
        assert port.dispatch_one_tool("read_file", {}, dispatch_tool=lambda *_a, **_k: "ok") == "stub:read_file"
    finally:
        set_tool_dispatch(None)


def test_live_tool_dispatch_wired():
    import butler.core.tool_dispatch  # noqa: F401 — registers port

    port = get_tool_dispatch()
    assert port is not None
    assert isinstance(port, ToolDispatchPort)
