"""Skill similarity LLM tier helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from butler.skills.similarity import SimilarityLLMUnavailable

logger = logging.getLogger(__name__)

LLMFn = Callable[[str], str]


def _safe_unavailable_reason(exc: BaseException) -> str:
    name = type(exc).__name__
    raw = str(exc) or ""
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in " ._-")[:80]
    return f"{name}: {safe}".strip(" :.") or name


def call_llm_similarity_safe(llm_fn: LLMFn, prompt: str) -> str:
    try:
        return llm_fn(prompt).strip()
    except Exception as exc:
        logger.warning("LLM similarity unavailable: %s", exc)
        raise SimilarityLLMUnavailable(_safe_unavailable_reason(exc)) from exc
