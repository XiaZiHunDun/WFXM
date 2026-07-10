"""Drift detection between .butler/todos.json and MEMORY.md ## Pending.

Read-only: never writes either store. Owner reviews via WeChat push
(/项目待办 vs /批准记忆 / /拒绝记忆).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VERB_PREFIXES = ("补 ", "整理 ", "添加 ", "实现 ", "完成 ", "修复 ")
_PENDING_LINE_RE = re.compile(
    r"^\s*-\s*\[PENDING\]\s*\[target:(?P<target>[^\]]+)\]\s*\[(?P<ts>[^\]]+)\]\s*(?P<body>.+)$"
)


def _normalize_drift_key(text: str) -> str:
    """Lowercase + collapse whitespace + strip leading verb prefix."""
    s = (text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    for prefix in _VERB_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


def _safe_load_pending(memory_path: Path) -> list[dict[str, str]]:
    """Parse MEMORY.md ## Pending into list of {target, timestamp, content, line}."""
    if not memory_path.is_file():
        return []
    try:
        text = memory_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read MEMORY.md %s: %s", memory_path, exc)
        return []
    out: list[dict[str, str]] = []
    in_pending = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            in_pending = stripped == "## Pending"
            continue
        if not in_pending:
            continue
        m = _PENDING_LINE_RE.match(line)
        if not m:
            continue
        out.append({
            "target": m.group("target").strip(),
            "timestamp": m.group("ts").strip(),
            "content": m.group("body").strip(),
            "line": stripped,
        })
    return out


def _safe_load_todos(todos_path: Path) -> list[dict[str, str]]:
    """Load todos.json; return [] on missing/corrupt."""
    if not todos_path.is_file():
        return []
    try:
        data = json.loads(todos_path.read_text(encoding="utf-8"))
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
                "priority": str(row.get("priority") or "medium"),
            })
    return out


def collect_todos_pending_drift(workspace: Path) -> dict[str, Any]:
    """Compute drift between project todos and MEMORY Pending (read-only)."""
    todos = _safe_load_todos(workspace / ".butler" / "todos.json")
    pending = _safe_load_pending(workspace / ".butler" / "memory" / "MEMORY.md")

    open_todos = [t for t in todos if t.get("status") in ("pending", "in_progress")]
    completed_todos = [t for t in todos if t.get("status") == "completed"]
    cancelled_todos = [t for t in todos if t.get("status") == "cancelled"]
    # dropped: cancelled/whatever; only track completed separately

    todo_index: dict[str, dict[str, str]] = {}
    for t in open_todos + completed_todos:
        key = _normalize_drift_key(t.get("content", ""))
        if key and key not in todo_index:
            todo_index[key] = t
    pending_index: dict[str, dict[str, str]] = {}
    for p in pending:
        key = _normalize_drift_key(p.get("content", ""))
        if key and key not in pending_index:
            pending_index[key] = p

    completed_todo_with_open_pending: list[dict[str, Any]] = []
    pending_with_no_todo: list[dict[str, Any]] = []
    open_todo_with_no_pending: list[dict[str, Any]] = []

    for key, t in todo_index.items():
        p = pending_index.get(key)
        if t.get("status") == "completed" and p is not None:
            completed_todo_with_open_pending.append({"todo": t, "pending": p})
        elif t.get("status") in ("pending", "in_progress") and p is None:
            open_todo_with_no_pending.append({"todo": t})

    for key, p in pending_index.items():
        if key not in todo_index:
            pending_with_no_todo.append({"pending": p})

    drift_total = (
        len(completed_todo_with_open_pending)
        + len(pending_with_no_todo)
        + len(open_todo_with_no_pending)
    )

    return {
        "completed_todo_with_open_pending": completed_todo_with_open_pending,
        "pending_with_no_todo": pending_with_no_todo,
        "open_todo_with_no_pending": open_todo_with_no_pending,
        "counts": {
            "todos_open": len(open_todos),
            "todos_completed": len(completed_todos),
            "pending_open": len(pending),
            "drift_total": drift_total,
        },
    }
