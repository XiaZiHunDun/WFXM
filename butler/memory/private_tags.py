"""Strip <private> tags before memory persistence (claude-mem subset)."""

from __future__ import annotations

import re

from butler.env_parse import env_truthy

_PRIVATE_BLOCK_RE = re.compile(
    r"<private\b[^>]*>(.*?)</private>",
    re.IGNORECASE | re.DOTALL,
)


def private_tags_enabled() -> bool:
    return env_truthy("BUTLER_MEMORY_PRIVATE_TAGS", default=True)


def strip_private_tags(text: str) -> tuple[str, bool]:
    """Return (public_text, was_entirely_private)."""
    raw = text or ""
    if not private_tags_enabled() or "<private" not in raw.lower():
        stripped = raw.strip()
        return stripped, False

    without_blocks = _PRIVATE_BLOCK_RE.sub("", raw)
    # Entire message wrapped in one private block
    if _PRIVATE_BLOCK_RE.fullmatch(raw.strip(), re.I | re.DOTALL):
        return "", True
    public = without_blocks.strip()
    if not public and _PRIVATE_BLOCK_RE.search(raw):
        return "", True
    return public, False
