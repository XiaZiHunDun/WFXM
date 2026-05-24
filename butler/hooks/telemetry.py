"""In-memory hook execution telemetry for /诊断 and ops."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_LOCK = threading.Lock()
_MAX_PER_SESSION = 12
_RECORDS: dict[str, deque[dict[str, Any]]] = {}


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
        bucket = _RECORDS.setdefault(key, deque(maxlen=_MAX_PER_SESSION))
        bucket.append(entry)


def recent_hook_runs(session_key: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
    key = str(session_key or "").strip() or "_global"
    with _LOCK:
        rows = list(_RECORDS.get(key, ()))
    return rows[-max(1, int(limit)) :]


def reset_hook_telemetry(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _RECORDS.clear()
            return
        key = str(session_key or "").strip() or "_global"
        _RECORDS.pop(key, None)


def configured_hook_summary(workspace: Any = None) -> str:
    """Compact summary of loaded hook rules (by event)."""
    try:
        from butler.hooks.loader import load_hooks_config
        from pathlib import Path

        ws = Path(workspace) if workspace is not None else None
        rules = load_hooks_config(ws)
    except Exception:
        return "-"
    if not rules:
        return "未配置"
    counts: dict[str, int] = {}
    for rule in rules:
        counts[rule.event] = counts.get(rule.event, 0) + 1
    return ", ".join(f"{ev}×{n}" for ev, n in sorted(counts.items()))


def format_hook_diagnostic_lines(session_key: str = "") -> list[str]:
    """Lines for ``/诊断`` — configured rules + recent executions."""
    key = str(session_key or "").strip() or "_global"
    try:
        from butler.hooks.runner import _resolve_workspace

        workspace = _resolve_workspace()
    except Exception:
        workspace = None
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
