"""Classify delegate tasks that skip dev auto-verify gate (PROD-P5-03)."""

from __future__ import annotations

from typing import Any

from butler.gateway.owner_ingest_shortcuts import looks_owner_ingest_intent


def _change_paths(changes: list[Any] | None) -> list[str]:
    out: list[str] = []
    for c in changes or []:
        if isinstance(c, dict):
            path = str(c.get("file") or c.get("path") or "").strip()
        else:
            path = str(getattr(c, "file", None) or getattr(c, "path", "") or "").strip()
        if path and path != "(文件变更)":
            out.append(path.replace("\\", "/"))
    return out


def infer_delegate_task_kind(
    *,
    role: str = "",
    task: str = "",
    task_preview: str = "",
    changes: list[Any] | None = None,
    category_meta: dict[str, Any] | None = None,
) -> str:
    """Return ``ingest`` | ``content_write`` | ``readonly_check`` | ````."""
    meta = dict(category_meta or {})
    explicit = str(meta.get("task_kind") or "").strip().lower()
    if explicit in ("ingest", "content_write", "readonly_check"):
        return explicit

    blob = f"{task}\n{task_preview}".strip()
    lower = blob.lower()
    if "【ext-5 ingest" in lower or looks_owner_ingest_intent(blob):
        return "ingest"

    paths = _change_paths(changes)
    if paths and all(".butler/ingest" in p for p in paths):
        return "ingest"

    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm == "content":
        return "content_write"

    if norm in ("dev", "review") and paths:
        ingest_only = all(
            p.startswith("docs/")
            or ".butler/ingest" in p
            or p.endswith((".md", ".txt"))
            for p in paths
        )
        if ingest_only and "ingest" in lower:
            return "ingest"

    return ""


def is_dev_verify_exempt(
    *,
    role: str = "",
    task: str = "",
    task_preview: str = "",
    changes: list[Any] | None = None,
    category_meta: dict[str, Any] | None = None,
) -> bool:
    kind = infer_delegate_task_kind(
        role=role,
        task=task,
        task_preview=task_preview,
        changes=changes,
        category_meta=category_meta,
    )
    return kind in ("ingest", "content_write", "readonly_check")


__all__ = [
    "infer_delegate_task_kind",
    "is_dev_verify_exempt",
]
