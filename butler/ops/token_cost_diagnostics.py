"""Token usage / cost hints for /诊断 (support line E).

A5/D4 成本模型数值标定：价格表按厂商公开定价维护（USD / 1M tokens）。
"""

from __future__ import annotations

from typing import Any

# (input_usd_per_1M, output_usd_per_1M)  — 按模型关键字从具体到通用排列
_PRICE_TABLE: list[tuple[tuple[str, ...], float, float]] = [
    # --- DeepSeek ---
    (("deepseek-chat", "deepseek-v3"), 0.27, 1.10),
    (("deepseek-reasoner", "deepseek-r1"), 0.55, 2.19),
    (("deepseek",), 0.27, 1.10),
    # --- MiniMax ---
    (("minimax-m3",), 0.20, 0.80),
    (("minimax-m2.7",), 0.12, 0.50),
    (("minimax-text-01",), 0.07, 0.28),
    (("minimax",), 0.20, 0.80),
    # --- Qwen / DashScope ---
    (("qwen-max",), 1.60, 6.40),
    (("qwen-plus",), 0.40, 1.20),
    (("qwen-turbo",), 0.05, 0.20),
    (("qwen-long",), 0.05, 0.20),
    (("qwen",), 0.40, 1.20),
    (("tongyi", "dashscope"), 0.40, 1.20),
    # --- Anthropic ---
    (("claude-sonnet-4", "claude-4-sonnet"), 3.0, 15.0),
    (("claude-opus-4", "claude-4-opus"), 15.0, 75.0),
    (("claude-3.5-sonnet", "claude-3-5-sonnet"), 3.0, 15.0),
    (("claude-3.5-haiku", "claude-3-5-haiku"), 0.80, 4.0),
    (("claude",), 3.0, 15.0),
    # --- OpenAI ---
    (("gpt-4o-mini",), 0.15, 0.60),
    (("gpt-4o",), 2.50, 10.0),
    (("gpt-4-turbo",), 10.0, 30.0),
    (("gpt-4",), 30.0, 60.0),
    (("gpt-3.5",), 0.50, 1.50),
    (("o1-mini",), 3.0, 12.0),
    (("o1",), 15.0, 60.0),
    (("openai",), 2.50, 10.0),
    # --- ZhiPu / GLM ---
    (("glm-4-plus",), 0.50, 0.50),
    (("glm-4",), 0.10, 0.10),
    (("glm", "zhipu", "chatglm"), 0.50, 0.50),
    # --- SiliconFlow (pass-through) ---
    (("siliconflow",), 0.30, 1.00),
]

_FALLBACK_IN, _FALLBACK_OUT = 1.0, 3.0


def _lookup_rate(model: str) -> tuple[float, float]:
    """Return (input, output) rate for model string (USD per 1M tokens)."""
    m = model.lower()
    for keywords, in_rate, out_rate in _PRICE_TABLE:
        if any(k in m for k in keywords):
            return in_rate, out_rate
    return _FALLBACK_IN, _FALLBACK_OUT


def _estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    model: str = "",
) -> float | None:
    """List-price estimate. Intentionally a rough upper bound, not billing truth."""
    pin = max(0, int(prompt_tokens or 0))
    pout = max(0, int(completion_tokens or 0))
    if pin + pout <= 0:
        return None
    in_rate, out_rate = _lookup_rate(model)
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
