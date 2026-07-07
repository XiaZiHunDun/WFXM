"""Session-scoped approval for terminal danger patterns (Hermes smart-approve subset)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import cast

from butler.env_parse import env_truthy, float_env
from butler.permissions.approvals import approvals_path


def smart_pattern_approve_enabled() -> bool:
    return bool(env_truthy("BUTLER_TERMINAL_SMART_APPROVE", default=True))


def _ttl_seconds() -> float:
    try:
        return float(float_env("BUTLER_TERMINAL_PATTERN_APPROVE_TTL", 86400, min=300.0))
    except ValueError:
        return 86400.0


def _patterns_path(session_key: str) -> Path:
    approved = cast(Path, approvals_path(session_key))
    return approved.parent / "terminal_patterns.json"


def _legacy_patterns_path(session_key: str) -> Path:
    import hashlib

    from butler.config import get_butler_home

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return Path(get_butler_home()) / "exec_approvals" / "patterns" / f"{digest}.json"


def _migrate_legacy_patterns(session_key: str) -> None:
    legacy = _legacy_patterns_path(session_key)
    target = _patterns_path(session_key)
    if target.is_file() or not legacy.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
        legacy.unlink(missing_ok=True)
    except OSError:
        return


def is_pattern_approved(session_key: str, pattern: str) -> bool:
    if not smart_pattern_approve_enabled() or not pattern.strip():
        return False
    _migrate_legacy_patterns(session_key)
    path = _patterns_path(session_key)
    if not path.is_file():
        return False
    from butler.tools.terminal_pattern_approval_ops import load_pattern_approval_map_safe

    data = load_pattern_approval_map_safe(path)
    if data is None:
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
    path = _patterns_path(session_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    from butler.tools.terminal_pattern_approval_ops import load_pattern_approval_map_for_write_safe

    data = load_pattern_approval_map_for_write_safe(path)
    data[pattern] = {"expires_at": time.time() + _ttl_seconds(), "approved_at": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
