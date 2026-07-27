"""Registered MCP tool names (mcp_{server}_{tool})."""

from __future__ import annotations

import os
import re

from butler.defaults.env_defaults import MCP_TOOL_PREFIX_DEFAULT


def tool_prefix() -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", os.getenv("BUTLER_MCP_TOOL_PREFIX", MCP_TOOL_PREFIX_DEFAULT).strip() or MCP_TOOL_PREFIX_DEFAULT)


def safe_segment(value: str, *, max_len: int = 48) -> str:
    out = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip())
    out = out.strip("_") or "x"
    return out[:max_len]


def build_registered_name(server_id: str, tool_name: str) -> str:
    return f"{tool_prefix()}_{safe_segment(server_id)}_{safe_segment(tool_name, max_len=80)}"


def is_mcp_registered_name(name: str) -> bool:
    prefix = tool_prefix() + "_"
    return str(name or "").startswith(prefix)
