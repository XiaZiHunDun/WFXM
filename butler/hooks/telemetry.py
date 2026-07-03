"""In-memory hook execution telemetry for /诊断 and ops."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MAX_PER_SESSION = 12
_MAX_SESSION_BUCKETS = 512
_RECORDS: dict[str, deque[dict[str, Any]]] = {}


def _evict_oldest_session_bucket_locked() -> None:
    while len(_RECORDS) >= _MAX_SESSION_BUCKETS:
        oldest = next(iter(_RECORDS))
        _RECORDS.pop(oldest, None)


def record_hook_run(
    *,
    session_key: str,
    event: str,
    exit_code: int | None,
    preview: str = "",
) -> None:
    key = str(session_key or "").strip() or "_global"
    entry = {
        "ts": time.time(),
        "event": str(event or "?"),
        "exit_code": exit_code,
        "preview": (preview or "")[:120],
    }
    with _LOCK:
        bucket = _RECORDS.get(key)
        if bucket is None:
            _evict_oldest_session_bucket_locked()
            bucket = deque(maxlen=_MAX_PER_SESSION)
            _RECORDS[key] = bucket
        bucket.append(entry)
    from butler.hooks.telemetry_ops import inc_hook_run_metric_safe

    inc_hook_run_metric_safe(
        event=str(event or "?"),
        exit_code=exit_code,
        session_key=session_key,
    )


def recent_hook_runs(session_key: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
    key = str(session_key or "").strip() or "_global"
    with _LOCK:
        rows = list(_RECORDS.get(key, ()))
    return rows[-max(1, int(limit)) :]


def reset_hook_telemetry(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _RECORDS.clear()
        else:
            key = str(session_key or "").strip() or "_global"
            _RECORDS.pop(key, None)
    if session_key:
        from butler.hooks.telemetry_ops import reset_hook_session_metrics_safe

        reset_hook_session_metrics_safe(session_key)


def configured_hook_summary(workspace: Any = None) -> str:
    """Compact summary of loaded hook rules (by event)."""
    from butler.hooks.telemetry_ops import load_hooks_config_summary_safe

    summary = load_hooks_config_summary_safe(workspace)
    return summary if summary is not None else "-"


def format_hook_diagnostic_lines(session_key: str = "") -> list[str]:
    """Lines for ``/诊断`` — configured rules + recent executions."""
    from butler.hooks.telemetry_ops import resolve_hook_workspace_safe

    workspace = resolve_hook_workspace_safe()
    lines = [f"Shell hooks 配置: {configured_hook_summary(workspace)}"]
    recent = recent_hook_runs(session_key, limit=5)
    if not recent:
        lines.append("Shell hooks 最近: 无记录")
        return lines
    lines.append("Shell hooks 最近:")
    for row in recent:
        code = row.get("exit_code")
        code_s = "?" if code is None else str(code)
        preview = row.get("preview") or ""
        suffix = f" — {preview}" if preview else ""
        lines.append(f"  {row.get('event')} exit={code_s}{suffix}")
    return lines
