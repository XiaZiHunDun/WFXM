"""MCP catalog install tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.unit
def test_mcp_catalog_search():
    from butler.registry.mcp_catalog import McpCatalogService

    svc = McpCatalogService()
    hits = svc.search("github")
    assert any(h.id == "github" for h in hits)


@pytest.mark.unit
def test_merge_mcp_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(tmp_path / "mcp.yaml"))
    monkeypatch.setenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "npx,python3")

    from butler.registry.mcp_install import install_catalog_server, remove_mcp_server

    ok, msg = install_catalog_server("github")
    assert ok, msg
    data = yaml.safe_load((tmp_path / "mcp.yaml").read_text(encoding="utf-8"))
    assert "github" in (data.get("servers") or {})

    ok2, _ = remove_mcp_server("github")
    assert ok2


@pytest.mark.unit
def test_remote_mcp_catalog_merge(monkeypatch):
    from unittest.mock import MagicMock, patch

    payload = {
        "version": 1,
        "servers": [
            {
                "id": "remote-demo",
                "title": "Remote Demo",
                "description": "from custom URL",
                "transport": "stdio",
                "command": "python3",
                "args": [],
            }
        ],
    }
    monkeypatch.setenv("BUTLER_MCP_CATALOG_URLS", "https://example.com/mcp-catalog.json")

    with patch("butler.registry.mcp_catalog_remote.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: payload)
        with patch("butler.registry.mcp_catalog_remote.is_safe_url", return_value=True):
            with patch("butler.registry.mcp_catalog_remote.read_cache", return_value=None):
                with patch("butler.registry.mcp_catalog_remote.write_cache"):
                    from butler.registry.mcp_catalog import McpCatalogService

                    svc = McpCatalogService()
                    hits = svc.search("remote")
                    assert any(e.id == "remote-demo" for e in hits)
                    assert svc.get("remote-demo") is not None


@pytest.mark.unit
def test_install_aborts_when_probe_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(tmp_path / "mcp.yaml"))
    monkeypatch.setenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "npx,python3")

    from unittest.mock import patch

    from butler.registry.mcp_install import install_catalog_server

    with patch("butler.registry.mcp_install.probe_server") as mock_probe:
        mock_probe.return_value = {"ok": False, "tool_count": 0, "error": "connection refused"}
        ok, msg = install_catalog_server("github")
    assert not ok
    assert "未写入" in msg
    assert not (tmp_path / "mcp.yaml").is_file()


@pytest.mark.unit
def test_install_to_project_mcp_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(tmp_path / "global-mcp.yaml"))
    monkeypatch.setenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "npx,python3")

    ws = tmp_path / "proj"
    ws.mkdir()
    from butler.registry.mcp_install import install_catalog_server

    ok, msg = install_catalog_server(
        "github",
        workspace=ws,
        use_project=True,
    )
    assert ok, msg
    proj_cfg = ws / ".butler" / "mcp.yaml"
    assert proj_cfg.is_file()
    data = yaml.safe_load(proj_cfg.read_text(encoding="utf-8"))
    assert "github" in (data.get("servers") or {})
    assert not (tmp_path / "global-mcp.yaml").is_file()


@pytest.mark.unit
def test_ensure_project_mcp_tools_appends_wildcard(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "project.yaml").write_text(
        "name: demo\n"
        "type: software\n"
        "description: test\n"
        "tools:\n"
        "  - read_file\n"
        "  - patch\n",
        encoding="utf-8",
    )
    from butler.registry.mcp_project_tools import ensure_project_mcp_tools

    ok, msg = ensure_project_mcp_tools(ws, "github", auto=True)
    assert ok
    assert "mcp_*" in msg
    data = yaml.safe_load((ws / "project.yaml").read_text(encoding="utf-8"))
    assert "mcp_*" in (data.get("tools") or [])


@pytest.mark.unit
def test_ensure_project_mcp_tools_skips_empty_allowlist(tmp_path):
    ws = tmp_path / "proj2"
    ws.mkdir()
    (ws / "project.yaml").write_text(
        "name: demo\n"
        "type: software\n"
        "description: test\n"
        "tools: []\n",
        encoding="utf-8",
    )
    from butler.registry.mcp_project_tools import ensure_project_mcp_tools

    ok, msg = ensure_project_mcp_tools(ws, "github", auto=True)
    assert ok
    assert "为空" in msg
    data = yaml.safe_load((ws / "project.yaml").read_text(encoding="utf-8"))
    assert "mcp_*" not in (data.get("tools") or [])


@pytest.mark.unit
def test_install_project_updates_project_yaml_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(tmp_path / "global-mcp.yaml"))
    monkeypatch.setenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "npx,python3")

    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "project.yaml").write_text(
        "name: demo\n"
        "type: software\n"
        "description: test\n"
        "tools:\n"
        "  - read_file\n",
        encoding="utf-8",
    )
    from butler.registry.mcp_install import install_catalog_server

    ok, msg = install_catalog_server("github", workspace=ws, use_project=True)
    assert ok
    assert "mcp_*" in msg
    data = yaml.safe_load((ws / "project.yaml").read_text(encoding="utf-8"))
    assert "mcp_*" in (data.get("tools") or [])
