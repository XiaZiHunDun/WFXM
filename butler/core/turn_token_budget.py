"""Per-turn token budget hints (+500k, /budget) for extended agent loops."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from butler.context_settings import TurnBudgetSettings
from butler.core.loop_types import LoopConfig

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


def _turn_budget_settings() -> TurnBudgetSettings:
    from butler.context_settings import resolve_context_config

    return resolve_context_config().turn_budget


def turn_token_budget_enabled() -> bool:
    return bool(_turn_budget_settings().enabled)


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
    tb = _turn_budget_settings()
    floor = max(base, int(tb.min_iterations))
    cap = max(floor, int(tb.max_iterations))
    extra = max(0, int(budget_tokens) // 80_000)
    return int(min(cap, floor + extra))


def resolve_turn_budget(
    text: str,
    config: LoopConfig,
) -> tuple[LoopConfig, int | None, str]:
    """Return (possibly updated config, budget tokens or None, cleaned user text)."""
    cleaned = text
    budget = parse_token_budget_text(text)
    if budget is None and wants_extended_turn(text):
        budget = _turn_budget_settings().default_tokens
    if budget is None:
        return config, None, cleaned
    cleaned = strip_budget_markers(text)
    new_max = budget_to_max_iterations(budget, config.max_iterations)
    if new_max <= config.max_iterations:
        return config, budget, cleaned
    return replace(config, max_iterations=new_max), budget, cleaned


def is_budget_command(text: str) -> bool:
    return bool(_BUDGET_CMD_RE.match((text or "").strip()))


def get_budget_continuation_message(budget_tokens: int, *, attempt: int = 1) -> str:
    return (
        f"[系统] 本轮 token 预算约 {budget_tokens:,}，当前进度未达 90%。"
        f"请继续完成用户任务，避免重复已交付内容。（续跑 {attempt}）"
    )


@dataclass
class TurnBudgetState:
    """Track mid-turn token budget continuation (CC query/tokenBudget.ts)."""

    budget_tokens: int
    continuations_used: int = 0
    tokens_at_last_check: int = 0

    def should_continue(
        self,
        output_tokens: int,
        *,
        max_continuations: int = 3,
        min_delta_tokens: int = 500,
    ) -> bool:
        if self.budget_tokens <= 0:
            return False
        if self.continuations_used >= max_continuations:
            if output_tokens - self.tokens_at_last_check < min_delta_tokens:
                return False
        threshold = int(self.budget_tokens * 0.9)
        if output_tokens < threshold:
            return True
        return False

    def record_continuation(self, output_tokens: int) -> None:
        self.continuations_used += 1
        self.tokens_at_last_check = output_tokens


def continuation_limits() -> tuple[int, int]:
    tb = _turn_budget_settings()
    return int(tb.max_continuations), int(tb.min_delta)
