"""MCP config best-effort helpers (P0-A)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

from butler.core.best_effort import safe_best_effort


def butler_home_mcp_config_paths_safe() -> list[Path]:
    def _run() -> list[Path]:
        from butler.config import get_butler_home

        paths: list[Path] = []
        for name in ("mcp.yaml", "mcp.yml"):
            p = get_butler_home() / name
            if p.is_file():
                paths.append(p)
        return paths

    result = safe_best_effort(
        _run,
        label="mcp_config.butler_home_paths",
        default=None,
    )
    if isinstance(result, list) and result:
        return result
    home = Path(os.path.expanduser("~/.butler/mcp.yaml"))
    return [home] if home.is_file() else []


def http_mcp_servers_configured_safe(*, workspace: Path | None = None) -> bool:
    def _run() -> bool:
        from butler.mcp.config import load_mcp_servers

        return any(s.transport == "http" for s in load_mcp_servers(workspace=workspace))

    result = safe_best_effort(
        _run,
        label="mcp_config.http_servers",
        default=False,
    )
    return bool(result)


def parse_http_url_safe(url: str) -> tuple[ParseResult | None, str | None]:
    try:
        return urlparse(url), None
    except Exception as exc:
        return None, f"invalid url: {exc}"
