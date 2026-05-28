"""Project + global MCP config merge view (MCP-P1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from butler.mcp.config import _resolve_config_paths
from butler.registry.paths import default_mcp_config_path
import logging


logger = logging.getLogger(__name__)

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
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        block = data.get("servers") if isinstance(data, dict) else None
        if isinstance(block, dict) and sid in block:
            return path
    return None


def resolve_workspace_for_session(session_key: str = "") -> Path | None:
    """Best-effort workspace from active project binding."""
    sk = str(session_key or "").strip()
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is not None and hasattr(orch, "project_manager"):
            if not sk:
                sk = str(get_current_session_key() or "").strip()
            proj = orch.project_manager.get_current(session_key=sk or None)
            if proj is not None:
                ws = getattr(proj, "workspace", None) or getattr(proj, "path", None)
                if ws:
                    p = Path(str(ws)).expanduser()
                    if p.is_dir():
                        return p
    except Exception as exc:
        logger.debug("resolve workspace for session skipped: %s", exc)
    if not sk:
        return None
    try:
        from butler.config import load_settings
        from butler.project.manager import ProjectManager

        pm = ProjectManager(load_settings())
        proj = pm.get_current(session_key=sk)
        if proj is not None:
            ws = getattr(proj, "workspace", None) or getattr(proj, "path", None)
            if ws:
                p = Path(str(ws)).expanduser()
                if p.is_dir():
                    return p
    except Exception as exc:
        logger.debug("resolve workspace for session skipped: %s", exc)
    return None


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
    if not path.is_file():
        return ()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return ()
    block = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return ()
    return tuple(sorted(str(k) for k in block if k))


def _read_server_block(path: Path, server_id: str) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    block = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(block, dict):
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
