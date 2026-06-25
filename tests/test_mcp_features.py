"""MCP client bridge: config, naming, policy, registry integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.mcp.classify import classify_tool, is_mutating_classification
from butler.mcp.config import (
    load_mcp_servers,
    mcp_enabled,
    tool_allowed_by_policy,
    validate_http_url,
    validate_stdio_command,
)
from butler.mcp.naming import build_registered_name, is_mcp_registered_name
from butler.mcp.types import McpServerConfig, McpToolPolicy
from butler.tools.project_tools import filter_tool_definitions


def test_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_MCP_ENABLED", raising=False)
    assert mcp_enabled() is False


def test_load_mcp_config_stdio(tmp_path, monkeypatch):
    cfg_path = tmp_path / "mcp.yaml"
    cfg_path.write_text(
        """
version: 1
servers:
  demo:
    transport: stdio
    command: python3
    args: ["-c", "print(1)"]
    tools:
      allow: ["ping"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(cfg_path))
    servers = load_mcp_servers()
    assert len(servers) == 1
    assert servers[0].server_id == "demo"
    assert servers[0].command == "python3"


def test_build_registered_name():
    name = build_registered_name("my-server", "query_db")
    assert is_mcp_registered_name(name)
    assert name.startswith("mcp_")


def test_classify_mutating_vs_readonly():
    assert classify_tool("delete_row", "remove data") == "mutating"
    assert classify_tool("list_tables", "list schema") == "readonly"
    assert is_mutating_classification("mutating") is True


def test_stdio_command_allowlist(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "python3,python")
    cfg = McpServerConfig(server_id="x", transport="stdio", command="npx", args=())
    assert validate_stdio_command(cfg) is not None
    cfg2 = McpServerConfig(server_id="x", transport="stdio", command="python3", args=())
    assert validate_stdio_command(cfg2) is None


def test_http_private_host_blocked():
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="http://127.0.0.1/mcp",
        hosts_allow=("127.0.0.1",),
    )
    assert validate_http_url(cfg) is not None


def test_http_metadata_ip_blocked_even_with_hosts_allow():
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="http://169.254.169.254/mcp",
        hosts_allow=("169.254.169.254",),
    )
    assert validate_http_url(cfg) is not None


def test_http_hosts_allow_strict_subdomain():
    """Substring bypass must be rejected: `notapi.com` ≠ allowlisted `api.com`."""
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="https://notapi.com/mcp",
        hosts_allow=("api.com",),
    )
    assert validate_http_url(cfg) is not None


def test_http_hosts_allow_suffix_attack():
    """Suffix attack: `api.com.attacker.tld` must NOT pass for allowlisted `api.com`."""
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="https://api.com.attacker.tld/mcp",
        hosts_allow=("api.com",),
    )
    assert validate_http_url(cfg) is not None


def test_http_hosts_allow_subdomain_match():
    """`sub.api.com` SHOULD pass for allowlisted `api.com`."""
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="https://sub.api.com/mcp",
        hosts_allow=("api.com",),
    )
    assert validate_http_url(cfg) is None


def test_http_hosts_allow_exact_match():
    """Exact host match SHOULD pass."""
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="https://api.com/mcp",
        hosts_allow=("api.com",),
    )
    assert validate_http_url(cfg) is None


def test_tool_policy_allow_deny():
    pol = McpToolPolicy(allow=("a",), deny=("b",))
    assert tool_allowed_by_policy(pol, "a") is True
    assert tool_allowed_by_policy(pol, "b") is False


def test_project_tools_mcp_wildcard():
    tools = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        {"type": "function", "function": {"name": "mcp_demo_ping", "parameters": {}}},
    ]
    allowed = {"read_file", "mcp_*"}
    out = filter_tool_definitions(tools, allowed)
    names = {t["function"]["name"] for t in out}
    assert "mcp_demo_ping" in names
    assert "read_file" in names


def test_registry_no_mcp_tools_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
    from butler.tools import registry as reg

    reg._builtins_loaded = False
    reg._ensure_builtins()
    names = {d["function"]["name"] for d in reg.get_tool_definitions()}
    assert not any(n.startswith("mcp_") for n in names)
    assert "load_mcp_tools" not in names


def test_dispatch_unknown_mcp_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
    from butler.tools.registry import dispatch_tool

    out = json.loads(dispatch_tool("mcp_fake_tool", {}))
    assert "error" in out


@patch("butler.mcp.registry_hook.get_manager")
def test_dispatch_mcp_tool_mock(mock_get_manager, monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    from butler.mcp.bridge import build_tool_refs
    from butler.mcp.types import McpToolRef
    from butler.tools.registry import dispatch_tool

    ref = McpToolRef(
        server_id="demo",
        original_name="ping",
        registered_name=build_registered_name("demo", "ping"),
        classification="readonly",
        input_schema={"type": "object", "properties": {}},
    )
    mgr = MagicMock()  # noqa: magicmock-no-spec — mcp features facade (mgr)
    mgr.get_tool_ref.return_value = ref
    mgr.call_tool.return_value = '{"ok":true,"pong":1}'
    mock_get_manager.return_value = mgr

    with patch("butler.mcp.registry_hook.mcp_sdk_available", return_value=True):
        with patch("butler.mcp.registry_hook.mcp_enabled", return_value=True):
            with patch("butler.mcp.config.mcp_sdk_available", return_value=True):
                with patch("butler.mcp.config.env_truthy", return_value=True):
                    out = json.loads(dispatch_tool(ref.registered_name, {}))
    assert out.get("ok") is True
    mgr.call_tool.assert_called_once()


@patch("butler.mcp.registry_hook.get_manager")
def test_mcp_status_lines_warms_on_diagnostic(mock_get_manager, monkeypatch):
    """Audit: /诊断 must not show empty MCP before first tool call."""
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    from butler.mcp.registry_hook import mcp_status_lines
    from butler.mcp.types import McpServerStatus

    mgr = MagicMock()
    mgr.status_snapshot.return_value = [
        McpServerStatus(server_id="todoist", transport="stdio", connected=True, tool_count=3),
    ]
    mock_get_manager.return_value = mgr

    with patch("butler.mcp.registry_hook.mcp_sdk_available", return_value=True):
        with patch("butler.mcp.registry_hook.mcp_enabled", return_value=True):
            lines = mcp_status_lines("diag-session")

    mgr.ensure_connected.assert_called_once()
    assert lines[0] == "MCP: 已开启"
    assert "todoist" in lines[1]
