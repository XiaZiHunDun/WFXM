"""Dev eval dataset sync helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def run_dataset_sync_safe(
    label: str,
    run: Callable[[], tuple[dict[str, Any], int]],
) -> tuple[dict[str, Any] | None, int, str]:
    """Return (payload, item_count, error_message)."""
    try:
        payload, items = run()
        return payload, int(items), ""
    except Exception as exc:
        logger.warning("%s dataset sync failed: %s", label, exc)
        return None, 0, f"{label}: {exc}"
