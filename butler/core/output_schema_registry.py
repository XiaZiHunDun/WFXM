"""Named Pydantic models for common workflow terminal outputs (主线 I 深化)."""

from __future__ import annotations

from typing import Any

_BUILTIN_SPECS: dict[str, list[dict[str, Any]]] = {
    "debate_verdict": [
        {"name": "bull_summary", "type": "string", "required": True},
        {"name": "bear_summary", "type": "string", "required": True},
        {"name": "verdict", "type": "string", "required": True},
        {"name": "confidence", "type": "integer", "required": False},
    ],
    "qa_report": [
        {"name": "status", "type": "string", "required": True},
        {"name": "issues", "type": "string", "required": False},
    ],
}


def get_named_schema(name: str) -> dict[str, Any] | None:
    """Return workflow ``output_schema`` dict for a built-in name."""
    specs = _BUILTIN_SPECS.get(str(name or "").strip())
    if not specs:
        return None
    return {"fields": specs}


def validate_with_named_schema(name: str, data: dict[str, Any]) -> tuple[bool, list[str]]:
    from butler.report import validate_structured_output

    schema = get_named_schema(name)
    if not schema:
        return False, [f"unknown schema name: {name}"]
    return validate_structured_output(data, schema)


def pydantic_model_for_name(name: str) -> Any | None:
    """Return dynamic Pydantic model class when pydantic is installed."""
    schema = get_named_schema(name)
    if not schema:
        return None
    try:
        from pydantic import Field, create_model

        from butler.report import _schema_field_specs

        fields: dict[str, Any] = {}
        for spec in _schema_field_specs(schema):
            fname = str(spec.get("name") or "")
            if not fname:
                continue
            expected = str(spec.get("type") or "string").lower()
            py_type: Any = str
            if expected in ("int", "integer"):
                py_type = int
            elif expected in ("bool", "boolean"):
                py_type = bool
            if spec.get("required", True):
                fields[fname] = (py_type, Field(...))
            else:
                fields[fname] = (py_type | None, None)
        if not fields:
            return None
        return create_model(f"ButlerSchema_{name}", **fields)
    except ImportError:
        return None


__all__ = [
    "get_named_schema",
    "pydantic_model_for_name",
    "validate_with_named_schema",
]
