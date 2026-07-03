"""Prompt eval LLM rubric best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.prompt_eval.runner import PromptEvalCase

logger = logging.getLogger(__name__)


def score_prompt_eval_llm_safe(case: "PromptEvalCase", body: str) -> tuple[int | None, str]:
    """Return (score, note) or ``(None, reason)`` on failure."""
    criteria = (case.description or case.id).strip()
    required = ", ".join(case.must_contain[:12])
    forbidden = ", ".join(case.must_not_contain[:8])
    prompt = (
        "Score how well this prompt file meets the rubric (0=poor, 100=excellent).\n"
        f"Rubric: {criteria}\n"
        f"Required phrases (must appear): {required or '(none)'}\n"
        f"Forbidden phrases (must not appear): {forbidden or '(none)'}\n"
        "Reply JSON only: {\"score\": <integer>, \"note\": \"<one line>\"}\n\n"
        f"PROMPT FILE EXCERPT:\n{body[:6000]}"
    )
    try:
        from butler.transport.auxiliary_client import auxiliary_complete

        raw = auxiliary_complete(
            prompt,
            task="prompt_eval",
            system="You are a prompt QA reviewer. Output JSON only.",
        )
        data = None
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
        if isinstance(data, dict) and "score" in data:
            score = max(0, min(100, int(data["score"])))
            note = str(data.get("note") or "").strip()
            return score, note
        m = re.search(r"\b(\d{1,3})\b", raw)
        if m:
            return max(0, min(100, int(m.group(1)))), raw[:120]
    except Exception as exc:
        logger.debug("prompt eval LLM rubric skipped: %s", exc)
    return None, "llm_failed"
