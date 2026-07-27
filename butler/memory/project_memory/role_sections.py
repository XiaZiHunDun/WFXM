from __future__ import annotations

from typing import Any

from .constants import _ROLE_PREFETCH_PROJECT_MAX_CHARS, _ROLE_SECTIONS


def sections_for_agent_role(role: str) -> tuple[str, ...]:
    key = (role or "default").strip().lower()
    sections = _ROLE_SECTIONS.get(key)
    if sections is not None:
        return sections
    for prefix, secs in _ROLE_SECTIONS.items():
        if prefix != "default" and key.startswith(prefix):
            return secs
    return _ROLE_SECTIONS["default"]


def project_prefetch_max_chars(role: str, *, default: int) -> int:
    key = (role or "default").strip().lower()
    if key in _ROLE_PREFETCH_PROJECT_MAX_CHARS:
        return _ROLE_PREFETCH_PROJECT_MAX_CHARS[key]
    for prefix, cap in _ROLE_PREFETCH_PROJECT_MAX_CHARS.items():
        if key.startswith(prefix):
            return cap
    return default


def filter_memory_hits_by_role(
    hits: list[dict[str, Any]],
    role: str,
) -> list[dict[str, Any]]:
    allowed = set(sections_for_agent_role(role))
    out: list[dict[str, Any]] = []
    for hit in hits:
        sec = (hit.get("section") or "Notes").strip() or "Notes"
        if sec in allowed:
            out.append(hit)
    return out