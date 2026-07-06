"""Cold-start hydration for gateway AgentLoop sessions after restart."""

from __future__ import annotations

import time
from typing import Any, cast

from butler.env_parse import env_truthy

_HYDRATION_MARKER = "[SESSION HYDRATED — tool facts from transcript]"


def session_hydrate_enabled() -> bool:
    return bool(env_truthy("BUTLER_SESSION_HYDRATE", default=True))


def _project_workspace(project: Any) -> Any:
    from butler.core.session_hydration_ops import project_workspace_safe

    return project_workspace_safe(project)


def _last_transcript_assistant_ts(session_key: str) -> float | None:
    from butler.core.session_hydration_ops import last_transcript_assistant_ts_safe

    return cast(float | None, last_transcript_assistant_ts_safe(session_key))


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
    from butler.core.session_hydration_ops import (
        hydrate_read_files_safe,
        rehydrate_read_state_safe,
    )

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
    hydrated, path_count = hydrate_read_files_safe(
        loop,
        sk,
        workspace=ws,
        marker=_HYDRATION_MARKER,
    )
    diag["session_read_paths"] = path_count
    if hydrated:
        diag["session_hydrated"] = True
    elif path_count == 0 and not should_show_recovery_notice(sk):
        return diag

    rehydrate_read_state_safe(loop, sk)
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
