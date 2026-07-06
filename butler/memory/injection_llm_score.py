"""Optional auxiliary LLM injection risk score (PEG P2 subset)."""

from __future__ import annotations

from typing import cast

from butler.env_parse import env_truthy, int_env


def injection_llm_score_enabled() -> bool:
    return bool(env_truthy("BUTLER_INJECTION_LLM_SCORE", default=False))


def injection_llm_gate_enabled() -> bool:
    """High scores require Owner 确认 + resend instead of hard reject."""
    return bool(env_truthy("BUTLER_INJECTION_LLM_GATE", default=False))


def injection_llm_block_threshold() -> int:
    import os

    try:
        return int(int_env("BUTLER_INJECTION_LLM_BLOCK", 85, min=0, max=100))
    except ValueError:
        return 85


def score_injection_llm(text: str) -> int | None:
    """Return 0–100 risk score via auxiliary model, or None on failure/disabled."""
    if not injection_llm_score_enabled():
        return None
    body = str(text or "").strip()
    if not body or len(body) < 8:
        return None
    from butler.memory.injection_llm_score_ops import score_injection_llm_safe

    return cast(int | None, score_injection_llm_safe(body))


def should_block_inbound_llm_score(text: str) -> tuple[bool, int | None, str]:
    """(block, score, user_message)."""
    score = score_injection_llm(text)
    if score is None:
        return False, None, ""
    if score >= injection_llm_block_threshold():
        return (
            True,
            score,
            f"消息未通过安全评分（injection_score={score}）。请改写后重试。",
        )
    return False, score, ""


__all__ = [
    "injection_llm_block_threshold",
    "injection_llm_gate_enabled",
    "injection_llm_score_enabled",
    "score_injection_llm",
    "should_block_inbound_llm_score",
]
