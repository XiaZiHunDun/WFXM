"""Project + global MCP config merge view (MCP-P1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.mcp.config import _resolve_config_paths
from butler.registry.paths import default_mcp_config_path
import logging


logger = logging.getLogger(__name__)

# R2-12: surface corrupted MCP config files (YAML parse errors, read
# errors) instead of silently masking them. When a layer's mcp.yaml is
# corrupt, the merge view used to return empty for that layer without any
# signal — operators see "0 servers" and don't know whether the config is
# genuinely empty or whether a partial write / bad edit / disk error ate
# their servers. The buffer below records the corruption so /诊断 can
# surface it, while the read helpers still return empty so a corrupt
# layer never blocks the others.
_MAX_MCP_MERGE_CORRUPTION_ENTRIES = 50
_MAX_MCP_MERGE_CORRUPTION_ERROR_LEN = 200
_mcp_merge_corruptions: list[dict[str, Any]] = []


def recent_mcp_merge_corruptions() -> list[dict[str, Any]]:
    """Read the module-level MCP-merge corruption diagnostics buffer."""
    return list(_mcp_merge_corruptions)


def reset_mcp_merge_corruptions() -> None:
    """Clear the MCP-merge corruption diagnostics buffer (test helper)."""
    _mcp_merge_corruptions.clear()


def _record_corruption(path: Path, exc: BaseException) -> None:
    """Append a corruption record for ``path`` to the diagnostics buffer."""
    logger.error(
        "MCP config layer corrupted (parsing failed); layer skipped: %s",
        path,
        exc_info=exc,
    )
    _mcp_merge_corruptions.append({
        "path": str(path),
        "error": str(exc)[:_MAX_MCP_MERGE_CORRUPTION_ERROR_LEN],
        "type": type(exc).__name__,
    })
    if len(_mcp_merge_corruptions) > _MAX_MCP_MERGE_CORRUPTION_ENTRIES:
        del _mcp_merge_corruptions[
            : len(_mcp_merge_corruptions) - _MAX_MCP_MERGE_CORRUPTION_ENTRIES
        ]


def _load_servers_block(path: Path) -> dict[str, Any] | None:
    """Load the ``servers:`` sub-block from a mcp.yaml.

    Returns:
    - ``None`` if the file does not exist (legitimate empty layer)
    - ``{}`` if the file exists but is unreadable, unparseable, or has
      the wrong root type (corruption; caller should still proceed
      without this layer; corruption is recorded)
    - the parsed ``servers`` dict on success (may be empty)
    """
    from butler.registry.mcp_merge_ops import load_servers_yaml_block_safe

    return load_servers_yaml_block_safe(path, record_corruption=_record_corruption)

@dataclass(frozen=True)
class McpConfigLayer:
    label: str
    path: Path
    server_ids: tuple[str, ...]


@dataclass(frozen=True)
class McpEffectiveServer:
    server_id: str
    source: str
    path: Path
    transport: str = ""


def project_mcp_config_path(workspace: Path) -> Path:
    """Project-layer MCP config (merged before global in load_mcp_servers)."""
    return (workspace.expanduser().resolve() / ".butler" / "mcp.yaml")


def resolve_mcp_write_path(
    *,
    workspace: Path | None = None,
    use_project: bool = False,
) -> Path:
    """Target yaml for catalog install/remove."""
    if use_project:
        if workspace is None or not workspace.is_dir():
            raise ValueError("项目层安装需要有效 --workspace 或已绑定项目工作区")
        return project_mcp_config_path(workspace)
    return default_mcp_config_path()


def find_server_config_path(
    server_id: str,
    *,
    workspace: Path | None = None,
) -> Path | None:
    """Locate which mcp.yaml contains server_id (project layer first)."""
    sid = server_id.strip()
    candidates: list[Path] = []
    if workspace is not None and workspace.is_dir():
        p = project_mcp_config_path(workspace)
        if p.is_file():
            candidates.append(p)
    global_path = resolve_mcp_write_path()
    if global_path.is_file():
        candidates.append(global_path)
    for path in candidates:
        block = _load_servers_block(path)
        if block is None or not block:
            continue
        if sid in block:
            return path
    return None


def resolve_workspace_for_session(session_key: str = "") -> Path | None:
    """Best-effort workspace from active project binding."""
    from butler.registry.mcp_merge_ops import (
        resolve_orchestrator_workspace_safe,
        resolve_project_manager_workspace_safe,
    )

    sk = str(session_key or "").strip()
    ws = resolve_orchestrator_workspace_safe(sk)
    if ws is not None:
        return ws
    return resolve_project_manager_workspace_safe(sk)


def _path_label(path: Path, workspace: Path | None) -> str:
    if workspace is not None:
        try:
            path.resolve().relative_to(workspace.resolve())
            return "project"
        except ValueError:
            pass
    import os

    env_path = os.getenv("BUTLER_MCP_CONFIG", "").strip()
    if env_path and path.resolve() == Path(env_path).expanduser().resolve():
        return "config"
    return "global"


def _read_server_ids(path: Path) -> tuple[str, ...]:
    block = _load_servers_block(path)
    if not block:
        return ()
    return tuple(sorted(str(k) for k in block if k))


def _read_server_block(path: Path, server_id: str) -> dict[str, Any]:
    block = _load_servers_block(path)
    if not block:
        return {}
    raw = block.get(server_id)
    return raw if isinstance(raw, dict) else {}


def list_mcp_config_layers(*, workspace: Path | None = None) -> list[McpConfigLayer]:
    layers: list[McpConfigLayer] = []
    for path in _resolve_config_paths(workspace):
        label = _path_label(path, workspace)
        layers.append(
            McpConfigLayer(
                label=label,
                path=path,
                server_ids=_read_server_ids(path),
            )
        )
    return layers


def effective_mcp_servers(*, workspace: Path | None = None) -> list[McpEffectiveServer]:
    """Later layers override same server_id (project → env → global)."""
    merged: dict[str, McpEffectiveServer] = {}
    for layer in list_mcp_config_layers(workspace=workspace):
        for sid in layer.server_ids:
            block = _read_server_block(layer.path, sid)
            transport = str(block.get("transport") or "stdio")
            merged[sid] = McpEffectiveServer(
                server_id=sid,
                source=layer.label,
                path=layer.path,
                transport=transport,
            )
    return [merged[k] for k in sorted(merged)]


def format_mcp_merge_diagnostic_lines(*, workspace: Path | None = None) -> list[str]:
    layers = list_mcp_config_layers(workspace=workspace)
    if not layers:
        return ["MCP 配置: 无 mcp.yaml"]
    lines = ["MCP 配置层:"]
    for layer in layers:
        ids = ", ".join(layer.server_ids) if layer.server_ids else "（空）"
        lines.append(f"  • {layer.label}: {layer.path.name} → {ids}")
    effective = effective_mcp_servers(workspace=workspace)
    if effective:
        lines.append("生效合并 (后者覆盖同名):")
        for row in effective[:8]:
            lines.append(f"  • {row.server_id} ← {row.source} ({row.transport})")
        if len(effective) > 8:
            lines.append(f"  … 另有 {len(effective) - 8} 个")
    else:
        lines.append("生效合并: （无 server）")
    return lines


def format_mcp_status_message(
    *,
    workspace: Path | None = None,
    include_catalog: bool = True,
) -> str:
    from butler.registry.mcp_catalog import McpCatalogService

    lines: list[str] = []
    if workspace is not None:
        lines.append(f"工作区: {workspace}")
    layers = list_mcp_config_layers(workspace=workspace)
    lines.append("配置层:")
    for layer in layers:
        ids = ", ".join(layer.server_ids) if layer.server_ids else "（空）"
        lines.append(f"  [{layer.label}] {layer.path}")
        lines.append(f"    servers: {ids}")
    effective = effective_mcp_servers(workspace=workspace)
    lines.append("\n生效 server（合并后）:")
    if effective:
        for row in effective:
            lines.append(f"  • {row.server_id} ← {row.source} ({row.transport})")
    else:
        lines.append("  （无）")
    if include_catalog:
        svc = McpCatalogService()
        cat = [e.id for e in svc._load_entries()]
        if cat:
            lines.append("\n目录模板（未安装）:")
            installed = {r.server_id for r in effective}
            for cid in cat:
                mark = "✓" if cid in installed else "○"
                lines.append(f"  {mark} {cid}")
    lines.append("\n安装: butler mcp add <id>  或  /mcp 安装 <id>")
    lines.append("重载: butler mcp reload  或  /mcp 重载")
    return "\n".join(lines)
