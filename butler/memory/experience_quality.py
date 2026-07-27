"""Experience quality scoring and pruning mechanism.

Provides:
1. Experience scoring based on usage and success rate
2. Experience pruning (淘汰) based on age, low score, and replacement
3. Quality metrics for experience library
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MIN_SUCCESS_RATE = 0.3
DEFAULT_MIN_HIT_COUNT = 3


@dataclass
class ExperienceScore:
    """Score for an experience entry."""

    experience_id: str
    success_rate: float = 0.0
    hit_count: int = 0
    age_days: float = 0.0
    recency_bonus: float = 0.0
    total_score: float = 0.0
    should_prune: bool = False
    prune_reason: str = ""


def calculate_experience_score(
    experience_id: str,
    hit_count: int,
    success_count: int,
    fail_count: int,
    created_at: float,
    last_used_at: float,
    *,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
    min_hit_count: int = DEFAULT_MIN_HIT_COUNT,
) -> ExperienceScore:
    """Calculate quality score for an experience.

    Scoring formula:
    - success_rate = success_count / max(1, hit_count)
    - age_days = (now - created_at) / 86400
    - recency_bonus = 1.0 if used within 7 days, else decays
    - total_score = success_rate * 40 + min(hit_count/10, 1.0) * 30 + recency_bonus * 30

    Pruning conditions:
    - age > max_age_days AND hit_count < min_hit_count
    - success_rate < min_success_rate AND hit_count >= min_hit_count
    """
    now = time.time()
    age_days = (now - created_at) / 86400.0
    days_since_use = (now - last_used_at) / 86400.0

    if hit_count > 0:
        success_rate = success_count / hit_count
    else:
        success_rate = 0.0

    if days_since_use < 1:
        recency_bonus = 1.0
    elif days_since_use < 7:
        recency_bonus = 0.8
    elif days_since_use < 30:
        recency_bonus = 0.5
    else:
        recency_bonus = 0.2

    hit_score = min(hit_count / 10.0, 1.0)
    total_score = success_rate * 40 + hit_score * 30 + recency_bonus * 30

    score = ExperienceScore(
        experience_id=experience_id,
        success_rate=success_rate,
        hit_count=hit_count,
        age_days=age_days,
        recency_bonus=recency_bonus,
        total_score=total_score,
    )

    if age_days > max_age_days and hit_count < min_hit_count:
        score.should_prune = True
        score.prune_reason = f"age={age_days:.0f}d, low_hits={hit_count}"
    elif hit_count >= min_hit_count and success_rate < min_success_rate:
        score.should_prune = True
        score.prune_reason = f"low_success_rate={success_rate:.2f}"

    return score


def score_experiences(
    experiences: List[Dict[str, Any]],
    **kwargs,
) -> List[ExperienceScore]:
    """Score multiple experiences."""
    results: List[ExperienceScore] = []

    for exp in experiences:
        exp_id = exp.get("id", "")
        hit_count = exp.get("hit_count", 0)
        success_count = exp.get("success_count", 0)
        fail_count = exp.get("fail_count", 0)
        created_at = exp.get("created_at", time.time())
        last_used_at = exp.get("last_used", time.time())

        score = calculate_experience_score(
            experience_id=exp_id,
            hit_count=hit_count,
            success_count=success_count,
            fail_count=fail_count,
            created_at=created_at,
            last_used_at=last_used_at,
            **kwargs,
        )
        results.append(score)

    return results


def get_experiences_to_prune(
    scores: List[ExperienceScore],
) -> List[str]:
    """Get list of experience IDs to prune."""
    return [s.experience_id for s in scores if s.should_prune]


def get_quality_metrics(
    scores: List[ExperienceScore],
) -> Dict[str, Any]:
    """Get aggregate quality metrics for experiences."""
    if not scores:
        return {
            "total": 0,
            "avg_score": 0.0,
            "avg_success_rate": 0.0,
            "avg_hit_count": 0.0,
            "prune_count": 0,
            "prune_ratio": 0.0,
        }

    total = len(scores)
    avg_score = sum(s.total_score for s in scores) / total
    avg_success_rate = sum(s.success_rate for s in scores) / total
    avg_hit_count = sum(s.hit_count for s in scores) / total
    prune_count = sum(1 for s in scores if s.should_prune)

    return {
        "total": total,
        "avg_score": round(avg_score, 2),
        "avg_success_rate": round(avg_success_rate, 3),
        "avg_hit_count": round(avg_hit_count, 1),
        "prune_count": prune_count,
        "prune_ratio": round(prune_count / total, 3) if total > 0 else 0.0,
    }


__all__ = [
    "ExperienceScore",
    "calculate_experience_score",
    "score_experiences",
    "get_experiences_to_prune",
    "get_quality_metrics",
]