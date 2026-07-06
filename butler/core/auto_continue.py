"""Freshness-gated auto-continue after interrupt (Hermes gateway/session subset)."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy, int_env

logger = logging.getLogger(__name__)

_CONTINUE_MARKERS = frozenset({
    "继续",
    "继续执行",
    "continue",
    "/continue",
    "/继续",
    "接着",
    "接着做",
})


def auto_continue_enabled() -> bool:
    return bool(env_truthy("BUTLER_AUTO_CONTINUE", default=True))


def auto_continue_max_age_seconds() -> int:
    try:
        return int(int_env("BUTLER_AUTO_CONTINUE_MAX_AGE", 3600, min=60))
    except ValueError:
        return 3600


def _sessions_root() -> Path:
    from butler.core.compaction_checkpoint import _sessions_root

    return cast(Path, _sessions_root())


def _pending_path(session_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_:" else "_" for c in session_key.strip())
    return _sessions_root() / safe / "auto_continue.json"


def _normalize_user_text(text: str) -> str:
    return (text or "").strip().lower()


def is_continue_marker(text: str) -> bool:
    raw = _normalize_user_text(text)
    if not raw:
        return False
    first = raw.split(maxsplit=1)[0]
    return raw in _CONTINUE_MARKERS or first in _CONTINUE_MARKERS


def capture_auto_continue_pending(
    session_key: str,
    *,
    user_preview: str = "",
    reason: str = "interrupt",
    diagnostics: dict[str, Any] | None = None,
) -> None:
    if not auto_continue_enabled() or not session_key.strip():
        return
    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "monotonic": time.monotonic(),
        "user_preview": (user_preview or "")[:800],
        "reason": str(reason or "interrupt")[:64],
    }
    if isinstance(diagnostics, dict):
        summary = str(diagnostics.get("compression_summary") or "")[:400]
        if summary:
            payload["compression_summary_preview"] = summary
        tr = diagnostics.get("loop_transition_reason")
        if tr:
            payload["transition_reason"] = str(tr)[:80]
    path = _pending_path(session_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("auto_continue capture failed: %s", exc)


def clear_auto_continue_pending(session_key: str) -> None:
    path = _pending_path(session_key)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def load_auto_continue_pending(session_key: str) -> dict[str, Any] | None:
    path = _pending_path(session_key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_auto_continue_user_message(session_key: str, user_text: str) -> str | None:
    """
    If the user sends a short continue marker and a fresh pending exists,
    return a synthetic user message that resumes the interrupted task.
    """
    if not auto_continue_enabled() or not is_continue_marker(user_text):
        return None
    pending = load_auto_continue_pending(session_key)
    if not pending:
        return None
    mono = float(pending.get("monotonic") or 0.0)
    if mono <= 0:
        return None
    if time.monotonic() - mono > auto_continue_max_age_seconds():
        clear_auto_continue_pending(session_key)
        return None

    preview = str(pending.get("user_preview") or "").strip()
    if not preview:
        clear_auto_continue_pending(session_key)
        return None

    clear_auto_continue_pending(session_key)
    return (
        "[AUTO-CONTINUE — resume the interrupted task; do not ask the user to repeat]\n\n"
        f"Previous task:\n{preview}"
    )
