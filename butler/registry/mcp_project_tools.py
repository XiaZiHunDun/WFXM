"""Ensure project.yaml tools allowlist includes MCP after catalog install."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from butler.mcp.naming import tool_prefix
from butler.project import Project

logger = logging.getLogger(__name__)


def mcp_auto_project_tools_enabled() -> bool:
    return os.getenv("BUTLER_MCP_AUTO_PROJECT_TOOLS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _has_mcp_tool_entry(tools: list[str]) -> bool:
    prefix = tool_prefix() + "_"
    for raw in tools:
        name = str(raw or "").strip()
        if not name:
            continue
        if name == "mcp_*" or name.startswith(prefix):
            return True
    return False


def ensure_project_mcp_tools(
    workspace: Path,
    server_id: str,
    *,
    auto: bool | None = None,
) -> tuple[bool, str]:
    """
    Add ``mcp_*`` to project.yaml ``tools`` when a non-empty allowlist would block MCP.

    Returns (changed_or_ok, message).
    """
    ws = workspace.expanduser().resolve()
    proj_yaml = ws / "project.yaml"
    if not proj_yaml.is_file():
        return False, (
            f"未找到 {proj_yaml}。\n"
            f"若需限制工具白名单，请创建 project.yaml 并在 tools 中加入 mcp_*。"
        )

    from butler.registry.mcp_project_tools_ops import load_project_yaml_safe

    project = load_project_yaml_safe(proj_yaml)
    if project is None:
        return False, f"无法读取 project.yaml"

    tools = [str(t) for t in (project.tools or []) if str(t).strip()]

    if not tools:
        return True, (
            "project.yaml 的 tools 为空（默认允许全部内置工具）。"
            f" 安装 MCP server={server_id} 后，连接成功即可注入 mcp_* 工具。"
        )

    if _has_mcp_tool_entry(tools):
        return True, "project.yaml 已包含 MCP 工具项（mcp_* 或 mcp_ 前缀）。"

    if auto is None:
        auto = mcp_auto_project_tools_enabled()
    if not auto:
        return False, (
            "project.yaml tools 未包含 mcp_*，Agent 无法调用 MCP 工具。\n"
            "请手动添加 mcp_*，或设置 BUTLER_MCP_AUTO_PROJECT_TOOLS=1 后重装。"
        )

    tools.append("mcp_*")
    project.tools = tools
    project.save()
    return True, f"已在 project.yaml tools 追加 mcp_*（server={server_id}）。"


def format_global_mcp_tools_hint(server_id: str) -> str:
    """Reminder when MCP yaml is global-only."""
    prefix = tool_prefix()
    return (
        f"\n提示: 若在某个项目中使用 MCP，请在 project.yaml 的 tools 中加入 mcp_* "
        f"（或具体工具名如 {prefix}_{server_id}_<tool>）。"
    )


def list_registered_tool_names(server_id: str, block: dict[str, Any]) -> list[str]:
    """Best-effort list of registered tool names after probe (for messages only)."""
    from butler.registry.mcp_project_tools_ops import list_registered_tool_names_safe

    return list(cast(list[str], list_registered_tool_names_safe(server_id, block)))
