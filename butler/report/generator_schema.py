"""Structured output parse/validate for agent reports (no generator import cycle)."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_structured_output(text: str, schema: dict[str, Any] | None) -> dict[str, Any]:
    """Extract JSON object from final text when workflow declares output_schema."""
    if not schema:
        return {}
    blob = str(text or "").strip()
    if not blob:
        return {}
    candidates: list[dict[str, Any]] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", blob, re.DOTALL)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except json.JSONDecodeError:
            pass
    for m in re.finditer(r"\{[^{}]*\}", blob):
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except json.JSONDecodeError:
            continue
    field_names: list[str] = []
    fields_raw = schema.get("fields")
    raw_fields: list[Any] = fields_raw if isinstance(fields_raw, list) else []
    for item in raw_fields:
        if isinstance(item, str):
            field_names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            field_names.append(str(item["name"]))
    if not field_names and isinstance(schema, dict):
        field_names = [
            k for k in schema.keys() if k not in ("type", "fields", "title", "description")
        ]
    if not candidates:
        return {}
    best = candidates[-1]
    if field_names:
        return {k: best.get(k) for k in field_names if k in best}
    return dict(best)


def _schema_field_specs(schema: dict[str, Any]) -> list[dict[str, Any]]:
    fields = schema.get("fields")
    if isinstance(fields, list):
        specs: list[dict[str, Any]] = []
        for item in fields:
            if isinstance(item, str):
                specs.append({"name": item, "type": "string", "required": True})
            elif isinstance(item, dict) and item.get("name"):
                specs.append(dict(item))
        return specs
    specs = []
    for key, val in schema.items():
        if key in ("type", "fields", "title", "description"):
            continue
        if isinstance(val, dict):
            specs.append({"name": key, **val})
        else:
            specs.append({"name": key, "type": "string", "required": True})
    return specs


def validate_structured_output(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Validate parsed output against a lightweight schema (optional Pydantic)."""
    if not schema:
        return True, []
    from butler.report.generator_ops import output_schema_validate_enabled_safe

    if output_schema_validate_enabled_safe() is False:
        return True, []
    specs = _schema_field_specs(schema)
    if not specs:
        return True, []
    errors: list[str] = []
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        required = bool(spec.get("required", True))
        if required and name not in data:
            errors.append(f"missing required field: {name}")
            continue
        if name not in data:
            continue
        val = data[name]
        expected = str(spec.get("type") or "string").strip().lower()
        if expected in ("str", "string") and not isinstance(val, str):
            errors.append(f"{name}: expected string")
        elif expected in ("int", "integer") and not isinstance(val, int):
            errors.append(f"{name}: expected integer")
        elif expected in ("bool", "boolean") and not isinstance(val, bool):
            errors.append(f"{name}: expected boolean")
        enum = spec.get("enum")
        if isinstance(enum, list) and enum and str(val) not in [str(x) for x in enum]:
            errors.append(f"{name}: value not in enum")
    if errors:
        return False, errors
    from butler.report.generator_ops import pydantic_validate_loud

    pydantic_errors = pydantic_validate_loud(data, specs)
    if pydantic_errors:
        return False, pydantic_errors
    return True, []


def build_schema_repair_prompt(
    errors: list[str],
    schema: dict[str, Any] | None,
) -> str:
    if not errors:
        return ""
    fields = [str(s.get("name") or "") for s in _schema_field_specs(schema or {}) if s.get("name")]
    return (
        "结构化输出未通过校验，请仅输出一个 JSON 对象修正以下问题：\n"
        + "\n".join(f"- {e}" for e in errors[:8])
        + (f"\n期望字段: {', '.join(fields)}" if fields else "")
    )


__all__ = [
    "build_schema_repair_prompt",
    "parse_structured_output",
    "validate_structured_output",
]
