"""P3-1: Evaluation feedback loop — read scores back from LangFuse and generate
optimisation suggestions (the "backpropagation" link).

This module closes the loop: eval_bridge writes scores *to* LangFuse;
eval_feedback reads them *back* and synthesises actionable suggestions
that the agent loop can incorporate into its context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

logger = logging.getLogger(__name__)


@dataclass
class ScoreSnapshot:
    """A single score observation read from LangFuse."""

    name: str
    value: float
    comment: str = ""
    trace_id: str = ""
    timestamp: float = 0.0


@dataclass
class FeedbackSuggestion:
    """An actionable optimisation suggestion derived from score analysis."""

    category: str  # "quality", "performance", "reliability", "experience"
    severity: str  # "critical", "warning", "info"
    message: str
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0


@dataclass
class FeedbackReport:
    """Result of analysing recent evaluation scores."""

    scores: list[ScoreSnapshot] = field(default_factory=list)
    suggestions: list[FeedbackSuggestion] = field(default_factory=list)
    period_seconds: float = 0.0
    source: str = "langfuse"

    @property
    def has_critical(self) -> bool:
        return any(s.severity == "critical" for s in self.suggestions)

    @property
    def summary(self) -> str:
        if not self.suggestions:
            return "No optimisation suggestions (all metrics within thresholds)."
        parts = []
        for s in self.suggestions:
            parts.append(f"[{s.severity.upper()}] {s.category}: {s.message}")
        return "\n".join(parts)

    def as_context_injection(self) -> str:
        """Format suggestions as a compact context string for agent loop injection."""
        if not self.suggestions:
            return ""
        lines = ["[Eval Feedback]"]
        for s in self.suggestions:
            lines.append(f"- {s.message}")
        return "\n".join(lines)


# ── Thresholds ──

_SCORE_THRESHOLDS: dict[str, tuple[float, str, str]] = {
    "intent_accuracy": (0.7, "critical", "quality"),
    "tool_selection": (0.6, "warning", "reliability"),
    "delegate_routing": (0.6, "warning", "reliability"),
    "response_quality": (0.5, "warning", "quality"),
    "memory_effectiveness": (0.5, "warning", "performance"),
    "dev_benchmark.pass_rate": (0.7, "critical", "quality"),
    "memory_benchmark.pass_rate": (0.6, "warning", "performance"),
    "llm_benchmark.pass_rate": (1.0, "warning", "quality"),
}

_SUGGESTIONS_MAP: dict[str, str] = {
    "intent_accuracy": "Intent accuracy below threshold — review prompt templates and routing logic.",
    "tool_selection": "Tool selection degraded — check if dev tasks should use delegate_task instead of terminal.",
    "delegate_routing": "Delegate routing degraded — dev-like turns may be using terminal/write_file directly.",
    "response_quality": "Response quality dropping — review system prompt and context assembly.",
    "memory_effectiveness": "Memory recall declining — check embedding quality and retrieval ranking.",
    "dev_benchmark.pass_rate": "DevEngine benchmark pass rate low — review coding knowledge checkers.",
    "memory_benchmark.pass_rate": "Memory benchmark pass rate low — review vector store and decay params.",
    "llm_benchmark.pass_rate": "B9 LLM delegate benchmark low — review delegate fix path or run oracle gate.",
}


def read_recent_scores(
    lookback_hours: float = 24.0,
    limit: int = 100,
) -> list[ScoreSnapshot]:
    """Read recent evaluation scores from LangFuse.

    Falls back to an empty list if LangFuse is unavailable.
    """
    from butler.ops.eval_feedback_ops import read_langfuse_scores_safe

    return cast(
        list[ScoreSnapshot],
        read_langfuse_scores_safe(
        lookback_hours=lookback_hours,
        limit=limit,
        snapshot_factory=ScoreSnapshot,
        ),
    )


def analyse_scores(
    scores: list[ScoreSnapshot] | None = None,
    lookback_hours: float = 24.0,
) -> FeedbackReport:
    """Analyse recent scores and generate optimisation suggestions.

    If scores is None, reads from LangFuse automatically.
    """
    if scores is None:
        scores = read_recent_scores(lookback_hours=lookback_hours)

    report = FeedbackReport(
        scores=scores,
        period_seconds=lookback_hours * 3600,
    )

    if not scores:
        return report

    averages: dict[str, list[float]] = {}
    for s in scores:
        averages.setdefault(s.name, []).append(s.value)

    for metric_name, values in averages.items():
        avg = sum(values) / len(values)
        threshold_info = _SCORE_THRESHOLDS.get(metric_name)
        if threshold_info is None:
            continue
        threshold, severity, category = threshold_info
        if avg < threshold:
            message = _SUGGESTIONS_MAP.get(
                metric_name,
                f"Metric '{metric_name}' avg={avg:.2f} below threshold {threshold:.2f}",
            )
            report.suggestions.append(FeedbackSuggestion(
                category=category,
                severity=severity,
                message=message,
                metric_name=metric_name,
                metric_value=round(avg, 3),
                threshold=threshold,
            ))

    return report


def get_feedback_context(lookback_hours: float = 24.0) -> str:
    """Convenience: read scores, analyse, return context injection string.

    Returns empty string if no actionable feedback.
    """
    from butler.ops.eval_feedback_ops import build_feedback_context_safe

    return cast(
        str,
        build_feedback_context_safe(
        lookback_hours=lookback_hours,
        analyse_fn=analyse_scores,
        ),
    )
