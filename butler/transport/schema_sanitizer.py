"""Sanitize tool JSON schemas for strict OpenAI-compatible backends."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_TYPES = {"object", "string", "number", "integer", "boolean", "array", "null"}
_TOP_LEVEL_FORBIDDEN_KEYS = ("allOf", "anyOf", "oneOf", "enum", "not")
_STRIP_ON_RECOVERY_KEYS = frozenset({"pattern", "format"})


def sanitize_tool_schemas(
    tools: list[dict] | None,
    *,
    keep_nullable_hint: bool = True,
) -> list[dict] | None:
    """Return a deep-copied tool list with provider-hostile schema shapes fixed."""
    if not tools:
        return tools
    return [
        _sanitize_single_tool(tool, keep_nullable_hint=keep_nullable_hint)
        for tool in tools
    ]


def _sanitize_single_tool(tool: dict, *, keep_nullable_hint: bool) -> dict:
    out = copy.deepcopy(tool)
    fn = out.get("function") if isinstance(out, dict) else None
    if not isinstance(fn, dict):
        return out

    params = fn.get("parameters")
    if not isinstance(params, dict):
        fn["parameters"] = {"type": "object", "properties": {}}
        return out

    fn["parameters"] = _sanitize_node(
        params,
        path=fn.get("name", "<tool>"),
        keep_nullable_hint=keep_nullable_hint,
    )
    top = fn["parameters"]
    if not isinstance(top, dict):
        fn["parameters"] = {"type": "object", "properties": {}}
        return out

    if top.get("type") != "object":
        top["type"] = "object"
    if not isinstance(top.get("properties"), dict):
        top["properties"] = {}
    fn["parameters"] = strip_nullable_unions(top, keep_nullable_hint=keep_nullable_hint)
    fn["parameters"] = _strip_top_level_combinators(
        fn["parameters"], path=fn.get("name", "<tool>")
    )
    return out


def strip_nullable_unions(schema: Any, *, keep_nullable_hint: bool = True) -> Any:
    """Collapse anyOf/oneOf nullable unions to their single non-null branch."""
    if isinstance(schema, list):
        return [strip_nullable_unions(item, keep_nullable_hint=keep_nullable_hint) for item in schema]
    if not isinstance(schema, dict):
        return schema

    stripped = {
        key: strip_nullable_unions(value, keep_nullable_hint=keep_nullable_hint)
        for key, value in schema.items()
    }
    for key in ("anyOf", "oneOf"):
        variants = stripped.get(key)
        if not isinstance(variants, list):
            continue
        non_null = [
            item for item in variants
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null) == 1 and len(non_null) != len(variants):
            replacement = dict(non_null[0]) if isinstance(non_null[0], dict) else {}
            if keep_nullable_hint:
                replacement.setdefault("nullable", True)
            for meta_key in ("title", "description", "default", "examples"):
                if meta_key in stripped and meta_key not in replacement:
                    replacement[meta_key] = stripped[meta_key]
            return strip_nullable_unions(replacement, keep_nullable_hint=keep_nullable_hint)
    return stripped


def _strip_top_level_combinators(params: dict, *, path: str = "<tool>") -> dict:
    out = dict(params)
    for key in _TOP_LEVEL_FORBIDDEN_KEYS:
        if key in out:
            logger.debug(
                "schema_sanitizer[%s]: stripped top-level %r for strict backend",
                path,
                key,
            )
            out.pop(key, None)
    return out


def _sanitize_node(node: Any, path: str, *, keep_nullable_hint: bool = True) -> Any:
    if isinstance(node, str):
        if node in _SCHEMA_TYPES:
            return {"type": node} if node != "object" else {
                "type": "object",
                "properties": {},
            }
        return {"type": "object", "properties": {}}

    if isinstance(node, list):
        return [
            _sanitize_node(item, f"{path}[{i}]", keep_nullable_hint=keep_nullable_hint)
            for i, item in enumerate(node)
        ]

    if not isinstance(node, dict):
        return node

    out: dict = {}
    for key, value in node.items():
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            if len(non_null) == 1 and isinstance(non_null[0], str):
                out["type"] = non_null[0]
                if keep_nullable_hint and "null" in value:
                    out.setdefault("nullable", True)
                continue
            first_type = next((t for t in value if isinstance(t, str) and t != "null"), None)
            out["type"] = first_type or "object"
            continue

        if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
            out[key] = {
                sub_key: _sanitize_node(
                    sub_value,
                    f"{path}.{key}.{sub_key}",
                    keep_nullable_hint=keep_nullable_hint,
                )
                for sub_key, sub_value in value.items()
            }
        elif key in {"items", "additionalProperties"}:
            out[key] = value if isinstance(value, bool) else _sanitize_node(
                value,
                f"{path}.{key}",
                keep_nullable_hint=keep_nullable_hint,
            )
        elif key in {"anyOf", "oneOf", "allOf"} and isinstance(value, list):
            out[key] = [
                _sanitize_node(
                    item,
                    f"{path}.{key}[{i}]",
                    keep_nullable_hint=keep_nullable_hint,
                )
                for i, item in enumerate(value)
            ]
        elif key in {"required", "enum", "examples"}:
            out[key] = copy.deepcopy(value) if isinstance(value, (list, dict)) else value
        else:
            out[key] = _sanitize_node(
                value,
                f"{path}.{key}",
                keep_nullable_hint=keep_nullable_hint,
            ) if isinstance(value, (dict, list)) else value

    if out.get("type") == "object" and not isinstance(out.get("properties"), dict):
        out["properties"] = {}

    if out.get("type") == "object" and isinstance(out.get("required"), list):
        props = out.get("properties") or {}
        valid = [item for item in out["required"] if isinstance(item, str) and item in props]
        if valid:
            out["required"] = valid
        else:
            out.pop("required", None)

    return out


def strip_pattern_and_format(tools: list[dict] | None) -> tuple[list[dict] | None, int]:
    """Strip pattern/format schema keywords in-place for grammar-parser recovery."""
    if not tools:
        return tools, 0

    stripped = 0

    def _walk(node: Any) -> None:
        nonlocal stripped
        if isinstance(node, dict):
            is_schema_node = "type" in node or "anyOf" in node or "oneOf" in node or "allOf" in node
            for key in list(node.keys()):
                if is_schema_node and key in _STRIP_ON_RECOVERY_KEYS:
                    node.pop(key, None)
                    stripped += 1
                    continue
                _walk(node[key])
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(fn, dict):
            params = fn.get("parameters")
            if isinstance(params, dict):
                _walk(params)

    if stripped:
        logger.info(
            "schema_sanitizer: stripped %d pattern/format keyword(s) from tool schemas",
            stripped,
        )
    return tools, stripped


def is_schema_grammar_error(error: Exception) -> bool:
    """True for local backend JSON-schema grammar conversion failures."""
    text_parts = [str(error).lower()]
    body = getattr(error, "body", None)
    if body is not None:
        text_parts.append(str(body).lower())
    text = " ".join(text_parts)
    return (
        "unable to generate parser" in text
        or "json schema conversion failed" in text
        or "json-schema-to-grammar" in text
        or ("grammar" in text and "schema" in text)
    )
