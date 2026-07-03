"""Turn scrape dedup bridge bucket best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def scrape_urls_seen_bucket_from_bridge_safe() -> set[str] | None:
    def _run() -> set[str]:
        from butler.execution_context import get_current_turn_bridge

        bridge = get_current_turn_bridge()
        if bridge is None:
            raise ValueError("no turn bridge for scrape dedup")
        bucket = getattr(bridge, "scrape_urls_seen", None)
        if bucket is None:
            bridge.scrape_urls_seen = set()
            bucket = bridge.scrape_urls_seen
        if not isinstance(bucket, set):
            raise ValueError("scrape_urls_seen must be a set")
        return bucket

    result = safe_best_effort(
        _run,
        label="turn_scrape_dedup.bridge_bucket",
        default=None,
    )
    return result if isinstance(result, set) else None
