"""P2: optional owner-facing memory recap when prefetch injected context."""

from __future__ import annotations

import logging
import re
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_TECH_SNIPPET = re.compile(
    r"(/home/|/tmp/|api[_-]?key|token=|sk-[a-z0-9]{8,}|BEGIN )",
    re.I,
)


def memory_recap_enabled() -> bool:
    return env_truthy("BUTLER_MEMORY_RECAP_LINE", default=True)


def memory_recap_min_out_chars() -> int:
    import os

    try:
        return max(0, int(os.getenv("BUTLER_MEMORY_RECAP_MIN_CHARS", "300")))
    except ValueError:
        return 300


def _pick_recap_snippets(health: dict[str, Any] | None, *, limit: int = 2) -> list[str]:
    from butler.core.memory_source_surface import build_memory_sources_snapshot

    h = health or {}
    stored = h.get("memory_last_turn_sources")
    if isinstance(stored, dict) and stored.get("snippet_samples"):
        snap = stored
    else:
        snap = build_memory_sources_snapshot(h)
    if snap.get("prefetch_skipped"):
        return []

    raw = snap.get("snippet_samples")
    if not isinstance(raw, list):
        return []

    picked: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if len(text) < 8 or _TECH_SNIPPET.search(text):
            continue
        if text in picked:
            continue
        picked.append(text[:72] + ("…" if len(text) > 72 else ""))
        if len(picked) >= limit:
            break
    return picked


def build_memory_recap_line(*, health: dict[str, Any] | None = None) -> str | None:
    """One-line recap like ``💭 记得：…`` when memory was prefetched."""
    from butler.core.memory_source_surface import build_memory_sources_snapshot

    h = health or {}
    snap = h.get("memory_last_turn_sources")
    if not isinstance(snap, dict) or not snap:
        snap = build_memory_sources_snapshot(h)
    if snap.get("prefetch_skipped"):
        return None

    snippets = _pick_recap_snippets(h)
    if snippets:
        if len(snippets) == 1:
            return f"💭 记得：{snippets[0]}"
        return "💭 记得：" + "；".join(snippets)

    injected = bool(h.get("memory_context_injected"))
    proj_hits = int(h.get("memory_project_query_hits") or snap.get("memory_project_query_hits") or 0)
    exp_hits = int(h.get("memory_experience_hits") or snap.get("memory_experience_hits") or 0)
    if not injected and not (proj_hits or exp_hits):
        chars = int(h.get("memory_prefetch_chars") or snap.get("memory_prefetch_chars") or 0)
        if chars <= 0:
            return None

    parts: list[str] = []
    if proj_hits:
        parts.append(f"项目记忆 {proj_hits} 条")
    if exp_hits:
        parts.append(f"经验 {exp_hits} 条")
    if parts:
        return "💭 结合记忆：" + " · ".join(parts)
    chars = int(h.get("memory_prefetch_chars") or snap.get("memory_prefetch_chars") or 0)
    if chars:
        return f"💭 结合记忆：预取 {chars} 字符上下文"
    return None


def maybe_prepend_memory_recap(
    session_key: str,
    out_text: str,
    *,
    health: dict[str, Any] | None = None,
) -> str:
    if not memory_recap_enabled():
        return out_text
    out = str(out_text or "")
    if len(out) < memory_recap_min_out_chars():
        return out
    if "💭 记得" in out or "💭 结合记忆" in out:
        return out
    line = build_memory_recap_line(health=health)
    if not line:
        return out
    _ = session_key  # reserved for future per-session throttling
    return f"{line}\n\n{out}"


__all__ = [
    "build_memory_recap_line",
    "maybe_prepend_memory_recap",
    "memory_recap_enabled",
    "memory_recap_min_out_chars",
]
