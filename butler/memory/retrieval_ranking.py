"""Decay and access-frequency boost for memory retrieval scores."""

from __future__ import annotations

import math
import os
import time
from typing import Any


def memory_half_life_days() -> float:
    try:
        return max(1.0, float(os.getenv("BUTLER_MEMORY_HALF_LIFE_DAYS", "30").strip() or "30"))
    except ValueError:
        return 30.0


def memory_access_boost() -> float:
    try:
        return max(0.0, float(os.getenv("BUTLER_MEMORY_ACCESS_BOOST", "0.12").strip() or "0.12"))
    except ValueError:
        return 0.12


def decay_factor(age_days: float, *, half_life_days: float) -> float:
    if age_days <= 0:
        return 1.0
    return math.exp(-math.log(2) * age_days / max(1.0, half_life_days))


def access_boost_factor(access_count: int, *, boost: float) -> float:
    return 1.0 + boost * math.log1p(max(0, int(access_count)))


def rerank_memory_hits(
    hits: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Apply Ebbinghaus-style decay and access boost; preserve original score as base_score."""
    ts = now if now is not None else time.time()
    half = memory_half_life_days()
    boost = memory_access_boost()
    scored: list[tuple[float, dict[str, Any]]] = []
    for hit in hits:
        item = dict(hit)
        base = float(item.get("score") or 0.5)
        item["base_score"] = base
        created = float(item.get("created_at") or item.get("updated_at") or ts)
        age_days = max(0.0, (ts - created) / 86400.0)
        acc = int(item.get("access_count") or 0)
        rank = base * decay_factor(age_days, half_life_days=half) * access_boost_factor(
            acc, boost=boost
        )
        item["rank_score"] = round(rank, 6)
        scored.append((rank, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]
