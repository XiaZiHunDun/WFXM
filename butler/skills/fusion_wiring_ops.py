"""Skill fusion wiring best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def wire_fusion_llm_fn_safe(manager: Any) -> None:
    try:
        from butler.transport.fusion_client import make_fusion_llm_fn

        manager.set_llm_fn(make_fusion_llm_fn())
    except Exception as exc:
        logger.warning("Skill fusion wiring skipped: %s", exc)
