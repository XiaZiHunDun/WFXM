"""Project-level persistent todo tools — survive across sessions."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_MAX = 50
_TODO_PRIORITIES = ("high", "medium", "low")
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _get_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        proj = orch.project_manager.active_project
        if proj and getattr(proj, "workspace", None):
            return Path(proj.workspace)
    except Exception as exc:
        logger.debug("get workspace skipped: %s", exc)
    return None


def _todos_path(workspace: Path) -> Path:
    return workspace / ".butler" / "todos.json"


def _load(workspace: Path) -> list[dict[str, str]]:
    path = _todos_path(workspace)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for row in items:
        if isinstance(row, dict) and row.get("content"):
            pr = str(row.get("priority") or "medium").strip().lower()
            if pr not in _TODO_PRIORITIES:
                pr = "medium"
            out.append({
                "id": str(row.get("id") or ""),
                "content": str(row.get("content") or ""),
                "status": str(row.get("status") or "pending"),
                "priority": pr,
            })
    return sorted(
        out,
        key=lambda t: (
            _PRIORITY_RANK.get(str(t.get("priority") or "medium"), 1),
            str(t.get("id") or ""),
        ),
    )


def _save(workspace: Path, items: list[dict[str, str]]) -> dict[str, Any]:
    record = {
        "project": workspace.name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items[:_MAX],
    }
    path = _todos_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    with _LOCK:
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("Project todos write failed: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "count": len(items[:_MAX])}


def _normalize_item(raw: Any, position: int) -> dict[str, str] | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return {"id": str(position), "content": text[:500], "status": "pending", "priority": "medium"}
    if not isinstance(raw, dict):
        return None
    content = str(raw.get("content") or raw.get("text") or "").strip()
    if not content:
        return None
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in ("pending", "in_progress", "completed", "cancelled"):
        status = "pending"
    priority = str(raw.get("priority") or "medium").strip().lower()
    if priority not in _TODO_PRIORITIES:
        priority = "medium"
    item_id = str(raw.get("id") or position).strip() or str(position)
    return {"id": item_id[:32], "content": content[:500], "status": status, "priority": priority}


def _tool_project_todos_list(**_) -> str:
    ws = _get_workspace()
    if ws is None:
        return json.dumps({"ok": False, "error": "NO_ACTIVE_PROJECT"})
    items = _load(ws)
    open_count = sum(1 for t in items if t.get("status") in ("pending", "in_progress"))
    return json.dumps({
        "ok": True, "project": ws.name, "count": len(items),
        "open_count": open_count, "items": items,
    }, ensure_ascii=False)


def _tool_project_todos_write(items: list[Any] | None = None, merge: bool = False, **_) -> str:
    ws = _get_workspace()
    if ws is None:
        return json.dumps({"ok": False, "error": "NO_ACTIVE_PROJECT"})
    if not isinstance(items, list):
        return json.dumps({"ok": False, "error": "items must be an array"})

    if merge:
        existing = {str(t.get("id") or ""): dict(t) for t in _load(ws)}
        for raw in items:
            if isinstance(raw, dict):
                iid = str(raw.get("id") or "").strip()
                if iid and iid in existing:
                    for k in ("content", "status", "priority"):
                        v = str(raw.get(k) or "").strip()
                        if v:
                            existing[iid][k] = v
                    continue
            item = _normalize_item(raw, len(existing) + 1)
            if item:
                existing[item["id"]] = item
        normalized = list(existing.values())
    else:
        normalized = []
        for i, raw in enumerate(items):
            if len(normalized) >= _MAX:
                break
            item = _normalize_item(raw, i + 1)
            if item:
                normalized.append(item)

    result = _save(ws, normalized)
    if not result.get("ok"):
        return json.dumps(result)
    return json.dumps({
        "ok": True, "project": ws.name, "count": result["count"],
        "mode": "merge" if merge else "replace",
        "wechat": "主公可发 /项目待办 查看",
    }, ensure_ascii=False)


def format_project_todos_for_wechat(workspace: Path, *, limit: int = 10) -> str:
    items = _load(workspace)
    if not items:
        return "项目待办: (空)"
    open_items = [t for t in items if t.get("status") in ("pending", "in_progress")]
    done_items = [t for t in items if t.get("status") not in ("pending", "in_progress")]
    lines = [f"项目待办（{len(open_items)} 进行中 / {len(done_items)} 已完成）:"]
    for row in open_items[:limit]:
        mark = "…" if row.get("status") == "in_progress" else "○"
        pr = row.get("priority") or "medium"
        lines.append(f"  {mark} [{pr}] {row.get('content', '')[:80]}")
    if len(open_items) > limit:
        lines.append(f"  … 另有 {len(open_items) - limit} 条")
    return "\n".join(lines)


def register_project_todos_tools(register: Callable[..., None]) -> None:
    register(
        name="project_todos_list",
        description=(
            "List the persistent project-level todo checklist. "
            "Unlike session_todos, these survive across sessions."
        ),
        schema={"type": "object", "properties": {}},
        handler=_tool_project_todos_list,
        toolset="planning",
    )
    register(
        name="project_todos_write",
        description=(
            "Replace or merge the project-level persistent todo list. "
            "Set merge=true to update by id. These persist across sessions."
        ),
        schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Todo rows: {id?, content, status?, priority?}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["content"],
                    },
                },
                "merge": {"type": "boolean", "description": "Merge by id instead of replace-all", "default": False},
            },
            "required": ["items"],
        },
        handler=_tool_project_todos_write,
        toolset="planning",
    )
