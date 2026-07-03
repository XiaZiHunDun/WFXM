"""Tool selector best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def get_semantic_embedder_safe() -> Any | None:
    def _run() -> Any:
        from butler.memory.embedding import get_embedder

        emb = get_embedder()
        if emb.model_id.startswith("hashing"):
            return None
        return emb

    return safe_best_effort(_run, label="tool_selector.embedder", default=None)


def embed_text_safe(embedder: Any, text: str) -> list[float]:
    def _run() -> list[float]:
        vec = embedder.embed(text)
        return list(vec) if vec is not None else []

    result = safe_best_effort(_run, label="tool_selector.embed_text", default=[])
    return result if isinstance(result, list) else []


def select_tools_bm25_safe(
    tools: list[dict],
    *,
    user_hint: str,
    cap: int,
) -> tuple[list[dict], dict[str, int]] | None:
    def _run() -> tuple[list[dict], dict[str, int]]:
        from butler.core.tool_recall_bm25 import select_tools_with_bm25

        selected = select_tools_with_bm25(tools, user_hint=user_hint, top_k=cap)
        return selected, {
            "tool_selector_input": len(tools),
            "tool_selector_output": len(selected),
        }

    result = safe_best_effort(_run, label="tool_selector.bm25", default=None)
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return None
