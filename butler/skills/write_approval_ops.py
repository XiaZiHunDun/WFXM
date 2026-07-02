"""Best-effort helpers for skill write approval (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def approve_pending_skill_safe(skill_manager: Any, item: dict[str, Any]) -> dict[str, Any]:
    try:
        outcome = skill_manager.create(
            str(item.get("name") or ""),
            str(item.get("description") or ""),
            list(item.get("triggers") or []),
            str(item.get("content") or ""),
            _bypass_approval=True,
        )
        return {"ok": True, "outcome": outcome, "name": item.get("name")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def create_pending_skill_safe(skill_manager: Any, item: dict[str, Any]) -> bool:
    def _run() -> bool:
        skill_manager.create(
            str(item.get("name") or ""),
            str(item.get("description") or ""),
            list(item.get("triggers") or []),
            str(item.get("content") or ""),
            _bypass_approval=True,
        )
        return True

    return safe_best_effort(_run, label="write_approval.approve_all_item", default=False) is True
