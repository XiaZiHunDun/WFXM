"""Reasoning replay URL helpers (P0-A)."""

from __future__ import annotations

from urllib.parse import urlparse

from butler.core.best_effort import safe_best_effort


def parse_url_hostname_safe(base_url: str | None) -> str:
    def _run() -> str:
        return (urlparse(str(base_url or "")).hostname or "").lower()

    result = safe_best_effort(
        _run,
        label="reasoning_replay.parse_hostname",
        default="",
    )
    return str(result or "").lower()
