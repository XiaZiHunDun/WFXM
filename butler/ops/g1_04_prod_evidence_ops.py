"""G1-04 production evidence append best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def append_production_evidence_safe(record: dict[str, Any]) -> tuple[bool, str | None]:
    """Return ``(ok, error)``; ``error`` set when append fails."""
    try:
        from butler.ops.eval_actions import append_eval_feedback

        append_eval_feedback(record)
        return True, None
    except Exception as exc:
        logger.debug("G1-04 production evidence skipped: %s", exc)
        return False, str(exc)
