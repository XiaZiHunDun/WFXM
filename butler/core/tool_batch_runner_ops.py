"""Sequential tool-batch helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def parse_tool_call_args_safe(tc: Any) -> dict[str, Any]:
    name = getattr(tc, "name", "?")

    def _run() -> dict[str, Any]:
        raw = tc.args_dict()
        return dict(raw) if isinstance(raw, dict) else {}

    result = safe_best_effort(_run, label=f"tool_batch_runner.args.{name}", default={})
    if not isinstance(result, dict):
        logger.warning("args_dict() parse failed for tool %s", name)
        return {}
    return result
