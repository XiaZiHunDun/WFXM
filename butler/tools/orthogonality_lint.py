"""Builtin tool orthogonality lint — warn on overlapping descriptions within toolsets."""

from __future__ import annotations

from typing import Any, cast

# Builtin search tools intentionally overlap MCP scrape/fetch (layered fallback).
_BENIGN_SEARCH_TOOLS = frozenset({"web_search", "web_fetch"})


def _tool_name(defn: dict[str, Any]) -> str:
    fn_raw = defn.get("function")
    fn = fn_raw if isinstance(fn_raw, dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def _tool_description(defn: dict[str, Any]) -> str:
    fn_raw = defn.get("function")
    fn = fn_raw if isinstance(fn_raw, dict) else {}
    return str(fn.get("description") or "").strip().lower()


def _tool_text(defn: dict[str, Any]) -> str:
    """Embedding text for orthogonality: description only (names are fixed API)."""
    return _tool_description(defn)


def _toolset_for(name: str) -> str:
    from butler.tools.orthogonality_lint_ops import toolset_for_safe

    ts = toolset_for_safe(name)
    if ts:
        return cast(str, ts)
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
    return (min(name_a, name_b), max(name_a, name_b))


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
        from butler.tools.orthogonality_lint_ops import embed_tool_text_safe

        vec = embed_tool_text_safe(embedder, _tool_text(defn))
        if vec is None:
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
    from butler.tools.orthogonality_lint_ops import load_embedder_for_lint_safe
    from butler.tools.registry import get_tool_definitions

    embedder, skip = load_embedder_for_lint_safe()
    if embedder is None:
        return [skip or "orthogonality lint skipped: embedder unavailable"]
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
    from butler.tools.orthogonality_lint_ops import (
        get_builtin_tool_definitions_safe,
        get_mcp_tool_definitions_safe,
        load_embedder_for_diagnostics_safe,
    )

    embedder = load_embedder_for_diagnostics_safe()
    if embedder is None:
        return []
    if embedder.model_id.startswith("hashing"):
        return []

    defs: list[dict[str, Any]] = list(get_builtin_tool_definitions_safe())

    mcp_defs = get_mcp_tool_definitions_safe(session_key)
    known = {_tool_name(d) for d in defs}
    for defn in mcp_defs:
        name = _tool_name(defn)
        if name and name not in known:
            defs.append(defn)

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
