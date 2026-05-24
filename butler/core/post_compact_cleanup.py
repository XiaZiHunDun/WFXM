"""Lightweight post-compaction housekeeping (Claude Code postCompactCleanup subset)."""

from __future__ import annotations

from typing import Any


def run_post_compact_cleanup(diagnostics: dict[str, Any] | None = None) -> None:
    """Clear stale compact attempt markers after a successful hygiene compact."""
    if diagnostics is None:
        return
    diagnostics.pop("hygiene_compact_noop", None)
    diagnostics.pop("hygiene_compact_error", None)
    diagnostics.pop("hygiene_compact_failed", None)
    diagnostics["post_compact_cleanup"] = True
