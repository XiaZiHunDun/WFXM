"""Session lifecycle best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def current_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(_run, label="lifecycle.session_key", default="")
    return str(result or "")


def current_project_name_safe(orchestrator: Any) -> str:
    pm = getattr(orchestrator, "project_manager", None)
    if pm is None:
        return ""
    session_key = current_session_key_safe()
    if hasattr(pm, "resolve_active_project_name"):
        return str(pm.resolve_active_project_name(session_key=session_key) or "")
    return str(getattr(pm, "current_project", "") or "")


def strip_private_tags_safe(user_msg: str, assistant_msg: str) -> tuple[str, str] | None:
    def _run() -> tuple[str, str]:
        from butler.memory.private_tags import strip_private_tags

        public_user, _ = strip_private_tags(user_msg)
        public_assistant, _ = strip_private_tags(assistant_msg)
        return public_user, public_assistant

    result = safe_best_effort(_run, label="lifecycle.private_tags", default=None)
    if isinstance(result, tuple) and len(result) == 2:
        return str(result[0]), str(result[1])
    return None


def record_experience_write_metric_safe() -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().on_write("experience", success=True)

    safe_best_effort(_run, label="lifecycle.experience_metric", default=None)


def provider_sync_turn_safe(
    provider: Any,
    public_user: str,
    public_assistant: str,
    *,
    session_id: str,
) -> tuple[bool, str]:
    try:
        provider.sync_turn(public_user, public_assistant, session_id=session_id)
        return True, ""
    except Exception as exc:
        logger.warning("Provider memory sync failed: %s", exc)
        return False, str(exc)


def post_commit_flush_safe() -> None:
    def _run() -> None:
        from butler.core.post_commit import flush_after_commit

        flush_after_commit()

    safe_best_effort(_run, label="lifecycle.post_commit_flush", default=None)


def flush_observer_queue_safe(orchestrator: Any, *, session_id: str) -> None:
    def _run() -> None:
        from pathlib import Path

        from butler.memory.observer_queue import flush_observer_queue

        proj = orchestrator.project_manager.get_current(session_key=session_id)
        if proj is not None:
            flush_observer_queue(Path(proj.workspace))

    safe_best_effort(_run, label="lifecycle.observer_flush", default=None)


def sync_turn_memory_loud(
    orchestrator: Any,
    user_msg: str,
    assistant_msg: str,
    *,
    session_id: str,
    run_sync: Any,
) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], run_sync())
    except Exception as exc:
        logger.warning("Memory sync failed: %s", exc)
        return {"skipped": True, "reason": "error", "error": str(exc), "experience_updates": 0}
