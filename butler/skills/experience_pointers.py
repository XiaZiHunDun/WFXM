"""Experience pointer parsing for execution trust cascade (tool / MCP pins)."""

from __future__ import annotations

import re
from typing import Any

_TOOL_REF_RE = re.compile(
    r"tool:([a-z][a-z0-9_]*)",
    re.IGNORECASE,
)

_MCP_REF_RE = re.compile(
    r"mcp:([a-z0-9][a-z0-9._/-]*)",
    re.IGNORECASE,
)


def extract_tool_refs_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    """Parse ``tool:<builtin_name>`` from experience tags and content."""
    seen: set[str] = set()
    ordered: list[str] = []
    for hit in hits:
        tags = hit.get("tags") or ""
        if isinstance(tags, list):
            blob = " ".join(str(t) for t in tags)
        else:
            blob = str(tags)
        blob = f"{blob} {hit.get('content', '')}"
        for m in _TOOL_REF_RE.finditer(blob):
            name = m.group(1).strip().lower()
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def extract_mcp_refs_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    """Parse ``mcp:<registered>`` or ``mcp:<server>/<tool>`` from experience."""
    seen: set[str] = set()
    ordered: list[str] = []
    for hit in hits:
        tags = hit.get("tags") or ""
        if isinstance(tags, list):
            blob = " ".join(str(t) for t in tags)
        else:
            blob = str(tags)
        blob = f"{blob} {hit.get('content', '')}"
        for m in _MCP_REF_RE.finditer(blob):
            ref = m.group(1).strip()
            if ref and ref.lower() not in seen:
                seen.add(ref.lower())
                ordered.append(ref)
    return ordered


def resolve_mcp_refs_to_registered(refs: list[str]) -> list[str]:
    """Map experience MCP pointers to session registered tool names."""
    from butler.mcp.naming import build_registered_name, is_mcp_registered_name, tool_prefix

    prefix = f"{tool_prefix()}_"
    out: list[str] = []
    seen: set[str] = set()
    for raw in refs:
        ref = str(raw or "").strip()
        if not ref:
            continue
        if is_mcp_registered_name(ref) or ref.startswith(prefix):
            name = ref
        elif "/" in ref:
            server_id, tool_name = ref.split("/", 1)
            if not server_id.strip() or not tool_name.strip():
                continue
            name = build_registered_name(server_id.strip(), tool_name.strip())
        else:
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


__all__ = [
    "extract_mcp_refs_from_hits",
    "extract_tool_refs_from_hits",
    "resolve_mcp_refs_to_registered",
]
