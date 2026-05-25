"""Pre-LLM context pressure routing (OpenClaw preemptive-compaction subset)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

PreemptiveRoute = str  # ok | compact | truncate | overflow_fail


class ContextPrecheckOverflow(RuntimeError):
    """Raised when prompt is too large before LLM call."""

    def __init__(self, message: str, *, estimated: int = 0, threshold: int = 0) -> None:
        super().__init__(message)
        self.estimated_tokens = estimated
        self.threshold_tokens = threshold


@dataclass(frozen=True)
class PreemptiveDecision:
    route: PreemptiveRoute
    estimated_tokens: int
    threshold_tokens: int
    overflow_tokens: int = 0
    message: str = ""


def preemptive_compact_enabled() -> bool:
    return env_truthy("BUTLER_PREEMPTIVE_COMPACT", default=True)


def truncate_buffer_tokens() -> int:
    try:
        return max(256, int(os.getenv("BUTLER_PREEMPTIVE_TRUNCATE_BUFFER", "512")))
    except ValueError:
        return 512


def apply_preemptive_pipeline(
    messages: list[dict],
    *,
    max_context_tokens: int,
    estimate_tokens: Callable[[list[dict]], int],
    compress: Callable[[list[dict]], list[dict]],
    diagnostics: dict[str, Any] | None = None,
    max_output_tokens: int | None = None,
) -> tuple[list[dict], PreemptiveDecision]:
    """Run prune already applied; decide compact / truncate / fail before LLM."""
    from butler.core.context_budget import (
        get_auto_compact_threshold,
        is_auto_compact_enabled,
    )

    if not preemptive_compact_enabled():
        est = estimate_tokens(messages)
        return messages, PreemptiveDecision(
            route="ok",
            estimated_tokens=est,
            threshold_tokens=max_context_tokens,
        )

    estimated = estimate_tokens(messages)
    threshold = get_auto_compact_threshold(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    effective_limit = threshold + truncate_buffer_tokens()

    if diagnostics is not None:
        diagnostics["preemptive_estimated_tokens"] = estimated
        diagnostics["preemptive_threshold_tokens"] = threshold

    if estimated < threshold:
        return messages, PreemptiveDecision(
            route="ok",
            estimated_tokens=estimated,
            threshold_tokens=threshold,
        )

    out = list(messages)
    route: PreemptiveRoute = "compact"
    if is_auto_compact_enabled():
        try:
            out = compress(out)
            estimated = estimate_tokens(out)
            if diagnostics is not None:
                diagnostics["preemptive_compact_applied"] = True
                diagnostics["preemptive_tokens_after_compact"] = estimated
        except Exception as exc:
            logger.warning("Preemptive compact failed: %s", exc)
            if diagnostics is not None:
                diagnostics["preemptive_compact_error"] = str(exc)[:200]

    if estimated < threshold:
        return out, PreemptiveDecision(
            route="compact",
            estimated_tokens=estimated,
            threshold_tokens=threshold,
            message="compacted before LLM",
        )

    out, truncated = _truncate_tool_results_aggressive(out)
    estimated = estimate_tokens(out)
    if diagnostics is not None:
        diagnostics["preemptive_truncate_applied"] = truncated

    if estimated < effective_limit:
        return out, PreemptiveDecision(
            route="truncate",
            estimated_tokens=estimated,
            threshold_tokens=threshold,
            message="tool results truncated before LLM",
        )

    overflow = estimated - effective_limit
    if diagnostics is not None:
        diagnostics["preemptive_overflow_fail"] = True
        diagnostics["loop_transition_reason"] = "preemptive_overflow"
    return out, PreemptiveDecision(
        route="overflow_fail",
        estimated_tokens=estimated,
        threshold_tokens=threshold,
        overflow_tokens=overflow,
        message=(
            f"Context overflow (precheck): ~{estimated} tokens >= "
            f"{effective_limit} effective limit"
        ),
    )


def _truncate_tool_results_aggressive(messages: list[dict]) -> tuple[list[dict], bool]:
    """Shrink tool role message bodies when still over budget."""
    from butler.core.tool_result_storage import BUDGET_TRUNCATED_TAG

    changed = False
    out: list[dict] = []
    max_chars = 1200
    for msg in messages:
        if msg.get("role") != "tool":
            out.append(msg)
            continue
        content = str(msg.get("content") or "")
        if len(content) <= max_chars or BUDGET_TRUNCATED_TAG in content:
            out.append(msg)
            continue
        trimmed = content[:max_chars] + f"\n\n{BUDGET_TRUNCATED_TAG}\n"
        copy = dict(msg)
        copy["content"] = trimmed
        out.append(copy)
        changed = True
    return out, changed
