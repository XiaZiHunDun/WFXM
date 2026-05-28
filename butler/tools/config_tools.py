"""Butler config query/set tool — lets the Agent read and modify BUTLER_* settings."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def tool_butler_config(action: str = "list", key: str = "", value: str = "", category: str = "", **_: Any) -> str:
    from butler.config_service import config_get, config_list, config_set, config_categories

    action = (action or "list").strip().lower()

    if action == "categories":
        return json.dumps({"categories": config_categories()}, ensure_ascii=False)

    if action == "list":
        items = config_list(category)
        rows = []
        for cv in items:
            row = {"key": cv.key, "value": cv.effective, "source": cv.source}
            if cv.meta:
                row["description"] = cv.meta.description
                row["category"] = cv.meta.category
            rows.append(row)
        return json.dumps({"ok": True, "count": len(rows), "items": rows}, ensure_ascii=False)

    if action == "get":
        if not key:
            return json.dumps({"error": "key is required for action=get"})
        cv = config_get(key)
        result: dict[str, Any] = {"key": cv.key, "value": cv.effective, "source": cv.source}
        if cv.meta:
            result["description"] = cv.meta.description
            result["default"] = cv.meta.default
            result["category"] = cv.meta.category
        return json.dumps(result, ensure_ascii=False)

    if action == "set":
        if not key or not value:
            return json.dumps({"error": "key and value are required for action=set"})
        r = config_set(key, value)
        return json.dumps({
            "ok": r.ok, "message": r.message,
            "needs_reset": r.needs_reset, "needs_restart": r.needs_restart,
        }, ensure_ascii=False)

    return json.dumps({"error": f"unknown action: {action}; use list/get/set/categories"})


def register_config_tools(register_fn) -> None:
    register_fn(
        name="butler_config",
        description=(
            "Query or modify Butler system configuration. "
            "action=list to browse settings (optionally filter by category), "
            "action=get to read one key, "
            "action=set to change a key value at runtime."
        ),
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "set", "categories"],
                    "description": "Operation: list/get/set/categories",
                },
                "key": {"type": "string", "description": "BUTLER_* variable name"},
                "value": {"type": "string", "description": "New value (for action=set)"},
                "category": {"type": "string", "description": "Filter category (for action=list)"},
            },
            "required": ["action"],
        },
        handler=tool_butler_config,
        toolset="system",
    )


__all__ = ["register_config_tools", "tool_butler_config"]
