"""Bounded transform parameter overrides (MOD-7)."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_MAX_ENTRIES = 32
_MIN_MAX_TOOLS = 8
_MAX_MAX_TOOLS = 64


def _override_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "config" / "transform_overrides.json"


def load_transform_overrides() -> dict[str, Any]:
    path = _override_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_transform_overrides(data: dict[str, Any]) -> None:
    path = _override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Trim oldest transform entries if over limit
    transforms = data.get("transforms")
    if isinstance(transforms, dict) and len(transforms) > _MAX_ENTRIES:
        keys = sorted(transforms.keys())[-_MAX_ENTRIES:]
        data["transforms"] = {k: transforms[k] for k in keys}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_transform_params(transform_id: str, base: dict[str, Any]) -> dict[str, Any]:
    data = load_transform_overrides()
    overrides = data.get("transforms") or {}
    if not isinstance(overrides, dict):
        return dict(base)
    extra = overrides.get(transform_id)
    if not isinstance(extra, dict):
        return dict(base)
    merged = {**base, **extra}
    if "max_tools" in merged:
        try:
            merged["max_tools"] = max(
                _MIN_MAX_TOOLS,
                min(_MAX_MAX_TOOLS, int(merged["max_tools"])),
            )
        except (TypeError, ValueError):
            pass
    return merged


def apply_transform_override(transform_id: str, delta: dict[str, Any]) -> None:
    data = load_transform_overrides()
    transforms = data.setdefault("transforms", {})
    if not isinstance(transforms, dict):
        transforms = {}
        data["transforms"] = transforms
    current = transforms.get(transform_id) if isinstance(transforms.get(transform_id), dict) else {}
    merged = {**(current or {}), **delta}
    transforms[transform_id] = merged
    data["updated_at"] = time.time()
    save_transform_overrides(data)


def clear_transform_overrides() -> None:
    save_transform_overrides({})


@contextmanager
def temporary_transform_overrides(overrides: dict[str, dict[str, Any]]) -> Iterator[None]:
    prev = load_transform_overrides()
    data = dict(prev)
    transforms = dict(data.get("transforms") or {})
    for tid, params in overrides.items():
        transforms[tid] = {**(transforms.get(tid) or {}), **params}
    data["transforms"] = transforms
    save_transform_overrides(data)
    try:
        yield
    finally:
        save_transform_overrides(prev)


def format_transform_diagnostic_lines() -> list[str]:
    data = load_transform_overrides()
    transforms = data.get("transforms") or {}
    if not transforms:
        return ["transform_overrides: (none)"]
    parts = [f"{k}={v}" for k, v in list(transforms.items())[:5]]
    return [f"transform_overrides: {', '.join(parts)}"]
