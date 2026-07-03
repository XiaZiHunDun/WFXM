"""Mode classifier best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)

ModeLabel = Literal["plan", "do"]


def classify_mode_auxiliary_safe(text: str, *, score_fn: Any) -> ModeLabel | None:
    try:
        from butler.transport.auxiliary_client import auxiliary_complete

        plan, do = score_fn(text)
        if abs(plan - do) > 3:
            return None
        if plan + do < 2:
            return None
        prompt = (
            "Classify the user message for a coding assistant.\n"
            '- "plan": explore, design, or write an implementation plan only; no code changes yet.\n'
            '- "do": execute, edit files, run commands, or delegate implementation.\n'
            "Reply with JSON only: {\"mode\":\"plan\"|\"do\",\"confidence\":0.0-1.0}\n\n"
            f"User message:\n{(text or '')[:800]}"
        )
        raw = auxiliary_complete(
            prompt,
            task="mode_classify",
            system="You output compact JSON only.",
        )
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            return None
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            return None
        mode = str(data.get("mode") or "").strip().lower()
        conf = float(data.get("confidence") or 0)
        if conf < 0.55:
            return None
        if mode in ("plan", "do"):
            return mode  # type: ignore[return-value]
    except Exception as exc:
        logger.debug("mode classifier aux skipped: %s", exc)
    return None


def is_plan_mode_safe(session_key: str) -> bool:
    def _run() -> bool:
        from butler.plan.mode import is_plan_mode

        return bool(is_plan_mode(session_key))

    result = safe_best_effort(
        _run,
        label="mode_classifier.is_plan_mode",
        default=False,
    )
    return bool(result)


def set_plan_mode_safe(session_key: str, enabled: bool) -> bool:
    def _run() -> bool:
        from butler.plan.mode import set_plan_mode

        set_plan_mode(session_key, enabled)
        return True

    result = safe_best_effort(
        _run,
        label="mode_classifier.set_plan_mode",
        default=False,
    )
    return bool(result)
