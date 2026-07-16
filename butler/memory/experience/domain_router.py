"""DomainRouter — routes user queries to the most relevant experience domain.

Three-stage routing:
1. Keyword matching (fast, O(1))
2. Semantic matching (accurate, ~50ms)
3. Frequency weighting (adaptive, based on access stats)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from butler.memory.experience.taxonomy import DOMAINS, get_all_domain_keywords

logger = logging.getLogger(__name__)

try:
    from butler.memory.embedding import get_embedder
    _EMBEDDER_AVAILABLE = True
except ImportError:
    _EMBEDDER_AVAILABLE = False
    get_embedder = lambda: None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class DomainRouter:
    def __init__(self, store=None):
        self._store = store
        self._keywords = get_all_domain_keywords()
        self._domain_hits: dict[str, int] = {did: 0 for did in DOMAINS}
        self._embedder = get_embedder() if _EMBEDDER_AVAILABLE else None
        self._domain_embeddings: dict[str, list[float]] = {}
        self._precompute_domain_embeddings()

    def _precompute_domain_embeddings(self) -> None:
        if not self._embedder:
            return
        try:
            for domain_id, domain_info in DOMAINS.items():
                text = f"{domain_info['name']} {domain_info['description']} {' '.join(domain_info['keywords'])}"
                embedding = self._embedder.embed(text)
                self._domain_embeddings[domain_id] = embedding
        except Exception as e:
            logger.debug("Failed to precompute domain embeddings: %s", e)

    def _semantic_match(self, query: str) -> dict[str, float]:
        if not self._embedder or not self._domain_embeddings:
            return {}
        try:
            query_embedding = self._embedder.embed(query)
            scores = {}
            for domain_id, domain_embedding in self._domain_embeddings.items():
                sim = cosine_similarity(query_embedding, domain_embedding)
                if sim > 0.3:
                    scores[domain_id] = sim
            return scores
        except Exception as e:
            logger.debug("Semantic matching failed: %s", e)
            return {}

    def route(self, query: str) -> tuple[str, float]:
        """Route a query to a domain. Returns (domain_id, confidence).

        Routing strategy:
        1. Keyword match → fast path, confidence based on match ratio
        2. If no keyword hit, return default domain with low confidence
        3. Frequency weighting adjusts confidence based on historical hits
        """
        q = (query or "").strip().lower()
        if not q:
            return "daily_life", 0.0

        scores: dict[str, float] = {}

        # Stage 1: Keyword matching (longer keywords get priority)
        for domain_id, keywords in self._keywords.items():
            score = 0.0
            matched_kws = 0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in q:
                    matched_kws += 1
                    kw_len = len(kw_lower)
                    q_len = len(q)
                    if kw_len >= 8:
                        score += 0.4
                    elif kw_len >= 4:
                        score += 0.2
                    else:
                        score += 0.05
                    score += kw_len / q_len * 0.5
            if score > 0:
                scores[domain_id] = score

        # Stage 2: Frequency weighting
        total_hits = sum(self._domain_hits.values()) or 1
        for domain_id in scores:
            freq_weight = self._domain_hits.get(domain_id, 0) / total_hits
            scores[domain_id] *= (1.0 + freq_weight * 0.3)

        # Stage 3: Semantic matching (if keyword matching is weak)
        if not scores or max(scores.values()) < 0.2:
            semantic_scores = self._semantic_match(q)
            for domain_id, sem_score in semantic_scores.items():
                scores[domain_id] = scores.get(domain_id, 0) + sem_score * 0.8

        if not scores:
            return "daily_life", 0.1

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_domain, best_score = ranked[0]

        # Normalize confidence to [0, 1]
        max_possible = min(len(self._keywords), 13) * 0.5
        confidence = min(best_score / max_possible, 1.0)

        # If second-best is close, reduce confidence
        if len(ranked) > 1:
            second_score = ranked[1][1]
            if second_score / max(best_score, 1e-6) > 0.7:
                confidence *= 0.8

        return best_domain, round(confidence, 4)

    def route_multi(self, query: str, top_n: int = 2) -> list[tuple[str, float]]:
        """Route to multiple candidate domains. Returns [(domain_id, confidence), ...]."""
        q = (query or "").strip().lower()
        if not q:
            return [("daily_life", 0.0)]

        scores: dict[str, float] = {}

        for domain_id, keywords in self._keywords.items():
            score = 0.0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in q:
                    kw_len = len(kw_lower)
                    q_len = len(q)
                    if kw_len >= 8:
                        score += 0.4
                    elif kw_len >= 4:
                        score += 0.2
                    else:
                        score += 0.05
                    score += kw_len / q_len * 0.5
            if score > 0:
                scores[domain_id] = score

        if not scores or max(scores.values()) < 0.2:
            semantic_scores = self._semantic_match(q)
            for domain_id, sem_score in semantic_scores.items():
                scores[domain_id] = scores.get(domain_id, 0) + sem_score * 0.8

        total_hits = sum(self._domain_hits.values()) or 1
        for domain_id in scores:
            freq_weight = self._domain_hits.get(domain_id, 0) / total_hits
            scores[domain_id] *= (1.0 + freq_weight * 0.3)

        if not scores:
            return [("daily_life", 0.1)]

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        max_possible = min(len(self._keywords), 13) * 0.5
        result = []
        for domain_id, score in ranked[:top_n]:
            confidence = min(score / max_possible, 1.0)
            result.append((domain_id, round(confidence, 4)))
        return result

    def record_hit(self, domain_id: str) -> None:
        """Record that a domain was successfully used."""
        if domain_id in self._domain_hits:
            self._domain_hits[domain_id] += 1

    def get_domain_stats(self) -> dict[str, int]:
        """Return hit counts per domain."""
        return dict(self._domain_hits)

    def reset_stats(self) -> None:
        """Reset frequency stats (for testing)."""
        self._domain_hits = {did: 0 for did in DOMAINS}
