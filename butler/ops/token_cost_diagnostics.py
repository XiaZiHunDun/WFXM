"""Token usage / cost hints for /诊断 (support line E)."""

from __future__ import annotations

from typing import Any


def _estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    model: str = "",
) -> float | None:
    """Rough list-price estimate when BUTLER_TOKEN_COST_ESTIMATE=1 (not billing truth)."""
    m = str(model or "").lower()
    pin = max(0, int(prompt_tokens or 0))
    pout = max(0, int(completion_tokens or 0))
    if pin + pout <= 0:
        return None
    # USD per 1M tokens (very rough defaults)
    if "claude" in m or "anthropic" in m:
        in_rate, out_rate = 3.0, 15.0
    elif "gpt" in m or "openai" in m:
        in_rate, out_rate = 2.5, 10.0
    elif "minimax" in m:
        in_rate, out_rate = 0.3, 1.2
    else:
        in_rate, out_rate = 1.0, 3.0
    return (pin * in_rate + pout * out_rate) / 1_000_000.0


def format_token_cost_diagnostic_lines(
    health: dict[str, Any] | None,
    *,
    model: str = "",
    estimate_cost: bool = False,
) -> list[str]:
    h = health if isinstance(health, dict) else {}
    billable = int(h.get("context_usage_billable_total") or 0)
    last_in = int(h.get("last_usage_prompt_tokens") or 0)
    last_out = int(h.get("last_usage_completion_tokens") or 0)
    cached = int(h.get("last_usage_cached_tokens") or 0)
    if billable <= 0 and last_in <= 0 and last_out <= 0:
        return []

    lines = ["Token / 成本（本会话）:"]
    if billable > 0:
        lines.append(f"  计费 tokens 累计: {billable:,}")
    if last_in or last_out:
        parts = [f"  最近一轮: in={last_in:,} out={last_out:,}"]
        if cached > 0:
            parts.append(f"cache={cached:,}")
        lines.append("".join(parts))
    if estimate_cost and model:
        est = _estimate_cost_usd(last_in, last_out, model=model)
        if est is not None:
            lines.append(f"  粗算成本（最近一轮）: ~${est:.4f} ({model})")
    return lines


def token_cost_estimate_enabled() -> bool:
    import os

    return os.getenv("BUTLER_TOKEN_COST_ESTIMATE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


__all__ = [
    "format_token_cost_diagnostic_lines",
    "token_cost_estimate_enabled",
]
