"""Cold-start hydration for gateway AgentLoop sessions after restart."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_HYDRATION_MARKER = "[SESSION HYDRATED — tool facts from transcript]"


def session_hydrate_enabled() -> bool:
    return env_truthy("BUTLER_SESSION_HYDRATE", default=True)


def _project_workspace(project: Any) -> Path | None:
    workspace = getattr(project, "workspace", None)
    if not workspace:
        return None
    try:
        from butler.project.worktree import effective_workspace

        return effective_workspace(Path(workspace))
    except Exception:
        return Path(workspace).expanduser().resolve(strict=False)


def _last_transcript_assistant_ts(session_key: str) -> float | None:
    try:
        from butler.core.session_epoch import last_assistant_ts_in_epoch

        return last_assistant_ts_in_epoch(session_key)
    except Exception:
        return None


def should_show_recovery_notice(session_key: str, *, gap_seconds: float = 300.0) -> bool:
    """True when transcript has history but this is a fresh in-memory loop."""
    if not env_truthy("BUTLER_SESSION_RECOVERY_NOTICE", default=False):
        return False
    from butler.core.session_tool_index import list_session_read_files

    if not list_session_read_files(session_key):
        return False
    last_ts = _last_transcript_assistant_ts(session_key)
    if last_ts is None:
        return False
    return (time.time() - last_ts) >= max(60.0, float(gap_seconds))


def recovery_notice_text() -> str:
    return (
        "（会话已从 transcript 恢复工具记录；问「刚才读过哪些文件」时只列 read_file 路径。）"
    )


def hydrate_loop_on_create(
    loop: Any,
    session_key: str,
    project: Any,
) -> dict[str, Any]:
    """Inject transcript-derived tool facts into a new AgentLoop."""
    diag: dict[str, Any] = {
        "session_hydrated": False,
        "session_read_paths": 0,
        "session_recovery_notice": False,
    }
    if not session_hydrate_enabled():
        return diag
    sk = str(session_key or "").strip()
    if not sk or loop is None:
        return diag

    ws = _project_workspace(project)
    try:
        from butler.core.session_tool_index import (
            format_session_read_files_block,
            list_session_read_files,
        )

        paths = list_session_read_files(sk, workspace=ws)
        diag["session_read_paths"] = len(paths)
        if not paths and not should_show_recovery_notice(sk):
            return diag

        block = format_session_read_files_block(sk, workspace=ws, title=_HYDRATION_MARKER)
        if hasattr(loop, "_messages"):
            loop._messages.append({"role": "system", "content": block})
            diag["session_hydrated"] = True
            logger.debug(
                "Hydrated session %s with %d read_file path(s)",
                sk[:40],
                len(paths),
            )
    except Exception as exc:
        logger.debug("session hydrate skipped: %s", exc)
        diag["session_hydrate_error"] = str(exc)[:200]

    try:
        from butler.core.read_state import rehydrate_read_state_from_messages

        if hasattr(loop, "messages") and callable(getattr(loop, "messages", None)):
            msgs = loop.messages
        elif hasattr(loop, "_messages"):
            msgs = loop._messages
        else:
            msgs = []
        if msgs:
            rehydrate_read_state_from_messages(list(msgs), session_key=sk)
    except Exception as exc:
        logger.debug("read_state rehydrate on create skipped: %s", exc)

    diag["session_recovery_notice"] = should_show_recovery_notice(sk)
    if diag["session_recovery_notice"]:
        try:
            loop._session_recovery_pending = True
        except AttributeError:
            pass
    return diag


__all__ = [
    "hydrate_loop_on_create",
    "recovery_notice_text",
    "session_hydrate_enabled",
    "should_show_recovery_notice",
]
