"""Bounded runtime overrides driven by eval hard feedback (O6) and experiments."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_MIN_HALF_LIFE = 7.0
_MAX_HALF_LIFE = 90.0
_MIN_FIX_ROUNDS = 1
_MAX_FIX_ROUNDS = 6
_MIN_DELEGATE_ITERS = 8
_MAX_DELEGATE_ITERS = 48
_MIN_GUIDANCE_CASES = 3
_MAX_GUIDANCE_CASES = 12


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


def effective_coding_knowledge_strict(default: bool = True) -> bool:
    raw = load_overrides().get("coding_knowledge_strict_experience")
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes")


def effective_coding_guidance_max_cases(default: int = 6) -> int:
    raw = load_overrides().get("coding_guidance_max_cases")
    if raw is None:
        return default
    try:
        return max(_MIN_GUIDANCE_CASES, min(_MAX_GUIDANCE_CASES, int(raw)))
    except (TypeError, ValueError):
        return default


def effective_dev_max_fix_rounds(default: int = 3) -> int:
    raw = load_overrides().get("dev_max_fix_rounds")
    if raw is None:
        return default
    try:
        return max(_MIN_FIX_ROUNDS, min(_MAX_FIX_ROUNDS, int(raw)))
    except (TypeError, ValueError):
        return default


def effective_delegate_max_iterations(default: int = 24) -> int:
    raw = load_overrides().get("delegate_max_iterations")
    if raw is None:
        return default
    try:
        return max(_MIN_DELEGATE_ITERS, min(_MAX_DELEGATE_ITERS, int(raw)))
    except (TypeError, ValueError):
        return default


def effective_dev_auto_verify_levels(default: str = "lint,test") -> str:
    raw = load_overrides().get("dev_auto_verify_levels")
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


def adjust_dev_coding_guidance(*, strict: bool = True, max_cases: int = 8) -> dict[str, Any]:
    """Tighten coding knowledge injection when DevEngine benchmark is low."""
    data = load_overrides()
    prev = {
        "coding_knowledge_strict_experience": data.get("coding_knowledge_strict_experience"),
        "coding_guidance_max_cases": data.get("coding_guidance_max_cases"),
    }
    data["coding_knowledge_strict_experience"] = strict
    data["coding_guidance_max_cases"] = max(
        _MIN_GUIDANCE_CASES, min(_MAX_GUIDANCE_CASES, int(max_cases)),
    )
    data["updated_at"] = time.time()
    save_overrides(data)
    action = {
        "action": "adjust_dev_coding_guidance",
        "strict_experience": strict,
        "max_cases": data["coding_guidance_max_cases"],
        "previous": prev,
    }
    logger.info("eval override: dev coding guidance strict=%s max_cases=%s", strict, max_cases)
    return action


def adjust_delegate_rescue(
    *,
    fix_rounds_step: int = 1,
    delegate_iters_step: int = 4,
    verify_levels: str = "lint,typecheck,test",
    base_fix_rounds: int = 3,
    base_delegate_iters: int = 24,
) -> dict[str, Any]:
    """Increase delegate/dev rescue capacity when B9 LIVE pass rate is low."""
    data = load_overrides()
    prev_fix = effective_dev_max_fix_rounds(base_fix_rounds)
    prev_iters = effective_delegate_max_iterations(base_delegate_iters)
    new_fix = min(_MAX_FIX_ROUNDS, prev_fix + fix_rounds_step)
    new_iters = min(_MAX_DELEGATE_ITERS, prev_iters + delegate_iters_step)
    data["dev_max_fix_rounds"] = new_fix
    data["delegate_max_iterations"] = new_iters
    data["dev_auto_verify_levels"] = verify_levels
    data["updated_at"] = time.time()
    save_overrides(data)
    action = {
        "action": "adjust_delegate_rescue",
        "dev_max_fix_rounds": new_fix,
        "delegate_max_iterations": new_iters,
        "dev_auto_verify_levels": verify_levels,
        "previous": {
            "dev_max_fix_rounds": prev_fix,
            "delegate_max_iterations": prev_iters,
        },
    }
    logger.info(
        "eval override: delegate rescue fix_rounds=%s delegate_iters=%s verify=%s",
        new_fix, new_iters, verify_levels,
    )
    return action


def delegate_routing_hint_enabled() -> bool:
    raw = load_overrides().get("delegate_routing_hint")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes")


def adjust_delegate_routing(*, enable_hint: bool = True) -> dict[str, Any]:
    """Enable delegate routing reminder when tool_selection / routing scores are low."""
    data = load_overrides()
    prev = data.get("delegate_routing_hint")
    data["delegate_routing_hint"] = enable_hint
    data["prefer_delegate_for_dev"] = True
    data["updated_at"] = time.time()
    save_overrides(data)
    return {
        "action": "adjust_delegate_routing",
        "delegate_routing_hint": enable_hint,
        "previous": prev,
    }


@contextmanager
def temporary_overrides(patch: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Apply override patch for the duration of an eval experiment."""
    backup = load_overrides()
    merged = dict(backup)
    merged.update(patch)
    merged["experiment_active"] = True
    merged["experiment_patch"] = patch
    merged["updated_at"] = time.time()
    save_overrides(merged)
    try:
        yield merged
    finally:
        save_overrides(backup)


__all__ = [
    "adjust_delegate_rescue",
    "adjust_delegate_routing",
    "adjust_dev_coding_guidance",
    "delegate_routing_hint_enabled",
    "adjust_memory_half_life",
    "effective_coding_guidance_max_cases",
    "effective_coding_knowledge_strict",
    "effective_delegate_max_iterations",
    "effective_dev_auto_verify_levels",
    "effective_dev_max_fix_rounds",
    "effective_memory_half_life_days",
    "load_overrides",
    "save_overrides",
    "temporary_overrides",
]
