"""Builtin tool orthogonality lint — warn on overlapping descriptions within toolsets."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
    return "default"


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
    by_toolset: dict[str, list[tuple[str, list[float]]]] = {}
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
        by_toolset.setdefault(ts, []).append((name, vec))

    issues: list[tuple[float, str]] = []
    for toolset, items in sorted(by_toolset.items()):
        for i in range(len(items)):
            n1, v1 = items[i]
            for j in range(i + 1, len(items)):
                n2, v2 = items[j]
                sim = cosine_similarity(v1, v2)
                if sim >= threshold:
                    issues.append(
                        (
                            sim,
                            f"toolset={toolset}: {n1} ↔ {n2} cosine={sim:.3f} (≥{threshold})",
                        )
                    )

    issues.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in issues[:max_pairs]]


def format_orthogonality_report(issues: list[str]) -> str:
    if not issues:
        return "Builtin tool orthogonality: OK (no high-overlap pairs)"
    lines = ["Builtin tool orthogonality warnings:"]
    lines.extend(f"  - {i}" for i in issues)
    return "\n".join(lines)


__all__ = ["format_orthogonality_report", "lint_builtin_tool_orthogonality"]
