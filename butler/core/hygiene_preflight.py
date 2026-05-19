"""Gateway hygiene preflight helpers for long-lived AgentLoop sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class HygienePreflightResult:
    messages: list[dict]
    compressed: bool = False


def run_hygiene_preflight(
    messages: list[dict],
    *,
    max_context_tokens: int,
    diagnostics: dict[str, Any],
    estimate_tokens: Callable[[list[dict]], int],
    compress: Callable[..., list[dict]],
    threshold_ratio: float = 0.85,
    hard_message_limit: int = 400,
) -> HygienePreflightResult:
    """Return possibly compressed messages and update diagnostics in-place."""
    for key in list(diagnostics):
        if str(key).startswith("hygiene_"):
            diagnostics.pop(key, None)

    diagnostics.update({
        "hygiene_checked": True,
        "hygiene_compressed": False,
        "hygiene_messages_before": len(messages),
    })
    if len(messages) < 4:
        return HygienePreflightResult(messages=messages, compressed=False)

    estimated = estimate_tokens(messages)
    threshold = int(max_context_tokens * threshold_ratio)
    diagnostics.update({
        "hygiene_estimated_tokens": estimated,
        "hygiene_threshold_tokens": threshold,
    })

    token_limit_hit = estimated >= threshold
    hard_limit_hit = len(messages) >= hard_message_limit
    if not token_limit_hit and not hard_limit_hit:
        return HygienePreflightResult(messages=messages, compressed=False)

    compression_threshold = threshold_ratio if token_limit_hit else 0.0
    compressed = compress(
        messages,
        threshold_ratio=compression_threshold,
        min_messages_to_compress=4,
        head_count=1,
        max_tail_messages=1,
        min_tail_messages=1,
    )
    if compressed == messages:
        return HygienePreflightResult(messages=messages, compressed=False)

    diagnostics.update({
        "hygiene_compressed": True,
        "hygiene_messages_after": len(compressed),
    })
    return HygienePreflightResult(messages=compressed, compressed=True)
