"""Session-scoped approval for terminal danger patterns (Hermes smart-approve subset)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from butler.env_parse import env_truthy, float_env
import logging


logger = logging.getLogger(__name__)

def smart_pattern_approve_enabled() -> bool:
    return env_truthy("BUTLER_TERMINAL_SMART_APPROVE", default=True)


def _ttl_seconds() -> float:
    try:
        return float_env("BUTLER_TERMINAL_PATTERN_APPROVE_TTL", 86400, min=300.0)
    except ValueError:
        return 86400.0


def _patterns_dir() -> Path:
    from butler.config import get_butler_home

    path = get_butler_home() / "exec_approvals" / "patterns"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(session_key: str) -> Path:
    import hashlib

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return _patterns_dir() / f"{digest}.json"


def is_pattern_approved(session_key: str, pattern: str) -> bool:
    if not smart_pattern_approve_enabled() or not pattern.strip():
        return False
    path = _session_path(session_key)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    entry = data.get(pattern)
    if not isinstance(entry, dict):
        return False
    if time.time() > float(entry.get("expires_at") or 0):
        data.pop(pattern, None)
        if data:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        return False
    return True


def approve_pattern(session_key: str, pattern: str) -> None:
    if not pattern.strip():
        return
    path = _session_path(session_key)
    data: dict = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except Exception as exc:
            logger.debug("approve pattern skipped: %s", exc)
    data[pattern] = {"expires_at": time.time() + _ttl_seconds(), "approved_at": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
