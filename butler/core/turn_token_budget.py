"""Per-turn token budget hints (+500k, /budget) for extended agent loops."""

from __future__ import annotations

import os
import re
from dataclasses import replace

from butler.core.loop_types import LoopConfig
from butler.env_parse import env_truthy

_BUDGET_CMD_RE = re.compile(
    r"^/budget\s+(\d+(?:\.\d+)?)\s*([kmb])?\s*$",
    re.IGNORECASE,
)
_SHORTHAND_END_RE = re.compile(
    r"\s\+(\d+(?:\.\d+)?)\s*([kmb])\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_VERBOSE_RE = re.compile(
    r"\b(?:use|spend)\s+(\d+(?:\.\d+)?)\s*([kmb])\s*tokens?\b",
    re.IGNORECASE,
)
_MULT = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_TURN_BUDGET_PHRASES = ("本轮尽量做完", "尽量做完", "多用点token", "多用点 token")


def turn_token_budget_enabled() -> bool:
    return env_truthy("BUTLER_TURN_TOKEN_BUDGET", default=True)


def _scale(value: str, suffix: str) -> int:
    return int(float(value) * _MULT.get(suffix.lower(), 1))


def parse_token_budget_text(text: str) -> int | None:
    """Parse +500k suffix or verbose 'use 2M tokens' from user text."""
    if not turn_token_budget_enabled():
        return None
    stripped = (text or "").strip()
    m = _BUDGET_CMD_RE.match(stripped)
    if m:
        suffix = (m.group(2) or "k").lower()
        return _scale(m.group(1), suffix)
    end = _SHORTHAND_END_RE.search(stripped)
    if end:
        return _scale(end.group(1), end.group(2))
    vm = _VERBOSE_RE.search(stripped)
    if vm:
        return _scale(vm.group(1), vm.group(2))
    return None


def wants_extended_turn(text: str) -> bool:
    if not turn_token_budget_enabled():
        return False
    lower = (text or "").lower()
    return any(p in lower for p in _TURN_BUDGET_PHRASES)


def strip_budget_markers(text: str) -> str:
    """Remove budget shorthand from user message before LLM."""
    out = _SHORTHAND_END_RE.sub("", text or "").strip()
    out = _VERBOSE_RE.sub("", out).strip()
    return out


def budget_to_max_iterations(budget_tokens: int, base: int) -> int:
    """Map declared budget to a higher iteration cap (heuristic)."""
    try:
        floor = max(base, int(os.getenv("BUTLER_TURN_BUDGET_MIN_ITERATIONS", "30") or "30"))
        cap = max(floor, int(os.getenv("BUTLER_TURN_BUDGET_MAX_ITERATIONS", "60") or "60"))
    except ValueError:
        floor, cap = max(base, 30), 60
    extra = max(0, int(budget_tokens) // 80_000)
    return min(cap, floor + extra)


def resolve_turn_budget(
    text: str,
    config: LoopConfig,
) -> tuple[LoopConfig, int | None, str]:
    """Return (possibly updated config, budget tokens or None, cleaned user text)."""
    cleaned = text
    budget = parse_token_budget_text(text)
    if budget is None and wants_extended_turn(text):
        try:
            budget = int(os.getenv("BUTLER_TURN_BUDGET_DEFAULT", "500000") or "500000")
        except ValueError:
            budget = 500_000
    if budget is None:
        return config, None, cleaned
    cleaned = strip_budget_markers(text)
    new_max = budget_to_max_iterations(budget, config.max_iterations)
    if new_max <= config.max_iterations:
        return config, budget, cleaned
    return replace(config, max_iterations=new_max), budget, cleaned


def is_budget_command(text: str) -> bool:
    return bool(_BUDGET_CMD_RE.match((text or "").strip()))
