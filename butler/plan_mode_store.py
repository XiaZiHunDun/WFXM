"""Persist per-session plan mode under ~/.butler/runtime/plan_mode/."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _store_root() -> Path:
    from butler.config import get_butler_settings

    root = get_butler_settings().butler_home / "runtime" / "plan_mode"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(session_key: str) -> str:
    raw = str(session_key or "default").strip() or "default"
    return re.sub(r"[^\w\-.]+", "_", raw)[:120]


def load_plan_mode_flag(session_key: str) -> bool:
    path = _store_root() / f"{_slug(session_key)}.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(data, dict) and data.get("enabled"))


def save_plan_mode_flag(session_key: str, enabled: bool) -> None:
    path = _store_root() / f"{_slug(session_key)}.json"
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.write_text(
        json.dumps({"enabled": True, "session_key": session_key}, ensure_ascii=False),
        encoding="utf-8",
    )
