"""Iteration and token budget wrap-up nudges (browser-use 75% subset)."""

from __future__ import annotations

import os
from typing import Any

from butler.env_parse import env_truthy, float_env


def loop_budget_nudge_enabled() -> bool:
    return bool(env_truthy("BUTLER_LOOP_BUDGET_NUDGE", default=True))


def loop_budget_warn_ratio() -> float:
    return float(float_env(
        "BUTLER_LOOP_BUDGET_WARN_RATIO",
        0.75,
        min=0.5,
        max=0.95,
        warn_on_clamp=True,
    ))


def iteration_budget_nudge_message(*, iteration: int, max_iterations: int) -> str:
    ratio = loop_budget_warn_ratio()
    pct = int(ratio * 100)
    return (
        f"[系统] 本轮已用约 {iteration}/{max_iterations} 次迭代（≥{pct}% 上限）。"
        "请优先收尾：给出结论、未完成项标为 IN-PROGRESS、避免重复工具调用。"
    )


def token_budget_wrap_nudge_message(*, used_tokens: int, budget_tokens: int) -> str:
    ratio = loop_budget_warn_ratio()
    pct = int(ratio * 100)
    return (
        f"[系统] 本轮 token 已用约 {used_tokens:,}/{budget_tokens:,}（≥{pct}% 预算）。"
        "请收敛范围并交付可验证结果；勿再展开新子任务。"
    )


def should_nudge_iteration_budget(iteration: int, max_iterations: int) -> bool:
    if not loop_budget_nudge_enabled():
        return False
    cap = max(1, int(max_iterations))
    it = max(1, int(iteration))
    threshold = max(1, int(cap * loop_budget_warn_ratio()))
    return it >= threshold


def should_nudge_token_budget(used_tokens: int, budget_tokens: int) -> bool:
    if not loop_budget_nudge_enabled() or budget_tokens <= 0:
        return False
    threshold = int(budget_tokens * loop_budget_warn_ratio())
    return int(used_tokens) >= threshold


def maybe_inject_loop_budget_nudges(
    messages: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    *,
    iteration: int,
    max_iterations: int,
    total_tokens: int = 0,
    budget_tokens: int | None = None,
) -> bool:
    """
    Append at most one iteration nudge and one token nudge per turn (diagnostics flags).
    Returns True if any nudge was injected.
    """
    if not loop_budget_nudge_enabled():
        return False
    injected = False
    if (
        not diagnostics.get("loop_iteration_budget_nudge")
        and should_nudge_iteration_budget(iteration, max_iterations)
    ):
        messages.append(
            {
                "role": "user",
                "content": iteration_budget_nudge_message(
                    iteration=iteration,
                    max_iterations=max_iterations,
                ),
            }
        )
        diagnostics["loop_iteration_budget_nudge"] = True
        injected = True
    if (
        budget_tokens
        and not diagnostics.get("loop_token_budget_nudge")
        and should_nudge_token_budget(total_tokens, int(budget_tokens))
    ):
        messages.append(
            {
                "role": "user",
                "content": token_budget_wrap_nudge_message(
                    used_tokens=int(total_tokens),
                    budget_tokens=int(budget_tokens),
                ),
            }
        )
        diagnostics["loop_token_budget_nudge"] = True
        injected = True
    return injected


__all__ = [
    "iteration_budget_nudge_message",
    "loop_budget_nudge_enabled",
    "loop_budget_warn_ratio",
    "maybe_inject_loop_budget_nudges",
    "should_nudge_iteration_budget",
    "should_nudge_token_budget",
    "token_budget_wrap_nudge_message",
]
