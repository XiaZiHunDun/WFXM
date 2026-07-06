"""Decay and access-frequency boost for memory retrieval scores.

Smart forget: memory types get differentiated half-lives.
  - permanent (birthdays, identity, preferences): no decay (half_life = inf)
  - experience / note: standard decay (configurable)
  - conversation / ephemeral: fast decay (half_life / 3)
"""

from __future__ import annotations

import math
import time

from butler.memory_settings import resolve_memory_config
from typing import Any, cast


MEMORY_TYPE_HALF_LIFE_MULTIPLIER: dict[str, float] = {
    "profile": float("inf"),
    "birthday": float("inf"),
    "identity": float("inf"),
    "preference": float("inf"),
    "permanent": float("inf"),
    "experience": 1.0,
    "note": 1.0,
    "fact": 1.2,
    "skill": 1.5,
    "conversation": 0.33,
    "ephemeral": 0.25,
}


def memory_half_life_days() -> float:
    base = resolve_memory_config().half_life_days
    from butler.memory.retrieval_ranking_ops import effective_memory_half_life_days_safe

    adjusted = effective_memory_half_life_days_safe(base)
    return float(adjusted) if adjusted is not None else float(base)


def memory_access_boost() -> float:
    return float(resolve_memory_config().access_boost)


def type_adjusted_half_life(base_half_life: float, memory_type: str = "") -> float:
    """Return a type-adjusted half-life. Permanent types get infinity (no decay)."""
    multiplier = MEMORY_TYPE_HALF_LIFE_MULTIPLIER.get(
        memory_type.lower().strip(), 1.0
    )
    if multiplier == float("inf"):
        return float("inf")
    return max(1.0, base_half_life * multiplier)


def decay_factor(age_days: float, *, half_life_days: float) -> float:
    if age_days <= 0 or half_life_days == float("inf"):
        return 1.0
    return math.exp(-math.log(2) * age_days / max(1.0, half_life_days))


def access_boost_factor(access_count: int, *, boost: float) -> float:
    return 1.0 + boost * math.log1p(max(0, int(access_count)))


DECAY_KILL_THRESHOLD = 0.05


def rerank_memory_hits(
    hits: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Apply Ebbinghaus-style decay and access boost; preserve original score as base_score.

    Smart forget: uses type-differentiated half-lives so permanent memory types
    (profile, birthday, preference) never decay, while ephemeral types decay faster.

    D2-6: tracks decay-killed items (rank_score < DECAY_KILL_THRESHOLD) and
    reports to MemoryMetricsCollector for E_d monitoring.
    """
    ts = now if now is not None else time.time()
    base_half = memory_half_life_days()
    boost = memory_access_boost()
    scored: list[tuple[float, dict[str, Any]]] = []
    killed = 0
    for hit in hits:
        item = dict(hit)
        base = float(item.get("score") or 0.5)
        item["base_score"] = base
        created = float(item.get("created_at") or item.get("updated_at") or ts)
        age_days = max(0.0, (ts - created) / 86400.0)
        acc = int(item.get("access_count") or 0)
        mem_type = str(item.get("memory_type") or item.get("type") or item.get("category") or "")
        half = type_adjusted_half_life(base_half, mem_type)
        rank = base * decay_factor(age_days, half_life_days=half) * access_boost_factor(
            acc, boost=boost
        )
        item["rank_score"] = round(rank, 6)
        if rank < DECAY_KILL_THRESHOLD and base >= 0.3:
            killed += 1
            item["decay_killed"] = True
        scored.append((rank, item))
    scored.sort(key=lambda x: x[0], reverse=True)

    if hits:
        from butler.memory.retrieval_ranking_ops import record_decay_evaluation_safe

        record_decay_evaluation_safe(total_important=len(hits), killed=killed)

    return [item for _, item in scored]
