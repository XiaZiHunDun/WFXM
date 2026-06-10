"""Bounded runtime overrides driven by eval hard feedback (O6)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MIN_HALF_LIFE = 7.0
_MAX_HALF_LIFE = 90.0


def _override_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "config" / "eval_overrides.json"


def load_overrides() -> dict[str, Any]:
    path = _override_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_overrides(data: dict[str, Any]) -> None:
    path = _override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def effective_memory_half_life_days(default: float) -> float:
    """Return override half-life if set, else default."""
    raw = load_overrides().get("memory_half_life_days")
    if raw is None:
        return default
    try:
        return max(_MIN_HALF_LIFE, min(_MAX_HALF_LIFE, float(raw)))
    except (TypeError, ValueError):
        return default


def adjust_memory_half_life(*, direction: str, step_days: float = 5.0, base: float = 30.0) -> float:
    """Bounded half-life tweak. direction: 'up' retains longer, 'down' decays faster."""
    current = effective_memory_half_life_days(base)
    if direction == "up":
        new_val = min(_MAX_HALF_LIFE, current + step_days)
    else:
        new_val = max(_MIN_HALF_LIFE, current - step_days)
    data = load_overrides()
    data["memory_half_life_days"] = new_val
    data["updated_at"] = time.time()
    save_overrides(data)
    logger.info("eval override: memory_half_life_days %s → %s", current, new_val)
    return new_val


__all__ = [
    "adjust_memory_half_life",
    "effective_memory_half_life_days",
    "load_overrides",
    "save_overrides",
]
