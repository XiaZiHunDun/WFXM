"""Experience consolidation best-effort helpers (P0-A)."""

from __future__ import annotations

import logging

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def inc_digestion_metric_safe(metric: str) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc(metric)

    safe_best_effort(_run, label=f"experience_consolidation.{metric}", default=None)


def fusion_complete_loud(prompt: str) -> tuple[str | None, BaseException | None]:
    try:
        from butler.transport.fusion_client import fusion_complete

        return fusion_complete(prompt), None
    except Exception as exc:
        logger.warning("Experience fusion LLM failed: %s", exc)
        return None, exc
