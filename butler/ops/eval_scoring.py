"""Multi-dimensional scoring functions for Butler evaluation.

Four scoring dimensions:
  1. Intent accuracy  — did Butler understand what the user wanted?
  2. Tool selection   — did Butler pick the right tools?
  3. Response quality — is the output helpful, correct, concise?
  4. Memory effectiveness — S_w / H_1 / E_d metrics

Each scorer takes structured input/output and returns a 0.0-1.0 score.
Designed for use with LangFuse evaluation datasets.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Result of a single scoring dimension."""

    dimension: str
    score: float
    max_score: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)
    comment: str = ""

    @property
    def normalized(self) -> float:
        if self.max_score <= 0:
            return 0.0
        return min(1.0, max(0.0, self.score / self.max_score))


@dataclass
class MultiDimScore:
    """Combined multi-dimensional score."""

    scores: list[ScoreResult] = field(default_factory=list)

    @property
    def overall(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.normalized for s in self.scores) / len(self.scores)

    def by_dimension(self) -> dict[str, float]:
        return {s.dimension: s.normalized for s in self.scores}

    def to_eval_scores(self, trace_id: str = "") -> list[Any]:
        """Convert to EvalScore objects for LangFuse push."""
        from butler.ops.eval_bridge import EvalScore
        result = []
        for s in self.scores:
            result.append(EvalScore(
                name=f"eval.{s.dimension}",
                value=s.normalized,
                comment=s.comment,
                category="multi_dim_eval",
                trace_id=trace_id,
                metadata=s.details,
            ))
        result.append(EvalScore(
            name="eval.overall",
            value=self.overall,
            comment=f"avg of {len(self.scores)} dims",
            category="multi_dim_eval",
            trace_id=trace_id,
        ))
        return result


# ── Dimension 1: Intent Accuracy ──

def score_intent(
    expected_intent: str,
    actual_intent: str = "",
    response_text: str = "",
    intent_keywords: list[str] | None = None,
) -> ScoreResult:
    """Score how well Butler understood the user's intent.

    Scoring:
      - Exact intent match: 1.0
      - Keyword overlap: proportional
      - No match: 0.0
    """
    score = 0.0
    details: dict[str, Any] = {"expected": expected_intent, "actual": actual_intent}

    if expected_intent and actual_intent:
        if expected_intent.lower() == actual_intent.lower():
            score = 1.0
        elif expected_intent.lower() in actual_intent.lower():
            score = 0.8

    if score < 1.0 and intent_keywords:
        text = (response_text or actual_intent or "").lower()
        hits = sum(1 for kw in intent_keywords if kw.lower() in text)
        keyword_score = hits / len(intent_keywords) if intent_keywords else 0.0
        score = max(score, keyword_score)
        details["keyword_hits"] = hits
        details["keyword_total"] = len(intent_keywords)

    return ScoreResult(
        dimension="intent_accuracy",
        score=score,
        details=details,
        comment=f"intent={'match' if score >= 0.8 else 'partial' if score > 0 else 'miss'}",
    )


# ── Dimension 2: Tool Selection ──

def score_tool_selection(
    expected_tools: list[str],
    actual_tools: list[str],
    no_extra_penalty: float = 0.1,
) -> ScoreResult:
    """Score tool selection correctness.

    Scoring:
      - Recall: expected tools that were used
      - Precision penalty: unexpected tools used (small penalty each)
    """
    if not expected_tools and not actual_tools:
        return ScoreResult(
            dimension="tool_selection", score=1.0,
            comment="no tools expected or used",
        )

    if not expected_tools:
        penalty = len(actual_tools) * no_extra_penalty
        return ScoreResult(
            dimension="tool_selection",
            score=max(0.0, 1.0 - penalty),
            details={"unexpected_tools": actual_tools},
            comment=f"no tools expected, {len(actual_tools)} used",
        )

    expected_set = set(t.lower() for t in expected_tools)
    actual_set = set(t.lower() for t in actual_tools)

    hits = expected_set & actual_set
    recall = len(hits) / len(expected_set) if expected_set else 0.0
    extra = actual_set - expected_set
    penalty = len(extra) * no_extra_penalty

    score = max(0.0, recall - penalty)

    return ScoreResult(
        dimension="tool_selection",
        score=score,
        details={
            "expected": sorted(expected_set),
            "actual": sorted(actual_set),
            "matched": sorted(hits),
            "extra": sorted(extra),
            "recall": round(recall, 4),
        },
        comment=f"recall={recall:.0%}, extra={len(extra)}",
    )


# ── Dimension 3: Response Quality ──

def score_response_quality(
    response_text: str,
    expected_contains: list[str] | None = None,
    expected_contains_any: list[str] | None = None,
    max_lines: int = 0,
    no_llm_expected: bool = False,
) -> ScoreResult:
    """Score response quality based on content expectations.

    Sub-scores:
      - contains check: all required substrings present
      - contains_any check: at least one of alternatives present
      - length check: within max_lines if specified
      - coherence: non-empty, not error-only
    """
    if not response_text:
        if no_llm_expected:
            return ScoreResult(
                dimension="response_quality", score=1.0,
                comment="no response expected (command)",
            )
        return ScoreResult(
            dimension="response_quality", score=0.0,
            comment="empty response",
        )

    sub_scores: list[float] = []
    details: dict[str, Any] = {}

    if expected_contains:
        text_lower = response_text.lower()
        hits = sum(1 for kw in expected_contains if kw.lower() in text_lower)
        contains_score = hits / len(expected_contains)
        sub_scores.append(contains_score)
        details["contains_hits"] = hits
        details["contains_total"] = len(expected_contains)
    else:
        sub_scores.append(1.0)

    if expected_contains_any:
        text_lower = response_text.lower()
        any_hit = any(kw.lower() in text_lower for kw in expected_contains_any)
        sub_scores.append(1.0 if any_hit else 0.0)
        details["contains_any_hit"] = any_hit

    if max_lines > 0:
        actual_lines = len(response_text.strip().split("\n"))
        line_ok = actual_lines <= max_lines
        sub_scores.append(1.0 if line_ok else max(0.0, 1.0 - (actual_lines - max_lines) / max_lines))
        details["line_count"] = actual_lines
        details["max_lines"] = max_lines

    coherent = len(response_text.strip()) > 5
    sub_scores.append(1.0 if coherent else 0.3)

    total = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0

    return ScoreResult(
        dimension="response_quality",
        score=total,
        details=details,
        comment=f"quality={total:.0%}",
    )


# ── Dimension 4: Memory Effectiveness ──

def score_memory_effectiveness(
    write_survival_rate: float = 0.0,
    first_turn_hit_rate: float = 0.0,
    decay_error_rate: float = 0.0,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> ScoreResult:
    """Score memory effectiveness from runtime metrics.

    Components:
      - S_w: Write survival rate (higher = better)
      - H_1: First-turn hit rate (higher = better)
      - E_d: Decay error rate (lower = better, inverted)
    """
    w_sw, w_h1, w_ed = weights
    e_d_inverted = max(0.0, 1.0 - decay_error_rate)

    weighted = (
        write_survival_rate * w_sw
        + first_turn_hit_rate * w_h1
        + e_d_inverted * w_ed
    )
    total_weight = sum(weights)
    score = weighted / total_weight if total_weight > 0 else 0.0

    return ScoreResult(
        dimension="memory_effectiveness",
        score=score,
        details={
            "S_w": round(write_survival_rate, 4),
            "H_1": round(first_turn_hit_rate, 4),
            "E_d": round(decay_error_rate, 4),
            "weights": list(weights),
        },
        comment=f"S_w={write_survival_rate:.0%} H_1={first_turn_hit_rate:.0%} E_d={decay_error_rate:.0%}",
    )


# ── Combined scorer ──

def score_turn(
    expected_intent: str = "",
    actual_intent: str = "",
    response_text: str = "",
    intent_keywords: list[str] | None = None,
    expected_tools: list[str] | None = None,
    actual_tools: list[str] | None = None,
    expected_contains: list[str] | None = None,
    expected_contains_any: list[str] | None = None,
    max_lines: int = 0,
    no_llm_expected: bool = False,
    memory_s_w: float = 0.0,
    memory_h_1: float = 0.0,
    memory_e_d: float = 0.0,
    include_memory: bool = False,
) -> MultiDimScore:
    """Score a single turn across all applicable dimensions."""
    result = MultiDimScore()

    result.scores.append(score_intent(
        expected_intent=expected_intent,
        actual_intent=actual_intent,
        response_text=response_text,
        intent_keywords=intent_keywords,
    ))

    result.scores.append(score_tool_selection(
        expected_tools=expected_tools or [],
        actual_tools=actual_tools or [],
    ))

    result.scores.append(score_response_quality(
        response_text=response_text,
        expected_contains=expected_contains,
        expected_contains_any=expected_contains_any,
        max_lines=max_lines,
        no_llm_expected=no_llm_expected,
    ))

    if include_memory:
        result.scores.append(score_memory_effectiveness(
            write_survival_rate=memory_s_w,
            first_turn_hit_rate=memory_h_1,
            decay_error_rate=memory_e_d,
        ))

    return result
