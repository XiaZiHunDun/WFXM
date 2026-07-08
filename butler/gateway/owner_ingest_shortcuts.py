"""Re-export L4 delegate ingest shortcuts (gateway compat shim)."""

from __future__ import annotations

from butler.delegate.owner_ingest_shortcuts import (
    build_ingest_delegate_prompt,
    looks_owner_ingest_intent,
    try_expand_owner_ingest_phrase,
)

__all__ = [
    "build_ingest_delegate_prompt",
    "looks_owner_ingest_intent",
    "try_expand_owner_ingest_phrase",
]
