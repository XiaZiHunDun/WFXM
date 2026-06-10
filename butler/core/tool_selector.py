"""Shrink tool schemas when count exceeds threshold (semantic + keyword scoring)."""

from __future__ import annotations

import hashlib
import os
import re
from collections import OrderedDict

from butler.env_parse import env_truthy, int_env
import logging

logger = logging.getLogger(__name__)

_CORE_TOOLS = frozenset({
    "read_file",
    "search_files",
    "list_directory",
    "delegate_task",
    "butler_recall",
    "search_transcript",
    "run_workflow",
    "memo_add",
    "contact_add",
    "expense_add",
    "habit_create",
    "set_reminder",
    "butler_remember",
})

_TOOL_EMBED_CACHE_MAX = 256
_tool_embed_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_embedder_instance = None
_embedder_resolved = False


def _tool_embed_cache_key(name: str, text: str) -> str:
    """Stable cache key (Sprint 13 PERF-13-1).

    blake2b is deterministic across processes; builtin hash() is not
    (PYTHONHASHSEED). 16 hex chars ≈ 64 bits, ample for cache key.
    """
    h = hashlib.blake2b(f"{name}\x00{text}".encode("utf-8")).hexdigest()[:16]
    return f"tool:{name}:{h}"


def tool_selector_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_SELECTOR", default=True)


def tool_selector_threshold() -> int:
    try:
        return int_env("BUTLER_TOOL_SELECTOR_THRESHOLD", 12, min=4, max=40)
    except ValueError:
        return 12


def _tool_name(defn: dict) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def _tool_text(defn: dict) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    parts = [str(fn.get("name") or ""), str(fn.get("description") or "")]
    return " ".join(parts).lower()


def _get_semantic_embedder():
    """Lazy-init embedder for tool semantic scoring (only if non-hashing)."""
    global _embedder_instance, _embedder_resolved
    if _embedder_resolved:
        return _embedder_instance
    _embedder_resolved = True
    if not env_truthy("BUTLER_TOOL_SEMANTIC_SELECT", default=True):
        return None
    try:
        from butler.memory.embedding import get_embedder

        emb = get_embedder()
        if emb.model_id.startswith("hashing"):
            return None
        _embedder_instance = emb
        return emb
    except Exception:
        return None


def _semantic_score(defn: dict, query_vec: list[float], embedder: object) -> float:
    """Compute semantic similarity between tool description and user query."""
    text = _tool_text(defn)
    name = _tool_name(defn)
    cache_key = _tool_embed_cache_key(name, text)
    if cache_key in _tool_embed_cache:
        tool_vec = _tool_embed_cache[cache_key]
        _tool_embed_cache.move_to_end(cache_key)
    else:
        try:
            tool_vec = embedder.embed(text)  # type: ignore[union-attr]
        except Exception:
            return 0.0
        _tool_embed_cache[cache_key] = tool_vec
        _tool_embed_cache.move_to_end(cache_key)
        if len(_tool_embed_cache) > _TOOL_EMBED_CACHE_MAX:
            _tool_embed_cache.popitem(last=False)
    from butler.memory.embedding import cosine_similarity

    return max(0.0, cosine_similarity(query_vec, tool_vec))


def _score_tool(defn: dict, *, keywords: set[str]) -> int:
    if not keywords:
        return 0
    text = _tool_text(defn)
    score = 0
    for kw in keywords:
        if kw in text:
            score += 2
        if kw in _tool_name(defn):
            score += 3
    return score


def _keywords_from_context(*, user_hint: str = "", role: str = "") -> set[str]:
    blob = f"{user_hint} {role}".lower()
    return {w for w in re.split(r"[^\w\u4e00-\u9fff]+", blob) if len(w) >= 2}


def select_tools_for_context(
    tools: list[dict],
    *,
    user_hint: str = "",
    role: str = "",
    threshold: int | None = None,
    skill_preferred_tools: set[str] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Return (selected_tools, diagnostics).

    skill_preferred_tools: tool names from matched skills that should be
    preserved even if keyword/semantic scores are low.
    """
    diag: dict[str, int] = {
        "tool_selector_input": len(tools),
        "tool_selector_output": len(tools),
    }
    if not tool_selector_enabled() or not tools:
        return list(tools), diag

    pinned = _CORE_TOOLS | (skill_preferred_tools or set())

    cap = threshold if threshold is not None else tool_selector_threshold()

    try:
        from butler.core.tool_recall_bm25 import (
            select_tools_with_bm25,
            tool_recall_bm25_enabled,
        )

        if tool_recall_bm25_enabled() and len(tools) > cap:
            return select_tools_with_bm25(tools, user_hint=user_hint or role, top_k=cap)
    except Exception as exc:
        logger.debug("select tools for context skipped: %s", exc)
    if len(tools) <= cap:
        return list(tools), diag

    keywords = _keywords_from_context(user_hint=user_hint, role=role)

    embedder = _get_semantic_embedder()
    query_vec: list[float] = []
    if embedder and user_hint:
        try:
            query_vec = embedder.embed(user_hint)
        except Exception:
            query_vec = []

    ranked: list[tuple[int, int, dict]] = []
    for idx, defn in enumerate(tools):
        name = _tool_name(defn)
        base = 100 if name in pinned else 0
        kw_score = _score_tool(defn, keywords=keywords)

        sem_boost = 0
        if query_vec and embedder:
            sem = _semantic_score(defn, query_vec, embedder)
            if sem > 0.3:
                sem_boost = int(sem * 10)

        ranked.append((base + kw_score + sem_boost, idx, defn))

    ranked.sort(key=lambda t: (-t[0], t[1]))
    chosen: list[dict] = []
    seen: set[str] = set()
    for _, _, defn in ranked:
        name = _tool_name(defn)
        if name in seen:
            continue
        chosen.append(defn)
        seen.add(name)
        if len(chosen) >= cap:
            break

    for _, _, defn in ranked:
        name = _tool_name(defn)
        if name in pinned and name not in seen:
            chosen.append(defn)
            seen.add(name)

    diag["tool_selector_output"] = len(chosen)
    diag["tool_selector_dropped"] = max(0, len(tools) - len(chosen))
    return chosen, diag
