"""MCP-P1: project + global mcp.yaml merge."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_effective_mcp_servers_project_and_global(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir()
    (ws / ".butler" / "mcp.yaml").write_text(
        "version: 1\nservers:\n  demo:\n    transport: stdio\n    command: python3\n    args: []\n",
        encoding="utf-8",
    )
    global_cfg = tmp_path / "mcp.yaml"
    global_cfg.write_text(
        "version: 1\nservers:\n  github:\n    transport: stdio\n    command: npx\n    args: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(global_cfg))

    from butler.registry.mcp_merge import effective_mcp_servers, list_mcp_config_layers
    from butler.mcp.config import load_mcp_servers

    layers = list_mcp_config_layers(workspace=ws)
    assert len(layers) >= 2
    effective = effective_mcp_servers(workspace=ws)
    ids = {r.server_id: r.source for r in effective}
    assert ids["demo"] == "project"
    assert ids["github"] == "config"

    loaded = load_mcp_servers(workspace=ws)
    loaded_ids = {s.server_id for s in loaded}
    assert "demo" in loaded_ids
    assert "github" in loaded_ids


@pytest.mark.unit
def test_global_overrides_same_server_id(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir()
    (ws / ".butler" / "mcp.yaml").write_text(
        "version: 1\nservers:\n  shared:\n    transport: stdio\n    command: python3\n    args: []\n",
        encoding="utf-8",
    )
    global_cfg = tmp_path / "mcp.yaml"
    global_cfg.write_text(
        "version: 1\nservers:\n  shared:\n    transport: stdio\n    command: npx\n    args: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(global_cfg))

    from butler.registry.mcp_merge import effective_mcp_servers
    from butler.mcp.config import load_mcp_servers

    effective = effective_mcp_servers(workspace=ws)
    assert len([r for r in effective if r.server_id == "shared"]) == 1
    assert effective[0].source in ("config", "global")

    loaded = load_mcp_servers(workspace=ws)[0]
    assert loaded.server_id == "shared"
    assert loaded.command == "npx"


@pytest.mark.unit
def test_reload_mcp_connections():
    from unittest.mock import MagicMock, patch

    from butler.registry.mcp_install import reload_mcp_connections

    with patch("butler.mcp.manager.McpConnectionManager") as mgr_cls:
        mgr_cls.return_value = MagicMock()  # noqa: magicmock-no-spec — mcp merge facade (mgr cls)
        ok, msg = reload_mcp_connections()
    assert ok
    mgr_cls.return_value.disconnect_all.assert_called_once()
    assert "断开" in msg


@pytest.mark.unit
def test_mcp_catalog_format_inspect():
    from butler.registry.mcp_catalog import McpCatalogEntry, McpCatalogService

    entry = McpCatalogEntry(
        id="github",
        title="GitHub",
        description="GitHub API",
        env_hints=[{"name": "GITHUB_PERSONAL_ACCESS_TOKEN", "required": True}],
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
    )
    text = McpCatalogService().format_inspect(entry)
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in text
    assert "npx" in text
