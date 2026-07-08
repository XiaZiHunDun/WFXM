"""Best-effort helpers for memory pending commands (L5)."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def owner_pending_lines() -> list[str]:
    def _run() -> list[str]:
        from butler.memory.owner_write_pending import format_owner_pending_lines

        return cast(list[str], format_owner_pending_lines())

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.owner_pending_lines",
        default=[],
    )
    return result if isinstance(result, list) else []


def current_project_name(orchestrator: Any) -> str:
    def _run() -> str:
        pman = getattr(orchestrator, "project_manager", None)
        if pman is None:
            return ""
        cur = pman.get_current()
        if cur is None:
            return ""
        return str(getattr(cur, "name", "") or "")

    return safe_best_effort(
        _run,
        label="memory.pending_command_ops.current_project_name",
        default="",
    ) or ""


def approve_all_owner_pending(bm: Any) -> int:
    def _run() -> int:
        from butler.memory.owner_write_pending import approve_all_owner_pending

        return int(approve_all_owner_pending(bm))

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.approve_all_owner",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0


def approve_owner_pending_index(idx: int, bm: Any) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.memory.owner_write_pending import approve_owner_pending

        return cast(dict[str, Any], approve_owner_pending(idx, bm))

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.approve_owner_index",
        default=None,
    )
    return result if isinstance(result, dict) else None


def list_owner_pending() -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.memory.owner_write_pending import list_owner_pending as _list

        return cast(list[dict[str, Any]], _list())

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.list_owner_pending",
        default=[],
    )
    return result if isinstance(result, list) else []


def reject_all_owner_pending() -> int:
    def _run() -> int:
        from butler.memory.owner_write_pending import reject_all_owner_pending

        return int(reject_all_owner_pending())

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.reject_all_owner",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0


def reject_owner_pending_index(idx: int) -> bool | None:
    def _run() -> bool:
        from butler.memory.owner_write_pending import reject_owner_pending

        return bool(reject_owner_pending(idx))

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.reject_owner_index",
        default=None,
    )
    return result if isinstance(result, bool) else None


def profile_entry_count(profile: Any) -> int | None:
    def _run() -> int:
        items = profile.list_all() if hasattr(profile, "list_all") else []
        return len(items)

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.profile_count",
        default=None,
    )
    return result if isinstance(result, int) else None


def experience_entry_count(experience: Any) -> int | None:
    def _run() -> int:
        items = experience.list_all() if hasattr(experience, "list_all") else []
        return len(items)

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.experience_count",
        default=None,
    )
    return result if isinstance(result, int) else None


def project_memory_bullet_total(pmem: Any) -> int | None:
    def _run() -> int:
        sections = pmem.markdown.list_sections() if hasattr(pmem.markdown, "list_sections") else []
        return sum(len(s.get("items", [])) for s in sections) if sections else 0

    result = safe_best_effort(
        _run,
        label="memory.pending_command_ops.project_bullet_total",
        default=None,
    )
    return result if isinstance(result, int) else None


__all__ = [
    "approve_all_owner_pending",
    "approve_owner_pending_index",
    "current_project_name",
    "experience_entry_count",
    "list_owner_pending",
    "owner_pending_lines",
    "profile_entry_count",
    "project_memory_bullet_total",
    "reject_all_owner_pending",
    "reject_owner_pending_index",
]
