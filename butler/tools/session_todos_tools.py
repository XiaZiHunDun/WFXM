"""Agent tools for session-scoped todo lists (OpenCode todowrite subset)."""

from __future__ import annotations

import json
from typing import Any, Callable


def _session_key() -> str:
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"
    except Exception:
        return "default"


def _tool_session_todos_list(**_) -> str:
    from butler.core.session_todos import load_session_todos, session_todos_enabled

    if not session_todos_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_SESSION_TODOS=0"})
    sk = _session_key()
    items = load_session_todos(sk)
    open_count = sum(
        1 for t in items if str(t.get("status") or "") in ("pending", "in_progress")
    )
    return json.dumps({
        "ok": True,
        "session_key": sk,
        "count": len(items),
        "open_count": open_count,
        "items": items,
        "hint": "用 session_todos_write 提交完整列表，或 merge=true 按 id 局部更新",
    }, ensure_ascii=False)


def _tool_session_todos_write(
    items: list[Any] | None = None,
    merge: bool = False,
    **_,
) -> str:
    from butler.core.session_todos import (
        merge_session_todos,
        replace_session_todos,
        session_todos_enabled,
    )

    if not session_todos_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_SESSION_TODOS=0"})
    if not isinstance(items, list):
        return json.dumps({"ok": False, "error": "items must be an array"})
    sk = _session_key()
    if merge:
        result = merge_session_todos(sk, items)
    else:
        result = replace_session_todos(sk, items)
    if result.get("skipped"):
        return json.dumps({"ok": False, **result})
    if not result.get("ok", True):
        return json.dumps({"ok": False, **result})
    return json.dumps({
        "ok": True,
        "session_key": sk,
        "count": result.get("count", 0),
        "mode": "merge" if merge else "replace",
        "wechat": "主公可发 /待办 查看",
    }, ensure_ascii=False)


def register_session_todos_tools(register: Callable[..., None]) -> None:
    register(
        name="session_todos_list",
        description=(
            "List the current session todo checklist (WeChat session scope). "
            "Use before session_todos_write to see open items."
        ),
        schema={"type": "object", "properties": {}},
        handler=_tool_session_todos_list,
        toolset="planning",
    )
    register(
        name="session_todos_write",
        description=(
            "Replace or merge the session todo list. Pass the full checklist you are tracking "
            "(OpenCode todowrite style). Set merge=true to update by id without dropping others."
        ),
        schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Todo rows: {id?, content, status?}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "cancelled",
                                ],
                            },
                        },
                        "required": ["content"],
                    },
                },
                "merge": {
                    "type": "boolean",
                    "description": "If true, merge by id into existing todos instead of replace-all",
                    "default": False,
                },
            },
            "required": ["items"],
        },
        handler=_tool_session_todos_write,
        toolset="planning",
    )
