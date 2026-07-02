"""Session hydration best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def project_workspace_safe(project: Any) -> Path | None:
    workspace = getattr(project, "workspace", None)
    if not workspace:
        return None

    def _run() -> Path:
        from butler.project.worktree import effective_workspace

        return effective_workspace(Path(workspace))

    result = safe_best_effort(
        _run,
        label="session_hydration.workspace",
        default=Path(workspace).expanduser().resolve(strict=False),
    )
    return result if isinstance(result, Path) else None


def last_transcript_assistant_ts_safe(session_key: str) -> float | None:
    def _run() -> float | None:
        from butler.core.session_epoch import last_assistant_ts_in_epoch

        return last_assistant_ts_in_epoch(session_key)

    return safe_best_effort(_run, label="session_hydration.transcript_ts", default=None)


def hydrate_read_files_safe(
    loop: Any,
    session_key: str,
    *,
    workspace: Path | None,
    marker: str,
) -> tuple[bool, int]:
    def _run() -> tuple[bool, int]:
        from butler.core.session_tool_index import (
            format_session_read_files_block,
            list_session_read_files,
        )

        paths = list_session_read_files(session_key, workspace=workspace)
        if not paths:
            return False, 0
        block = format_session_read_files_block(session_key, workspace=workspace, title=marker)
        if hasattr(loop, "_messages"):
            loop._messages.append({"role": "system", "content": block})
            return True, len(paths)
        return False, len(paths)

    result = safe_best_effort(_run, label="session_hydration.read_files", default=(False, 0))
    if isinstance(result, tuple) and len(result) == 2:
        return bool(result[0]), int(result[1])
    return False, 0


def rehydrate_read_state_safe(loop: Any, session_key: str) -> None:
    def _run() -> None:
        from butler.core.read_state import rehydrate_read_state_from_messages

        if hasattr(loop, "messages") and callable(getattr(loop, "messages", None)):
            msgs = loop.messages
        elif hasattr(loop, "_messages"):
            msgs = loop._messages
        else:
            msgs = []
        if msgs:
            rehydrate_read_state_from_messages(list(msgs), session_key=session_key)

    safe_best_effort(_run, label="session_hydration.read_state", default=None)
