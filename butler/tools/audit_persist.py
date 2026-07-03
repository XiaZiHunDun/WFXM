"""Optional append-only JSONL persistence for tool audit events."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PERSIST_LOCK = threading.Lock()


def audit_jsonl_enabled() -> bool:
    return os.getenv("BUTLER_TOOL_AUDIT_JSONL", "").strip() == "1"


def audit_jsonl_path() -> Path:
    raw = os.getenv("BUTLER_TOOL_AUDIT_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    from butler.tools.audit_persist_ops import resolve_butler_home_safe

    home = resolve_butler_home_safe()
    return home / "audit" / "tools.jsonl"


def persist_tool_audit_event(event: dict) -> None:
    """Append one audit row when ``BUTLER_TOOL_AUDIT_JSONL=1``."""
    if not audit_jsonl_enabled():
        return
    path = audit_jsonl_path()
    row = {
        "ts": time.time(),
        **event,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with _PERSIST_LOCK:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError as exc:
        logger.debug("Tool audit JSONL append skipped: %s", exc)
