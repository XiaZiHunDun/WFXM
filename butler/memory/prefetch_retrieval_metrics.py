"""P_r: approximate whether LLM replies reference prefetched memory snippets."""

from __future__ import annotations

import re
from typing import Any

_MIN_TERM_LEN = 4
_MAX_TERMS = 24
_TERM_MAX_CHARS = 80


def extract_prefetch_match_terms(prefetch_text: str) -> list[str]:
    """Pull short phrases from injected prefetch blocks for overlap checks."""
    terms: list[str] = []
    seen: set[str] = set()
    for raw in (prefetch_text or "").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        body = re.sub(r"^\[[^\]]+\]\s*", "", line[2:]).strip()
        if len(body) < _MIN_TERM_LEN:
            continue
        term = body[:_TERM_MAX_CHARS].lower()
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= _MAX_TERMS:
            break
    return terms


def estimate_prefetch_used_count(response: str, terms: list[str]) -> int:
    """Count prefetch terms whose prefix appears in the assistant reply."""
    resp = (response or "").strip().lower()
    if not resp or not terms:
        return 0
    used = 0
    for term in terms:
        needle = term[:40]
        if len(needle) >= _MIN_TERM_LEN and needle in resp:
            used += 1
    return used


def record_prefetch_snippets(diagnostics: dict[str, Any] | None, prefetch_text: str) -> None:
    if diagnostics is None:
        return
    terms = extract_prefetch_match_terms(prefetch_text)
    if terms:
        diagnostics["memory_prefetch_snippets"] = terms


def finalize_prefetch_retrieval_metrics(
    session_key: str,
    response_text: str,
    health: dict[str, Any] | None,
) -> int:
    """Update P_r used_by_llm for the current turn after the model responds."""
    h = health or {}
    total = int(h.get("memory_prefetch_retrieval_total") or 0)
    if total <= 0:
        return 0
    snippets = h.get("memory_prefetch_snippets")
    if not isinstance(snippets, list):
        snippets = []
    used = estimate_prefetch_used_count(response_text, [str(s) for s in snippets])
    used = min(used, total)
    from butler.memory.prefetch_retrieval_metrics_ops import persist_prefetch_retrieval_used_safe

    persist_prefetch_retrieval_used_safe(used, h)
    return used


__all__ = [
    "estimate_prefetch_used_count",
    "extract_prefetch_match_terms",
    "finalize_prefetch_retrieval_metrics",
    "record_prefetch_snippets",
]
