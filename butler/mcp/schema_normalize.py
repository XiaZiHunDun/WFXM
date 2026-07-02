"""Normalize MCP / registry tool schemas (double-wrap protection)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _is_openai_function_shell(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if str(obj.get("type") or "") != "function":
        return False
    fn = obj.get("function")
    if not isinstance(fn, dict):
        return False
    if fn.get("name"):
        return True
    inner = fn.get("function")
    return isinstance(inner, dict) and bool(inner.get("name"))


def normalize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten double-wrapped OpenAI function schemas."""
    if not isinstance(schema, dict):
        return schema
    out = deepcopy(schema)
    while _is_openai_function_shell(out):
        fn = out.get("function")
        if not isinstance(fn, dict):
            break
        if fn.get("name"):
            out = {"type": "function", "function": _normalize_function_block(fn)}
            break
        inner = fn.get("function")
        if isinstance(inner, dict) and inner.get("name"):
            out = {"type": "function", "function": _normalize_function_block(inner)}
            break
        break
    if "name" in out and "parameters" in out and "type" not in out:
        return {
            "type": "function",
            "function": {
                "name": out.get("name"),
                "description": out.get("description", ""),
                "parameters": _normalize_parameters(out.get("parameters")),
            },
        }
    return out


def _normalize_function_block(fn: dict[str, Any]) -> dict[str, Any]:
    block = dict(fn)
    block["parameters"] = _normalize_parameters(block.get("parameters"))
    return block


def _normalize_parameters(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {"type": "object", "properties": {}}
    if _is_openai_function_shell(params):
        inner = params.get("function")
        if isinstance(inner, dict):
            return _normalize_parameters(inner.get("parameters"))
    p = dict(params)
    if "type" not in p:
        p["type"] = "object"
    if "properties" not in p:
        p["properties"] = {}
    return p


def normalize_tool_definitions(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_tool_schema(d) for d in definitions if isinstance(d, dict)]


__all__ = ["normalize_tool_definitions", "normalize_tool_schema"]
