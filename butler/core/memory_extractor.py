"""DEPRECATED: Session-to-project-memory auto-extraction.

This module has been replaced by butler.agent.post_session.PostSessionProcessor
which provides dual-channel extraction (memory + skill).

Kept for backward compatibility. New code should use PostSessionProcessor directly.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.core.memory_extractor is deprecated. Use butler.agent.post_session.PostSessionProcessor instead.",
    DeprecationWarning,
    stacklevel=2,
)


async def extract_session_memories(*args, **kwargs) -> dict:
    """Deprecated stub — always returns empty dict."""
    return {}
