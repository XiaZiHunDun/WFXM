"""Outbound PII scrub best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def scrub_internal_leaks_safe(text: str) -> str:
    def _run() -> str:
        from butler.gateway.internal_leak_scrub import scrub_internal_ops_leaks

        return scrub_internal_ops_leaks(text)

    result = safe_best_effort(
        _run,
        label="pii_scrub.internal_leaks",
        default=text,
    )
    return str(result) if isinstance(result, str) else text
