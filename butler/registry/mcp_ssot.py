"""MCP SSOT index — single merged view written by ``butler mcp sync``."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.registry.mcp_merge import effective_mcp_servers, list_mcp_config_layers


def mcp_ssot_path(*, workspace: Path | None = None) -> Path:
    if workspace is not None and workspace.is_dir():
        return workspace.expanduser().resolve() / ".butler" / "mcp-ssot.yaml"
    from butler.config import get_butler_home

    return Path(get_butler_home()) / "mcp-ssot.yaml"


def build_mcp_ssot_payload(*, workspace: Path | None = None) -> dict[str, Any]:
    layers = list_mcp_config_layers(workspace=workspace)
    effective = effective_mcp_servers(workspace=workspace)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace.resolve()) if workspace and workspace.is_dir() else "",
        "layers": [
            {
                "label": layer.label,
                "path": str(layer.path),
                "server_ids": list(layer.server_ids),
            }
            for layer in layers
        ],
        "servers": [
            {
                "server_id": row.server_id,
                "source": row.source,
                "transport": row.transport,
                "config_path": str(row.path),
            }
            for row in effective
        ],
    }


def write_mcp_ssot(*, workspace: Path | None = None, dry_run: bool = False) -> Path:
    payload = build_mcp_ssot_payload(workspace=workspace)
    path = mcp_ssot_path(workspace=workspace)
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    from butler.io.atomic_write import atomic_write_text

    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)
    return path


def sync_mcp_ssot(
    *,
    workspace: Path | None = None,
    dry_run: bool = False,
    reload: bool = False,
) -> tuple[bool, str]:
    """Refresh SSOT index; optionally reload live MCP connections."""
    path = write_mcp_ssot(workspace=workspace, dry_run=dry_run)
    effective = effective_mcp_servers(workspace=workspace)
    if dry_run:
        return True, (
            f"[dry-run] 将写入 {path}（{len(effective)} 个生效 server，"
            f"{len(list_mcp_config_layers(workspace=workspace))} 层配置）"
        )
    msg = f"已写入 MCP SSOT: {path}（{len(effective)} 个生效 server）"
    if reload:
        from butler.registry.mcp_install import reload_mcp_connections

        ok, rmsg = reload_mcp_connections()
        msg += f"\n{rmsg}"
        return ok, msg
    return True, msg


__all__ = [
    "build_mcp_ssot_payload",
    "mcp_ssot_path",
    "sync_mcp_ssot",
    "write_mcp_ssot",
]
