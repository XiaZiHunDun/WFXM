"""Optional auxiliary LLM rubric for prompt-eval cases (PEG P2 / 五报告 H)."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from butler.env_parse import env_truthy

if TYPE_CHECKING:
    from butler.prompt_eval.runner import PromptEvalCase

logger = logging.getLogger(__name__)


def prompt_eval_llm_enabled() -> bool:
    return env_truthy("BUTLER_PROMPT_EVAL_LLM", default=False)


def prompt_eval_llm_min_score() -> int:
    import os

    try:
        return max(0, min(100, int(os.getenv("BUTLER_PROMPT_EVAL_LLM_MIN", "70"))))
    except ValueError:
        return 70


def score_prompt_eval_llm(case: PromptEvalCase, text: str) -> tuple[int | None, str]:
    """Return (score 0–100, note) via auxiliary model, or (None, reason) on skip/failure."""
    if not prompt_eval_llm_enabled():
        return None, "disabled"
    body = str(text or "").strip()
    if not body:
        return None, "empty"
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


def llm_rubric_passes(score: int | None, *, min_score: int | None = None) -> bool:
    if score is None:
        return True
    floor = prompt_eval_llm_min_score() if min_score is None else min_score
    return score >= floor


__all__ = [
    "llm_rubric_passes",
    "prompt_eval_llm_enabled",
    "prompt_eval_llm_min_score",
    "score_prompt_eval_llm",
]
