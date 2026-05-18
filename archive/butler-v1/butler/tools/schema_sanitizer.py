"""Sanitize OpenAI-style tool JSON schemas for domestic / local LLM backends.

Adapted from Hermes Agent. Fixes shapes that break strict json-schema-to-grammar
or provider validators (empty objects, nullable union noise, bare type strings).
"""

from __future__ import annotations

import copy
from typing import Any


def sanitize_tool_schemas(tools: list[dict]) -> list[dict]:
    """Return a deep copy of ``tools`` with schemas sanitized for broad compatibility."""
    if not tools:
        return tools
    return [_sanitize_single_tool(tool) for tool in tools]


def _sanitize_single_tool(tool: dict) -> dict:
    out = copy.deepcopy(tool)
    fn = out.get("function") if isinstance(out, dict) else None
    if not isinstance(fn, dict):
        return out

    params = fn.get("parameters")
    if not isinstance(params, dict):
        fn["parameters"] = _minimal_parameters_object()
        return out

    fn["parameters"] = _sanitize_node(params, path=fn.get("name", "<tool>"))
    top = fn["parameters"]
    if not isinstance(top, dict):
        fn["parameters"] = _minimal_parameters_object()
    else:
        if top.get("type") != "object":
            top["type"] = "object"
        if "properties" not in top or not isinstance(top.get("properties"), dict):
            top["properties"] = {}
            top.setdefault("required", [])
        _strip_additional_properties_if_empty_object(top)
        fn["parameters"] = strip_nullable_unions(top, keep_nullable_hint=True)
    return out


def _minimal_parameters_object() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


def strip_nullable_unions(
    schema: Any,
    *,
    keep_nullable_hint: bool = True,
) -> Any:
    """Collapse ``anyOf`` / ``oneOf`` unions that only add a ``null`` branch."""
    if isinstance(schema, list):
        return [
            strip_nullable_unions(item, keep_nullable_hint=keep_nullable_hint)
            for item in schema
        ]
    if not isinstance(schema, dict):
        return schema

    stripped = {
        k: strip_nullable_unions(v, keep_nullable_hint=keep_nullable_hint)
        for k, v in schema.items()
    }
    for key in ("anyOf", "oneOf"):
        variants = stripped.get(key)
        if not isinstance(variants, list):
            continue
        non_null = [
            item
            for item in variants
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null) == 1 and len(non_null) != len(variants):
            replacement = dict(non_null[0]) if isinstance(non_null[0], dict) else {}
            if keep_nullable_hint:
                replacement.setdefault("nullable", True)
            for meta_key in ("title", "description", "default", "examples"):
                if meta_key in stripped and meta_key not in replacement:
                    replacement[meta_key] = stripped[meta_key]
            return strip_nullable_unions(
                replacement, keep_nullable_hint=keep_nullable_hint
            )
    return stripped


def _strip_additional_properties_if_empty_object(node: dict) -> None:
    props = node.get("properties")
    if node.get("type") == "object" and isinstance(props, dict) and len(props) == 0:
        node.pop("additionalProperties", None)


def _sanitize_node(node: Any, path: str) -> Any:
    if isinstance(node, str):
        if node in {
            "object",
            "string",
            "number",
            "integer",
            "boolean",
            "array",
            "null",
        }:
            if node == "object":
                return _minimal_parameters_object()
            return {"type": node}
        return _minimal_parameters_object()

    if isinstance(node, list):
        return [_sanitize_node(item, f"{path}[{i}]") for i, item in enumerate(node)]

    if not isinstance(node, dict):
        return node

    props_key_present = "properties" in node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            if len(non_null) == 1 and isinstance(non_null[0], str):
                out["type"] = non_null[0]
                if "null" in value:
                    out.setdefault("nullable", True)
                continue
            first_str = next(
                (t for t in value if isinstance(t, str) and t != "null"), None
            )
            if first_str:
                out["type"] = first_str
                continue
            out["type"] = "object"
            continue

        if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
            out[key] = {
                sub_k: _sanitize_node(sub_v, f"{path}.{key}.{sub_k}")
                for sub_k, sub_v in value.items()
            }
        elif key in {"items", "additionalProperties"}:
            if isinstance(value, bool):
                out[key] = value
            else:
                out[key] = _sanitize_node(value, f"{path}.{key}")
        elif key in {"anyOf", "oneOf", "allOf"} and isinstance(value, list):
            out[key] = [
                _sanitize_node(item, f"{path}.{key}[{i}]")
                for i, item in enumerate(value)
            ]
        elif key in {"required", "enum", "examples"}:
            out[key] = (
                copy.deepcopy(value) if isinstance(value, (list, dict)) else value
            )
        else:
            out[key] = (
                _sanitize_node(value, f"{path}.{key}")
                if isinstance(value, (dict, list))
                else value
            )

    if out.get("type") == "object" and not isinstance(out.get("properties"), dict):
        out["properties"] = {}
        if not props_key_present:
            out.setdefault("required", [])

    if out.get("type") == "object" and isinstance(out.get("required"), list):
        props = out.get("properties") or {}
        valid = [r for r in out["required"] if isinstance(r, str) and r in props]
        if not valid:
            out.pop("required", None)
        elif len(valid) != len(out["required"]):
            out["required"] = valid

    _strip_additional_properties_if_empty_object(out)
    return out
