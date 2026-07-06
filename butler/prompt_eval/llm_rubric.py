"""Optional auxiliary LLM rubric for prompt-eval cases (PEG P2 / 五报告 H)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from butler.env_parse import env_truthy, int_env

if TYPE_CHECKING:
    from butler.prompt_eval.runner import PromptEvalCase


def prompt_eval_llm_enabled() -> bool:
    return cast(bool, env_truthy("BUTLER_PROMPT_EVAL_LLM", default=False))


def prompt_eval_llm_min_score() -> int:
    import os

    try:
        return cast(int, int_env("BUTLER_PROMPT_EVAL_LLM_MIN", 70, min=0, max=100))
    except ValueError:
        return 70


def score_prompt_eval_llm(case: PromptEvalCase, text: str) -> tuple[int | None, str]:
    """Return (score 0–100, note) via auxiliary model, or (None, reason) on skip/failure."""
    if not prompt_eval_llm_enabled():
        return None, "disabled"
    body = str(text or "").strip()
    if not body:
        return None, "empty"
    from butler.prompt_eval.llm_rubric_ops import score_prompt_eval_llm_safe

    return cast(tuple[int | None, str], score_prompt_eval_llm_safe(case, body))


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
