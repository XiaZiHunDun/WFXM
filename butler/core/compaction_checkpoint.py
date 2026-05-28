"""Persist agent/model/todos snapshot across context compaction (OMO compaction-context-injector subset)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sessions_root() -> Path:
    return Path(os.path.expanduser("~/.butler/sessions"))


def checkpoint_path(session_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_:" else "_" for c in session_key.strip())
    return _sessions_root() / safe / "compact_checkpoint.json"


def capture_checkpoint(
    session_key: str,
    *,
    model: str = "",
    agent_role: str = "",
    tool_names: list[str] | None = None,
    max_iterations: int | None = None,
    open_todos: int = 0,
    compression_summary: str = "",
) -> None:
    if not session_key.strip():
        return
    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "agent_role": agent_role,
        "tool_names": list(tool_names or [])[:64],
        "max_iterations": max_iterations,
        "open_todos": open_todos,
        "compression_summary_preview": (compression_summary or "")[:500],
    }
    path = checkpoint_path(session_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Compaction checkpoint capture failed: %s", exc)


def load_checkpoint(session_key: str) -> dict[str, Any] | None:
    path = checkpoint_path(session_key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def clear_checkpoint(session_key: str) -> None:
    path = checkpoint_path(session_key)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def restore_into_diagnostics(
    session_key: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    """Merge checkpoint fields into turn diagnostics after compaction."""
    ckpt = load_checkpoint(session_key)
    if not ckpt:
        return None
    diagnostics["compaction_checkpoint_restored"] = True
    if ckpt.get("model"):
        diagnostics["compaction_checkpoint_model"] = ckpt["model"]
    if ckpt.get("agent_role"):
        diagnostics["compaction_checkpoint_agent_role"] = ckpt["agent_role"]
    if ckpt.get("open_todos"):
        diagnostics["compaction_checkpoint_open_todos"] = ckpt["open_todos"]
    if ckpt.get("max_iterations") is not None:
        diagnostics["compaction_checkpoint_max_iterations"] = ckpt["max_iterations"]
    tools = ckpt.get("tool_names")
    if isinstance(tools, list) and tools:
        diagnostics["compaction_checkpoint_tool_count"] = len(tools)
    return ckpt


def capture_from_loop(
    session_key: str,
    *,
    loop: Any,
    compression_summary: str = "",
) -> None:
    model = ""
    try:
        client = getattr(loop, "client", None)
        model = str(getattr(client, "model", "") or "")
    except Exception as exc:
        logger.debug("capture from loop skipped: %s", exc)
    tool_names: list[str] = []
    for t in getattr(loop, "tools", None) or []:
        fn = (t.get("function") or {}) if isinstance(t, dict) else {}
        name = fn.get("name") if isinstance(fn, dict) else None
        if name:
            tool_names.append(str(name))
    open_todos = 0
    try:
        from butler.core.session_todos import count_open_todos, session_todos_enabled

        if session_todos_enabled():
            open_todos = count_open_todos(session_key)
    except Exception as exc:
        logger.debug("capture from loop skipped: %s", exc)
    max_iter = getattr(getattr(loop, "config", None), "max_iterations", None)
    capture_checkpoint(
        session_key,
        model=model,
        tool_names=tool_names,
        max_iterations=int(max_iter) if max_iter is not None else None,
        open_todos=open_todos,
        compression_summary=compression_summary,
    )
