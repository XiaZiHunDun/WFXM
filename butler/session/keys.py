"""Canonical Butler session keys: (platform, chat_id, project)."""

from __future__ import annotations

import re

_NO_PROJECT_SLUG = "_"
_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_:.\-+]+$")
_MAX_KEY_LEN = 256


def _base_session_key(session_key: str) -> str:
    """Strip child/delegate suffixes so parsers see canonical ``platform:chat:project``."""
    return str(session_key or "").split("::", 1)[0]


def slug_project(project: str) -> str:
    """Filesystem-safe project segment for session keys."""
    name = str(project or "").strip()
    return name if name else _NO_PROJECT_SLUG


def build_session_key(
    *,
    platform: str,
    chat_id: str,
    project: str = "",
) -> str:
    """Build ``platform:chat_id:project`` session key (design §5)."""
    plat = str(platform or "unknown").strip() or "unknown"
    cid = str(chat_id or "default").strip() or "default"
    return f"{plat}:{cid}:{slug_project(project)}"


def project_from_session_key(session_key: str) -> str:
    """Extract project name from a v2 session key; legacy two-part keys return ``\"\"``."""
    parts = _base_session_key(session_key).split(":", 2)
    if len(parts) < 3:
        return ""
    slug = parts[2]
    return "" if slug == _NO_PROJECT_SLUG else slug


def chat_id_from_session_key(session_key: str) -> str:
    """Extract chat/channel id from session key."""
    parts = _base_session_key(session_key).split(":", 2)
    if len(parts) < 2:
        return str(session_key or "default")
    return parts[1]


def normalize_session_key(
    *,
    platform: str,
    external_id: str | None = None,
    session_key: str | None = None,
    project: str = "",
) -> str:
    """Resolve a session key from explicit key, external id + project, or legacy two-part key."""
    if external_id is not None and str(external_id).strip():
        return build_session_key(
            platform=platform,
            chat_id=str(external_id).strip(),
            project=project,
        )
    raw = str(session_key or "").strip()
    if not raw:
        return build_session_key(platform=platform, chat_id="default", project=project)
    parts = raw.split(":")
    if len(parts) == 2:
        return build_session_key(platform=parts[0], chat_id=parts[1], project=project)
    validated = _validate_session_key(raw)
    return validated


def _validate_session_key(raw: str) -> str:
    """Sanitize and validate session key format."""
    key = raw[:_MAX_KEY_LEN]
    if not _KEY_PATTERN.match(key):
        import logging

        logging.getLogger(__name__).warning(
            "Session key contains invalid characters, sanitizing: %r",
            raw[:50],
        )
        key = re.sub(r"[^a-zA-Z0-9_:.\-+]", "_", key)
    return key


__all__ = [
    "build_session_key",
    "chat_id_from_session_key",
    "normalize_session_key",
    "project_from_session_key",
    "slug_project",
]
