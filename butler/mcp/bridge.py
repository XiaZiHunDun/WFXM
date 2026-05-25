"""MCP tools → OpenAI function schemas and dispatch."""

from __future__ import annotations

import json
from typing import Any

from butler.mcp.classify import classify_tool
from butler.mcp.config import max_tools, tool_allowed_by_policy
from butler.mcp.naming import build_registered_name
from butler.mcp.types import McpServerConfig, McpToolRef


def _tool_input_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict) and schema:
        return schema
    return {"type": "object", "properties": {}}


def build_tool_refs(config: McpServerConfig, tools: list[Any]) -> list[McpToolRef]:
    refs: list[McpToolRef] = []
    seen: set[str] = set()
    for tool in tools:
        original = str(getattr(tool, "name", "") or "").strip()
        if not original or not tool_allowed_by_policy(config.tools, original):
            continue
        registered = build_registered_name(config.server_id, original)
        if registered in seen:
            continue
        seen.add(registered)
        desc = str(getattr(tool, "description", "") or "")[:2000]
        classification = classify_tool(
            original,
            desc,
            config_override=config.classify.get(original, ""),
        )
        refs.append(
            McpToolRef(
                server_id=config.server_id,
                original_name=original,
                registered_name=registered,
                classification=classification,
                input_schema=_tool_input_schema(tool),
                description=desc or f"MCP tool {original} on {config.server_id}",
            )
        )
        if len(refs) >= max_tools():
            break
    return refs


def refs_to_openai_definitions(refs: list[McpToolRef]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in refs:
        out.append({
            "type": "function",
            "function": {
                "name": ref.registered_name,
                "description": f"[MCP:{ref.server_id}] {ref.description}"[:4000],
                "parameters": ref.input_schema,
            },
        })
    return out


def format_call_result(text: str, *, tool_name: str, server_id: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return json.dumps({
            "ok": True,
            "tool": tool_name,
            "server": server_id,
            "code": "MCP_OK",
            "result": "",
        }, ensure_ascii=False)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            parsed.setdefault("ok", True)
            parsed.setdefault("code", "MCP_OK")
            parsed.setdefault("tool", tool_name)
            parsed.setdefault("server", server_id)
            return json.dumps(parsed, ensure_ascii=False, default=str)
    except json.JSONDecodeError:
        pass
    return json.dumps({
        "ok": True,
        "tool": tool_name,
        "server": server_id,
        "code": "MCP_OK",
        "result": stripped[:50000],
    }, ensure_ascii=False)
