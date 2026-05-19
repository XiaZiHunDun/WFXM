"""Context-window length inference for preflight compression checks."""

from __future__ import annotations

DEFAULT_CONTEXT_LENGTH = 128000


def infer_context_length(
    *,
    provider: str = "",
    model: str = "",
    configured: int | None = None,
) -> int:
    """Return best-effort context length for a model."""
    if configured is not None:
        try:
            value = int(configured)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    provider_l = (provider or "").lower()
    model_l = (model or "").lower()

    if "deepseek" in provider_l or "deepseek" in model_l:
        return 64000
    if "claude" in provider_l or "anthropic" in provider_l or "claude" in model_l:
        return 200000
    if "minimax" in provider_l or "mini-max" in provider_l or "minimax" in model_l:
        return 200000
    if "qwen" in provider_l or "dashscope" in provider_l or "qwen" in model_l:
        return 32768
    if "gpt-4o" in model_l or "gpt-4.1" in model_l:
        return 128000

    return DEFAULT_CONTEXT_LENGTH
