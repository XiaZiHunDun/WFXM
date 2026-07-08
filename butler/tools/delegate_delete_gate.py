"""Delegate delete-task verification — block false-positive success."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DELETE_PATH_RE = re.compile(
    r"(?:docs|butler|tests|src|novel-factory)/[\w./_-]+\.\w+",
    re.IGNORECASE,
)
_CLAIM_DELETED_RE = re.compile(
    r"(已删除|删除成功|deleted\s+successfully|✅\s*已删)",
    re.IGNORECASE,
)


def _delete_intent(task: str, task_preview: str) -> bool:
    blob = f"{task}\n{task_preview}".lower()
    return "delete_file" in blob or "删除" in blob


def extract_delete_paths(task: str, task_preview: str = "") -> list[str]:
    """Relative workspace paths mentioned in a delete-oriented delegate task."""
    blob = f"{task}\n{task_preview}"
    seen: set[str] = set()
    paths: list[str] = []
    for m in _DELETE_PATH_RE.finditer(blob):
        p = m.group(0).strip().lstrip("./")
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def _resolve_workspace_path(project: Any, rel_path: str) -> Path | None:
    ws_raw = getattr(project, "workspace", None) if project is not None else None
    if not ws_raw:
        return None
    try:
        ws = Path(str(ws_raw)).resolve()
    except (TypeError, ValueError, OSError):
        return None
    rel = str(rel_path or "").strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return None
    return ws / rel


def _paths_deleted_in_messages(messages: list[Any] | None) -> set[str]:
    deleted: set[str] = set()
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        lowered = content.lower()
        if "delete_file" not in lowered and '"action": "deleted"' not in lowered:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not payload.get("success"):
            continue
        path = str(payload.get("path") or "").strip()
        if path:
            deleted.add(path)
    return deleted


def _paths_deleted_in_changes(changes: list[Any] | None) -> set[str]:
    deleted: set[str] = set()
    for change in changes or []:
        action = getattr(change, "action", None)
        if action is None and isinstance(change, dict):
            action = change.get("action")
        if str(action or "").lower() != "deleted":
            continue
        path = getattr(change, "file", None)
        if path is None and isinstance(change, dict):
            path = change.get("file")
        p = str(path or "").strip()
        if p and p != "(文件变更)":
            deleted.add(p)
    return deleted


def _summary_claims_deleted(summary: str) -> bool:
    return bool(_CLAIM_DELETED_RE.search(str(summary or "")))


def apply_delegate_delete_verify_gate(
    *,
    base_success: bool,
    issues: list[str] | None,
    task: str = "",
    task_preview: str = "",
    changes: list[Any] | None = None,
    project: Any = None,
    messages: list[Any] | None = None,
    summary: str = "",
) -> tuple[bool, list[str]]:
    """Fail closed when a delete task reports success but files remain or were not deleted."""
    out = list(issues or [])
    if not base_success:
        return False, out
    if not _delete_intent(task, task_preview):
        return True, out

    paths = extract_delete_paths(task, task_preview)
    deleted_tools = _paths_deleted_in_messages(messages) | _paths_deleted_in_changes(changes)
    claims_deleted = _summary_claims_deleted(summary)

    if paths:
        still_exist: list[str] = []
        for rel in paths:
            resolved = _resolve_workspace_path(project, rel)
            if resolved is not None and resolved.is_file():
                still_exist.append(rel)
        if still_exist:
            msg = (
                "DELETE_VERIFY_GATE: delete task finished but file(s) still exist — "
                + ", ".join(still_exist[:5])
            )
            if msg not in out:
                out.append(msg)
            return False, out

    if claims_deleted and not deleted_tools:
        msg = "DELETE_VERIFY_GATE: summary claims deletion but no delete_file tool success recorded"
        if msg not in out:
            out.append(msg)
        return False, out

    return True, out


__all__ = [
    "apply_delegate_delete_verify_gate",
    "extract_delete_paths",
]
