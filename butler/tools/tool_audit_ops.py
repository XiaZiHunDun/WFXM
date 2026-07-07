"""Tool audit best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def get_audit_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_audit_session_key

        return str(get_audit_session_key() or "")

    result = safe_best_effort(
        _run,
        label="tool_audit.session_key",
        default="",
    )
    return str(result or "unscoped") or "unscoped"


def resolve_observation_workspace_safe(
    orchestrator: Any,
    session_key: str,
) -> Path | None:
    def _run() -> Path | None:
        proj = orchestrator.project_manager.get_current(session_key=session_key)
        if proj is not None:
            return Path(proj.workspace)
        return None

    result = safe_best_effort(
        _run,
        label="tool_audit.observation_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def record_tool_observation_safe(
    session_key: str,
    *,
    tool: str,
    ok: bool,
    preview: str,
) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_tool_observation

        record_tool_observation(
            session_key,
            tool=tool,
            ok=ok,
            preview=preview,
        )

    safe_best_effort(_run, label="tool_audit.record_observation", default=None)


def enqueue_tool_observation_safe(
    *,
    session_key: str,
    tool: str,
    ok: bool,
    preview: str,
    path: str,
    workspace: Path | None,
) -> None:
    def _run() -> None:
        from butler.memory.observer_queue import enqueue_tool_observation

        enqueue_tool_observation(
            session_key=session_key,
            tool=tool,
            ok=ok,
            preview=preview,
            path=path,
            workspace=workspace,
        )

    safe_best_effort(_run, label="tool_audit.enqueue_observation", default=None)


def run_observation_side_effects_safe(fn: Callable[[], None]) -> None:
    safe_best_effort(fn, label="tool_audit.observation_side_effects", default=None)


def run_permission_denied_hooks_safe(
    name: str,
    args: dict[str, Any],
    err: str,
) -> str | None:
    def _run() -> str | None:
        from butler.hooks.runner import run_permission_denied_hooks

        hook_msg = run_permission_denied_hooks(name, args, err)
        return str(hook_msg) if hook_msg else None

    result = safe_best_effort(
        _run,
        label="tool_audit.permission_denied_hooks",
        default=None,
    )
    return str(result) if result else None
