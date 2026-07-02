"""Shared recall scope constants for unified memory search (P3-H)."""

from __future__ import annotations

RECALL_SCOPES: tuple[str, ...] = (
    "experience",
    "project",
    "profile",
    "coding",
    "transcript",
    "observation",
    "hybrid",
)


def parse_recall_scopes(scope: str) -> tuple[list[str], str | None]:
    """Parse ``all``, comma list, or single scope. Returns (scopes, error)."""
    raw = (scope or "experience").strip().lower()
    if raw == "all":
        return list(RECALL_SCOPES), None
    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [raw] if raw else ["experience"]
    unknown = [p for p in parts if p not in RECALL_SCOPES]
    if unknown:
        return [], f"invalid scope(s): {', '.join(unknown)}"
    # preserve order, dedupe
    seen: set[str] = set()
    ordered: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered, None


__all__ = ["RECALL_SCOPES", "parse_recall_scopes"]
