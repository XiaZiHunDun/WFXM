"""Builtin tool orthogonality lint — warn on overlapping descriptions within toolsets."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Builtin search tools intentionally overlap MCP scrape/fetch (layered fallback).
_BENIGN_SEARCH_TOOLS = frozenset({"web_search", "web_fetch"})


def _tool_name(defn: dict[str, Any]) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def _tool_description(defn: dict[str, Any]) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    return str(fn.get("description") or "").strip().lower()


def _tool_text(defn: dict[str, Any]) -> str:
    """Embedding text for orthogonality: description only (names are fixed API)."""
    return _tool_description(defn)


def _toolset_for(name: str) -> str:
    try:
        from butler.tools.registry import _REGISTRY

        entry = _REGISTRY.get(name)
        if entry is not None:
            return str(entry.toolset or "default")
    except Exception:
        pass
    if name.startswith("mcp_"):
        parts = name.split("_", 2)
        if len(parts) >= 2:
            return f"mcp:{parts[1]}"
    return "default"


def _is_benign_overlap(name_a: str, name_b: str) -> bool:
    """Suppress expected builtin↔MCP search/scrape redundancy in /诊断."""
    a = str(name_a or "").lower()
    b = str(name_b or "").lower()
    names = {a, b}
    if names & _BENIGN_SEARCH_TOOLS:
        for n in names - _BENIGN_SEARCH_TOOLS:
            if "firecrawl" in n or n.startswith("mcp_fetch"):
                return True
    return False


def _canonical_pair(name_a: str, name_b: str) -> tuple[str, str]:
    return tuple(sorted((name_a, name_b)))


def _collect_tool_vectors(
    defs: list[dict[str, Any]],
    embedder: Any,
) -> list[tuple[str, str, list[float]]]:
    out: list[tuple[str, str, list[float]]] = []
    for defn in defs:
        name = _tool_name(defn)
        if not name:
            continue
        ts = _toolset_for(name)
        try:
            vec = embedder.embed(_tool_text(defn))
        except Exception as exc:
            logger.debug("orthogonality embed skipped for %s: %s", name, exc)
            continue
        out.append((name, ts, vec))
    return out


def _lint_tool_vectors(
    items: list[tuple[str, str, list[float]]],
    *,
    threshold: float,
    max_pairs: int,
    cross_toolset: bool,
) -> list[str]:
    from butler.memory.embedding import cosine_similarity

    issues: list[tuple[float, str]] = []
    seen: set[tuple[str, str]] = set()
    for i in range(len(items)):
        n1, ts1, v1 = items[i]
        for j in range(i + 1, len(items)):
            n2, ts2, v2 = items[j]
            if not cross_toolset and ts1 != ts2:
                continue
            pair = _canonical_pair(n1, n2)
            if pair in seen:
                continue
            if _is_benign_overlap(n1, n2):
                continue
            sim = cosine_similarity(v1, v2)
            if sim >= threshold:
                seen.add(pair)
                scope = "cross" if ts1 != ts2 else ts1
                issues.append(
                    (
                        sim,
                        f"{scope}: {n1} ↔ {n2} cosine={sim:.3f} (≥{threshold})",
                    )
                )
    issues.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in issues[:max_pairs]]


def lint_builtin_tool_orthogonality(
    *,
    threshold: float = 0.82,
    max_pairs: int = 12,
) -> list[str]:
    """Return warning lines for semantically overlapping builtin tools."""
    from butler.tools.registry import get_tool_definitions

    try:
        from butler.memory.embedding import cosine_similarity, get_embedder
    except Exception as exc:
        return [f"orthogonality lint skipped: embedder unavailable ({exc})"]

    embedder = get_embedder()
    if embedder.model_id.startswith("hashing"):
        return ["orthogonality lint skipped: hashing embedder (set real embedding model)"]

    defs = get_tool_definitions()
    items = _collect_tool_vectors(defs, embedder)
    return _lint_tool_vectors(items, threshold=threshold, max_pairs=max_pairs, cross_toolset=False)


def lint_tool_orthogonality_for_diagnostics(
    *,
    session_key: str = "",
    threshold: float = 0.82,
    max_pairs: int = 2,
) -> list[str]:
    """Builtin + MCP overlap warnings for /诊断 (deduped, noise-reduced)."""
    try:
        from butler.memory.embedding import cosine_similarity, get_embedder
    except Exception as exc:
        logger.debug("diagnostic orthogonality skipped: %s", exc)
        return []

    embedder = get_embedder()
    if embedder.model_id.startswith("hashing"):
        return []

    defs: list[dict[str, Any]] = []
    try:
        from butler.tools.registry import get_tool_definitions

        defs.extend(get_tool_definitions())
    except Exception as exc:
        logger.debug("builtin defs for orthogonality skipped: %s", exc)

    try:
        from butler.mcp.config import mcp_enabled
        from butler.mcp.registry_hook import get_mcp_tool_definitions

        if mcp_enabled():
            mcp_defs = get_mcp_tool_definitions(session_key)
            known = {_tool_name(d) for d in defs}
            for defn in mcp_defs:
                name = _tool_name(defn)
                if name and name not in known:
                    defs.append(defn)
    except Exception as exc:
        logger.debug("mcp defs for orthogonality skipped: %s", exc)

    if len(defs) < 2:
        return []

    items = _collect_tool_vectors(defs, embedder)
    return _lint_tool_vectors(
        items,
        threshold=threshold,
        max_pairs=max_pairs,
        cross_toolset=True,
    )


def format_orthogonality_report(issues: list[str]) -> str:
    if not issues:
        return "Builtin tool orthogonality: OK (no high-overlap pairs)"
    lines = ["Builtin tool orthogonality warnings:"]
    lines.extend(f"  - {i}" for i in issues)
    return "\n".join(lines)


__all__ = [
    "format_orthogonality_report",
    "lint_builtin_tool_orthogonality",
    "lint_tool_orthogonality_for_diagnostics",
]
