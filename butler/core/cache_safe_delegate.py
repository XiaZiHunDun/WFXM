"""Share static system-prefix with parent loop for delegate prompt-cache alignment."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from butler.env_parse import env_truthy

_DEFAULT_SHARED_CHARS = 4096


def cache_safe_delegate_enabled() -> bool:
    return env_truthy("BUTLER_CACHE_SAFE_DELEGATE", default=True)


def shared_prefix_max_chars() -> int:
    try:
        return max(512, int(os.getenv("BUTLER_CACHE_SAFE_SHARED_CHARS", "") or _DEFAULT_SHARED_CHARS))
    except ValueError:
        return _DEFAULT_SHARED_CHARS


def system_prompt_fingerprint(text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def extract_shared_prefix(parent_system: str, *, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else shared_prefix_max_chars()
    return (parent_system or "").strip()[:limit]


def apply_cache_safe_system_prompt(parent_system: str, child_system: str) -> str:
    """Prepend parent's cacheable prefix when child does not already include it."""
    if not cache_safe_delegate_enabled():
        return child_system
    prefix = extract_shared_prefix(parent_system)
    if not prefix:
        return child_system
    child = (child_system or "").strip()
    if prefix in child:
        return child
    return (
        f"{prefix}\n\n"
        "[DELEGATE — dynamic suffix below; shared prefix matches parent for prompt cache]\n\n"
        f"{child}"
    )


def delegate_diagnostics(
    parent_system: str,
    child_system: str,
) -> dict[str, Any]:
    prefix = extract_shared_prefix(parent_system)
    return {
        "cache_safe_delegate": True,
        "parent_system_fingerprint": system_prompt_fingerprint(parent_system),
        "child_system_fingerprint": system_prompt_fingerprint(child_system),
        "shared_prefix_chars": len(prefix),
    }
