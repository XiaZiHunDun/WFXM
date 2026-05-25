"""Install MCP catalog entries into mcp.yaml."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from butler.registry.audit import append_audit
from butler.registry.mcp_catalog import McpCatalogEntry, McpCatalogService
from butler.registry.mcp_merge import find_server_config_path, resolve_mcp_write_path
from butler.registry.mcp_project_tools import (
    ensure_project_mcp_tools,
    format_global_mcp_tools_hint,
    list_registered_tool_names,
)
from butler.registry.paths import default_mcp_config_path, mcp_lock_path

logger = logging.getLogger(__name__)


def _parse_env_list(raw: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw or []:
        text = str(item).strip()
        if "=" not in text:
            continue
        k, v = text.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _entry_to_server_block(entry: McpCatalogEntry, env: dict[str, str]) -> dict[str, Any]:
    block: dict[str, Any] = {"transport": entry.transport}
    if entry.transport == "stdio":
        block["command"] = entry.command
        if entry.args:
            block["args"] = list(entry.args)
        merged_env = dict(env)
        for hint in entry.env_hints:
            name = str(hint.get("name") or "")
            if name and name not in merged_env:
                merged_env[name] = f"${{{name}}}"
        if merged_env:
            block["env"] = merged_env
    else:
        block["url"] = entry.url
    return block


def _validate_stdio_command(command: str) -> None:
    from butler.mcp.config import stdio_allow_commands

    base = Path(command).name
    allowed = stdio_allow_commands()
    if base not in allowed:
        raise ValueError(
            f"Command '{base}' not in BUTLER_MCP_STDIO_ALLOW_COMMANDS ({','.join(sorted(allowed))})"
        )


def merge_mcp_yaml(
    server_id: str,
    block: dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Path:
    path = config_path or default_mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        data = {"version": 1, "servers": {}}
    if not isinstance(data, dict):
        data = {"version": 1, "servers": {}}
    servers = data.setdefault("servers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["servers"] = servers
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", server_id.strip())[:64]
    servers[sid] = block
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    return path


def probe_server(server_id: str, block: dict[str, Any]) -> dict[str, Any]:
    """Best-effort probe; requires MCP SDK and BUTLER_MCP_ENABLED."""
    result: dict[str, Any] = {"ok": False, "tool_count": 0, "error": ""}
    if os.getenv("BUTLER_MCP_ENABLED", "0").strip().lower() not in ("1", "true", "yes", "on"):
        result["error"] = "BUTLER_MCP_ENABLED=0 — skipped live probe"
        result["ok"] = True
        return result
    try:
        from butler.mcp.config import _parse_server, mcp_sdk_available

        if not mcp_sdk_available():
            result["error"] = "MCP SDK not installed (pip install butler-system[mcp])"
            result["ok"] = True
            return result
        cfg = _parse_server(server_id, block)
        if cfg is None:
            result["error"] = "Invalid server block"
            return result
        from butler.mcp.manager import McpConnectionManager

        mgr = McpConnectionManager()
        refs = mgr.ensure_connected("registry-probe", workspace=None)
        count = sum(1 for r in refs if r.server_id == server_id)
        mgr.disconnect_all()
        result["ok"] = True
        result["tool_count"] = count
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def install_catalog_server(
    server_id: str,
    *,
    env_assignments: list[str] | None = None,
    workspace: Path | None = None,
    use_project: bool = False,
) -> tuple[bool, str]:
    svc = McpCatalogService()
    entry = svc.get(server_id)
    if entry is None:
        return False, f"Unknown MCP catalog id: {server_id}"

    if entry.transport == "stdio" and entry.command:
        _validate_stdio_command(entry.command)

    block = _entry_to_server_block(entry, _parse_env_list(env_assignments))
    try:
        from butler.registry.install_scan import (
            format_scan_message,
            install_pre_scan_fail_closed,
            pre_install_scan_mcp,
        )

        scan = pre_install_scan_mcp(entry, block)
        if not scan.ok_to_install and install_pre_scan_fail_closed():
            return False, format_scan_message(scan) + "\n安装已取消。"
    except Exception as exc:
        logger.debug("MCP pre-install scan skipped: %s", exc)
    try:
        config_path = resolve_mcp_write_path(workspace=workspace, use_project=use_project)
    except ValueError as exc:
        return False, str(exc)

    probe = probe_server(entry.id, block)
    if not probe.get("ok"):
        layer = "项目" if use_project else "全局"
        err = probe.get("error") or "unknown"
        return False, f"探测失败，未写入 {layer} mcp.yaml: {err}"

    path = merge_mcp_yaml(entry.id, block, config_path=config_path)

    lock_path = mcp_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock: dict[str, Any] = {"version": 1, "servers": {}}
    if lock_path.is_file():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("servers"), dict):
                lock["servers"] = dict(existing["servers"])
        except (OSError, json.JSONDecodeError):
            pass
    lock["servers"][entry.id] = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe,
    }
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    append_audit("MCP_INSTALL", entry.id, str(path))

    layer = "项目 .butler" if use_project else "全局"
    msg = f"已写入 {layer} {path}（server={entry.id}）"
    if probe.get("error"):
        msg += f"\n探测: {probe['error']}"
    elif probe.get("tool_count"):
        msg += f"\n探测: {probe['tool_count']} 个工具已注册"
        sample = list_registered_tool_names(entry.id, block)
        if sample:
            msg += f"\n示例工具: {', '.join(sample[:5])}"
            if len(sample) > 5:
                msg += f" …共 {len(sample)} 个"

    if use_project and workspace is not None:
        _ok, tools_msg = ensure_project_mcp_tools(workspace, entry.id)
        msg += f"\n项目 tools: {tools_msg}"
    else:
        msg += format_global_mcp_tools_hint(entry.id)

    reload_mcp_connections()
    return True, msg


def reload_mcp_connections() -> tuple[bool, str]:
    """Disconnect all MCP handles; next turn reloads YAML."""
    try:
        from butler.mcp.manager import McpConnectionManager

        McpConnectionManager().disconnect_all()
        return True, "MCP 连接已断开；下一 turn 将重读 mcp.yaml（含项目 .butler/mcp.yaml）。"
    except Exception as exc:
        return False, f"重载失败: {exc}"


def remove_mcp_server(
    server_id: str,
    *,
    workspace: Path | None = None,
    config_path: Path | None = None,
) -> tuple[bool, str]:
    path = config_path or find_server_config_path(server_id, workspace=workspace)
    if path is None or not path.is_file():
        return False, f"未在 mcp.yaml 中找到 server: {server_id}"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or server_id not in servers:
        return False, f"未配置 server: {server_id}"
    del servers[server_id]
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    reload_mcp_connections()
    append_audit("MCP_REMOVE", server_id, str(path))
    return True, f"已从 {path} 移除 {server_id}"
