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
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_SUBDIR = "sessions"


def session_todos_enabled() -> bool:
    return env_truthy("BUTLER_SESSION_TODOS", default=True)


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
    item_id = str(raw.get("id") or position).strip() or str(position)
    return {"id": item_id[:32], "content": content[:500], "status": status}


def replace_session_todos(session_key: str, items: list[Any]) -> dict[str, Any]:
    """Atomically replace the session todo list (delete-all + insert)."""
    if not session_todos_enabled():
        return {"skipped": True, "reason": "disabled"}
    sk = str(session_key or "").strip()
    if not sk:
        return {"skipped": True, "reason": "empty_session"}

    normalized: list[dict[str, str]] = []
    for i, raw in enumerate(items or []):
        item = _normalize_item(raw, i + 1)
        if item is not None:
            normalized.append(item)

    record = {
        "session_key": sk,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": normalized,
    }
    path = todos_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    with _LOCK:
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

    try:
        from butler.core.session_transcript import record_todo_updated

        record_todo_updated(sk, count=len(normalized))
    except Exception:
        pass
    return {"ok": True, "count": len(normalized)}


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
            out.append({
                "id": str(row.get("id") or ""),
                "content": str(row.get("content") or ""),
                "status": str(row.get("status") or "pending"),
            })
    return out


def format_session_todos_for_wechat(session_key: str, *, limit: int = 10) -> str:
    items = load_session_todos(session_key)
    if not items:
        return "会话待办: (空) — Agent 可通过内部 API 写入 todos.json"
    lines = ["会话待办:"]
    for row in items[: max(1, limit)]:
        mark = {
            "completed": "✓",
            "cancelled": "✗",
            "in_progress": "…",
        }.get(row.get("status", ""), "○")
        lines.append(f"  {mark} [{row.get('id')}] {row.get('content', '')[:80]}")
    if len(items) > limit:
        lines.append(f"  … 另有 {len(items) - limit} 条")
    return "\n".join(lines)


def count_open_todos(session_key: str) -> int:
    return sum(
        1
        for t in load_session_todos(session_key)
        if str(t.get("status") or "") in ("pending", "in_progress")
    )
