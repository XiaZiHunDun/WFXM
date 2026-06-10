"""Session-scoped todo list with replace-all semantics (OpenCode session/todo subset)."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy, int_env

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_SUBDIR = "sessions"
_TODO_PRIORITIES = ("high", "medium", "low")
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def session_todos_enabled() -> bool:
    return env_truthy("BUTLER_SESSION_TODOS", default=True)


def max_todos_items() -> int:
    try:
        return int_env("BUTLER_SESSION_TODOS_MAX_ITEMS", 30, min=1, max=100)
    except ValueError:
        return 30


def _resolve_session_key(session_key: str = "") -> str:
    if str(session_key or "").strip():
        return str(session_key).strip()
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"
    except Exception:
        return "default"


def _safe_segment(value: str) -> str:
    import re

    raw = str(value or "").strip() or "_global"
    return re.sub(r"[^a-zA-Z0-9._+-]+", "_", raw)[:120] or "_global"


def todos_path(session_key: str) -> Path:
    sk = _safe_segment(session_key)
    return get_butler_home() / _SUBDIR / sk / "todos.json"


def _normalize_item(raw: Any, position: int) -> dict[str, str] | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return {
            "id": str(position),
            "content": text[:500],
            "status": "pending",
        }
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
    return {
        "id": item_id[:32],
        "content": content[:500],
        "status": status,
        "priority": priority,
    }


def _persist_session_todos_file(
    sk: str,
    normalized: list[dict[str, str]],
) -> dict[str, Any]:
    """Write todos.json; caller must hold ``_LOCK``."""
    record = {
        "session_key": sk,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": normalized,
    }
    path = todos_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Session todos write failed: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "count": len(normalized)}


def replace_session_todos(session_key: str, items: list[Any]) -> dict[str, Any]:
    """Atomically replace the session todo list (delete-all + insert)."""
    if not session_todos_enabled():
        return {"skipped": True, "reason": "disabled"}
    sk = str(session_key or "").strip()
    if not sk:
        return {"skipped": True, "reason": "empty_session"}

    normalized: list[dict[str, str]] = []
    cap = max_todos_items()
    for i, raw in enumerate(items or []):
        if len(normalized) >= cap:
            break
        item = _normalize_item(raw, i + 1)
        if item is not None:
            normalized.append(item)

    with _LOCK:
        result = _persist_session_todos_file(sk, normalized)

    if result.get("ok"):
        try:
            from butler.core.session_transcript import record_todo_updated

            record_todo_updated(sk, count=len(normalized))
        except Exception as exc:
            logger.debug("replace session todos skipped: %s", exc)
    return result


def _apply_merge_patch(existing: dict[str, dict[str, str]], raw: Any) -> bool:
    """Patch an existing row by id (status/content only) or return False to fall through."""
    if not isinstance(raw, dict):
        return False
    iid = str(raw.get("id") or "").strip()
    if not iid or iid not in existing:
        return False
    content = str(raw.get("content") or raw.get("text") or "").strip()
    if content:
        existing[iid]["content"] = content[:500]
    status = str(raw.get("status") or "").strip().lower()
    if status in ("pending", "in_progress", "completed", "cancelled"):
        existing[iid]["status"] = status
    priority = str(raw.get("priority") or "").strip().lower()
    if priority in _TODO_PRIORITIES:
        existing[iid]["priority"] = priority
    return True


def _sort_todos(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        items,
        key=lambda t: (
            _PRIORITY_RANK.get(str(t.get("priority") or "medium"), 1),
            str(t.get("id") or ""),
        ),
    )


def merge_session_todos(session_key: str, items: list[Any]) -> dict[str, Any]:
    """Merge by ``id`` into existing list; append items without id clash."""
    if not session_todos_enabled():
        return {"skipped": True, "reason": "disabled"}
    sk = _resolve_session_key(session_key)
    if not sk:
        return {"skipped": True, "reason": "empty_session"}
    with _LOCK:
        existing = {str(t.get("id") or ""): dict(t) for t in load_session_todos(sk)}
        for raw in items or []:
            if _apply_merge_patch(existing, raw):
                continue
            item = _normalize_item(raw, len(existing) + 1)
            if item is None:
                continue
            iid = str(item.get("id") or "")
            if iid in existing:
                existing[iid].update(item)
            else:
                existing[iid] = item
        merged = list(existing.values())[: max_todos_items()]
        result = _persist_session_todos_file(sk, merged)

    if result.get("ok"):
        try:
            from butler.core.session_transcript import record_todo_updated

            record_todo_updated(sk, count=result.get("count", 0))
        except Exception as exc:
            logger.debug("merge session todos skipped: %s", exc)
    return result


def load_session_todos(session_key: str) -> list[dict[str, str]]:
    if not session_todos_enabled():
        return []
    path = todos_path(session_key)
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
    return _sort_todos(out)


def format_open_todos_anchor(session_key: str = "", *, limit: int = 8) -> str:
    """Short markdown block for post-compact re-injection."""
    sk = _resolve_session_key(session_key)
    items = [
        t
        for t in load_session_todos(sk)
        if str(t.get("status") or "") in ("pending", "in_progress")
    ]
    if not items:
        return ""
    lines = [
        f"- [{t.get('priority', 'medium')}] [{t.get('id')}] {t.get('content', '')[:120]}"
        for t in _sort_todos(items)[:limit]
    ]
    if len(items) > limit:
        lines.append(f"- … 另有 {len(items) - limit} 条未完成")
    return "## Session todos (open)\n" + "\n".join(lines)


def format_session_todos_for_wechat(session_key: str, *, limit: int = 10) -> str:
    items = load_session_todos(session_key)
    if not items:
        return "会话待办: (空) — 可用工具 session_todos_write / session_todos_list"
    lines = ["会话待办:"]
    for row in _sort_todos(items)[: max(1, limit)]:
        mark = {
            "completed": "✓",
            "cancelled": "✗",
            "in_progress": "…",
        }.get(row.get("status", ""), "○")
        pr = row.get("priority") or "medium"
        lines.append(f"  {mark} [{pr}] [{row.get('id')}] {row.get('content', '')[:80]}")
    if len(items) > limit:
        lines.append(f"  … 另有 {len(items) - limit} 条")
    return "\n".join(lines)


def count_open_todos(session_key: str) -> int:
    return sum(
        1
        for t in load_session_todos(session_key)
        if str(t.get("status") or "") in ("pending", "in_progress")
    )
