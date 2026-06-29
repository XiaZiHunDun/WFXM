"""Eval-driven bounded transform parameter feedback (MOD-7)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.transform_overrides import apply_transform_override

logger = logging.getLogger(__name__)


def analyse_transform_signals(
    *,
    tcr_rate: float | None = None,
    tool_score: float | None = None,
    memory_score: float | None = None,
    response_score: float | None = None,
    provider: str = "",
) -> list[str]:
    """Apply bounded deltas from eval signals; returns human-readable actions."""
    actions: list[str] = []
    if tcr_rate is not None and tcr_rate < 0.98:
        apply_transform_override(
            "tool_schema_compact",
            {"max_tools": 24},
        )
        actions.append("tcr_low→tool_schema_compact.max_tools=24")
    if tool_score is not None and tool_score < 0.6:
        apply_transform_override(
            "tool_schema_compact",
            {"max_tools": 20},
        )
        actions.append("tool_score_low→max_tools=20")
    if memory_score is not None and memory_score < 0.5:
        apply_transform_override(
            "memory_inject",
            {"enabled": True, "boost": 1},
        )
        actions.append("memory_low→memory_inject boost")
    prov = (provider or "").lower()
    if response_score is not None and response_score < 0.6 and prov in (
        "deepseek",
        "moonshot",
        "zhipu",
        "qwen",
    ):
        apply_transform_override("fc_hint_extra", {"strength": "high"})
        actions.append("response_low→fc_hint_extra strength=high")
    if actions:
        logger.info("transform feedback: %s", "; ".join(actions))
    return actions


def maybe_apply_turn_feedback(turn_eval: dict[str, Any], *, provider: str = "") -> list[str]:
    dims = turn_eval.get("dimensions") or turn_eval
    return analyse_transform_signals(
        tool_score=_float(dims.get("tool_selection")),
        memory_score=_float(dims.get("memory_effectiveness")),
        response_score=_float(dims.get("response_quality")),
        provider=provider,
    )


def _float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
